'use strict';

/**
 * Database layer using SQLite (better-sqlite3)
 * Handles task execution records, deduplication, and failed notifications.
 */

const path = require('path');
const fs = require('fs');

class Database {
  constructor(dbPath) {
    this.dbPath = path.resolve(dbPath);
    this.db = null;
  }

  init() {
    const dir = path.dirname(this.dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    // Lazy-require so tests can mock easily
    const Database = require('better-sqlite3');
    this.db = new Database(this.dbPath);
    this.db.pragma('journal_mode = WAL');
    this._createTables();
    return this;
  }

  _createTables() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS task_runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     TEXT    NOT NULL,
        started_at  INTEGER NOT NULL,
        finished_at INTEGER,
        status      TEXT    NOT NULL DEFAULT 'running',
        items_found INTEGER DEFAULT 0,
        items_sent  INTEGER DEFAULT 0,
        error       TEXT
      );

      CREATE TABLE IF NOT EXISTS seen_items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     TEXT    NOT NULL,
        item_hash   TEXT    NOT NULL,
        seen_at     INTEGER NOT NULL,
        UNIQUE(task_id, item_hash)
      );

      CREATE TABLE IF NOT EXISTS failed_notifications (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     TEXT    NOT NULL,
        payload     TEXT    NOT NULL,
        created_at  INTEGER NOT NULL,
        attempts    INTEGER DEFAULT 0,
        last_error  TEXT,
        sent        INTEGER DEFAULT 0
      );

      CREATE INDEX IF NOT EXISTS idx_task_runs_task_id ON task_runs(task_id);
      CREATE INDEX IF NOT EXISTS idx_seen_items_task_id ON seen_items(task_id);
      CREATE INDEX IF NOT EXISTS idx_failed_notif_sent ON failed_notifications(sent);
    `);
  }

  // ── Task run lifecycle ──────────────────────────────────────────────────

  startRun(taskId) {
    const stmt = this.db.prepare(
      'INSERT INTO task_runs (task_id, started_at, status) VALUES (?, ?, ?)'
    );
    const info = stmt.run(taskId, Date.now(), 'running');
    return info.lastInsertRowid;
  }

  finishRun(runId, { status, itemsFound = 0, itemsSent = 0, error = null } = {}) {
    this.db.prepare(`
      UPDATE task_runs
      SET finished_at = ?, status = ?, items_found = ?, items_sent = ?, error = ?
      WHERE id = ?
    `).run(Date.now(), status, itemsFound, itemsSent, error, runId);
  }

  // ── Deduplication ────────────────────────────────────────────────────────

  /**
   * Returns true if the item was NOT seen before (i.e. it is new).
   * Inserts it into seen_items so future calls return false.
   */
  markSeen(taskId, hash) {
    try {
      this.db.prepare(
        'INSERT INTO seen_items (task_id, item_hash, seen_at) VALUES (?, ?, ?)'
      ).run(taskId, hash, Date.now());
      return true; // new
    } catch {
      return false; // duplicate (UNIQUE constraint)
    }
  }

  /**
   * Remove items older than windowMs for the given task (housekeeping).
   */
  purgeOldSeen(taskId, windowMs) {
    const cutoff = Date.now() - windowMs;
    this.db.prepare(
      'DELETE FROM seen_items WHERE task_id = ? AND seen_at < ?'
    ).run(taskId, cutoff);
  }

  // ── Failed notifications ─────────────────────────────────────────────────

  saveFailedNotification(taskId, payload) {
    return this.db.prepare(`
      INSERT INTO failed_notifications (task_id, payload, created_at)
      VALUES (?, ?, ?)
    `).run(taskId, JSON.stringify(payload), Date.now()).lastInsertRowid;
  }

  getPendingNotifications() {
    return this.db.prepare(
      'SELECT * FROM failed_notifications WHERE sent = 0 ORDER BY created_at ASC'
    ).all();
  }

  markNotificationSent(id) {
    this.db.prepare(
      'UPDATE failed_notifications SET sent = 1 WHERE id = ?'
    ).run(id);
  }

  updateNotificationAttempt(id, error) {
    this.db.prepare(
      'UPDATE failed_notifications SET attempts = attempts + 1, last_error = ? WHERE id = ?'
    ).run(error, id);
  }

  // ── Statistics API ────────────────────────────────────────────────────────

  getStats(taskId) {
    const row = this.db.prepare(`
      SELECT
        COUNT(*)                                        AS total_runs,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_runs,
        SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) AS failed_runs,
        AVG(CASE WHEN finished_at IS NOT NULL
              THEN finished_at - started_at END)        AS avg_duration_ms,
        SUM(items_found)                                AS total_items_found,
        SUM(items_sent)                                 AS total_items_sent
      FROM task_runs
      WHERE task_id = ?
    `).get(taskId);

    const total = row.total_runs || 0;
    return {
      taskId,
      totalRuns: total,
      successRuns: row.success_runs || 0,
      failedRuns: row.failed_runs || 0,
      successRate: total > 0 ? ((row.success_runs || 0) / total * 100).toFixed(1) + '%' : 'N/A',
      avgDurationMs: row.avg_duration_ms ? Math.round(row.avg_duration_ms) : null,
      totalItemsFound: row.total_items_found || 0,
      totalItemsSent: row.total_items_sent || 0,
    };
  }

  getAllStats() {
    const taskIds = this.db.prepare(
      'SELECT DISTINCT task_id FROM task_runs'
    ).all().map(r => r.task_id);
    return taskIds.map(id => this.getStats(id));
  }

  getRecentRuns(taskId, limit = 10) {
    return this.db.prepare(`
      SELECT * FROM task_runs WHERE task_id = ?
      ORDER BY started_at DESC LIMIT ?
    `).all(taskId, limit);
  }

  close() {
    if (this.db) this.db.close();
  }
}

module.exports = Database;
