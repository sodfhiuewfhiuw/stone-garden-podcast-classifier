'use strict';

/**
 * TaskRunner - OODA Loop executor for a single task.
 *
 * Features:
 *  - Observe → Orient → Decide → Act pipeline
 *  - Automatic retry with exponential backoff (1s → 2s → 4s)
 *  - Task isolation: exceptions do not propagate to the engine
 *  - Deduplication via seen_items DB table
 *  - Graceful recovery: DB-backed state survives restarts
 */

const crypto = require('crypto');

const MAX_RETRIES = 3;
const BASE_RETRY_DELAY_MS = 1000;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function parseWindow(windowStr) {
  if (!windowStr) return 24 * 60 * 60 * 1000;
  const match = String(windowStr).match(/^(\d+)(h|m|s|d)$/);
  if (!match) return 24 * 60 * 60 * 1000;
  const n = parseInt(match[1], 10);
  const unit = match[2];
  const ms = { s: 1000, m: 60000, h: 3600000, d: 86400000 };
  return n * ms[unit];
}

function hashItem(item) {
  const key = [item.url, item.post_id, item.content].filter(Boolean).join('|');
  return crypto.createHash('sha256').update(key).digest('hex');
}

function applyScoring(item, scoringCfg) {
  let score = 0;
  if (!scoringCfg) return score;
  if (scoringCfg.has_email && item.email) score += scoringCfg.has_email;
  if (scoringCfg.has_phone && item.phone) score += scoringCfg.has_phone;
  if (scoringCfg.mentions_salary && item.salary) score += scoringCfg.mentions_salary;
  return score;
}

class TaskRunner {
  /**
   * @param {object} opts
   * @param {object}   opts.config    - Task config from matrix.yaml
   * @param {object}   opts.connector - Connector instance
   * @param {object}   opts.analyzer  - Analyzer instance
   * @param {object}   opts.notifier  - Notifier instance
   * @param {object}   opts.db        - Database instance
   * @param {object}   opts.logger    - Winston logger
   */
  constructor({ config, connector, analyzer, notifier, db, logger }) {
    this.config = config;
    this.connector = connector;
    this.analyzer = analyzer;
    this.notifier = notifier;
    this.db = db;
    this.logger = logger;
    this.isRunning = false;
  }

  // ── Public entry point ────────────────────────────────────────────────────

  async run() {
    if (this.isRunning) {
      this.logger.warn(`任務已在執行中，跳過本次: ${this.config.id}`);
      return;
    }
    this.isRunning = true;
    const runId = this.db.startRun(this.config.id);
    this.logger.info(`任務開始: ${this.config.id}`, { runId });

    let itemsFound = 0;
    let itemsSent = 0;
    let lastError = null;

    try {
      // ── Observe ──────────────────────────────────────────────────────────
      const rawItems = await this._withRetry(
        () => this._observe(),
        `${this.config.id}:observe`
      );

      itemsFound = rawItems.length;
      this.logger.info(`Observe 完成: ${this.config.id}`, { itemsFound });

      // ── Orient ───────────────────────────────────────────────────────────
      const orientedItems = await this._orient(rawItems);

      // ── Decide ───────────────────────────────────────────────────────────
      const selectedItems = this._decide(orientedItems);

      // ── Act ──────────────────────────────────────────────────────────────
      itemsSent = await this._act(selectedItems);

      this.db.finishRun(runId, { status: 'success', itemsFound, itemsSent });
      this.logger.info(`任務完成: ${this.config.id}`, { runId, itemsFound, itemsSent });
    } catch (err) {
      lastError = err.message;
      this.logger.error(`任務失敗: ${this.config.id}`, { runId, error: err.message });
      this.db.finishRun(runId, { status: 'failed', itemsFound, itemsSent, error: err.message });
    } finally {
      this.isRunning = false;
    }

    return { runId, itemsFound, itemsSent, error: lastError };
  }

  // ── OODA stages ───────────────────────────────────────────────────────────

  async _observe() {
    const observeCfg = this.config.observe;
    if (!this.connector.init) {
      throw new Error('Connector missing init()');
    }
    await this.connector.init();
    return this.connector.fetch(observeCfg.config);
  }

  async _orient(items) {
    const orientCfg = this.config.orient;
    if (!orientCfg || !orientCfg.ai_analysis) return items;

    const enriched = [];
    for (const item of items) {
      try {
        const analysis = await this._withRetry(
          () => this.analyzer.analyze(item, orientCfg),
          `${this.config.id}:orient:${item.post_id || item.url}`
        );
        enriched.push({ ...item, ...analysis });
      } catch (err) {
        this.logger.warn(`AI 分析失敗，使用原始資料: ${item.post_id}`, { error: err.message });
        enriched.push(item);
      }
    }
    return enriched;
  }

  _decide(items) {
    const decideCfg = this.config.decide || {};
    const windowMs = parseWindow(decideCfg.deduplicate_window);
    const minScore = decideCfg.min_score || 0;
    const scoringCfg = decideCfg.priority_scoring;

    // Housekeeping: remove old seen entries
    this.db.purgeOldSeen(this.config.id, windowMs);

    const selected = [];
    for (const item of items) {
      const hash = hashItem(item);

      // Deduplication
      if (!this.db.markSeen(this.config.id, hash)) {
        this.logger.debug(`重複項目，跳過: ${this.config.id}`, { hash });
        continue;
      }

      // Scoring
      const score = applyScoring(item, scoringCfg);
      if (score < minScore) {
        this.logger.debug(`分數不足，跳過: ${this.config.id}`, { score, minScore });
        continue;
      }

      selected.push({ ...item, _score: score });
    }

    // Sort by score descending
    selected.sort((a, b) => b._score - a._score);
    this.logger.info(`Decide 完成: ${this.config.id}`, { selected: selected.length, from: items.length });
    return selected;
  }

  async _act(items) {
    const actCfg = this.config.act || {};
    if (!actCfg.notify) return 0;

    // Concurrency limit: default 3 parallel notifications
    const concurrency = actCfg.concurrency || 3;
    let sent = 0;
    let index = 0;

    const worker = async () => {
      while (index < items.length) {
        const item = items[index++];
        const success = await this._sendWithRetry(item);
        if (success) sent++;
      }
    };

    const workerCount = Math.min(concurrency, items.length || 1);
    await Promise.all(Array.from({ length: workerCount }, worker));
    return sent;
  }

  async _sendWithRetry(item) {
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        await this.notifier.send(this.config, item);
        return true;
      } catch (err) {
        this.logger.warn(`通知發送失敗 (嘗試 ${attempt}/${MAX_RETRIES})`, { error: err.message });
        if (attempt === MAX_RETRIES) {
          // Save to DB for manual resend
          const failId = this.db.saveFailedNotification(this.config.id, item);
          this.logger.error(`通知已記錄到資料庫供手動重發: ${failId}`);
          return false;
        }
        await sleep(BASE_RETRY_DELAY_MS * Math.pow(2, attempt - 1));
      }
    }
    return false;
  }

  // ── Retry helper ──────────────────────────────────────────────────────────

  async _withRetry(fn, label) {
    let lastErr;
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        return await fn();
      } catch (err) {
        lastErr = err;
        this.logger.warn(`重試 ${label} (${attempt}/${MAX_RETRIES})`, { error: err.message });
        if (attempt < MAX_RETRIES) {
          await sleep(BASE_RETRY_DELAY_MS * Math.pow(2, attempt - 1));
        }
      }
    }
    throw lastErr;
  }
}

// ── Manual resend utility (called by scripts/resend.js or admin API) ─────────

TaskRunner.resendPending = async function (db, notifier, taskConfig, logger) {
  const pending = db.getPendingNotifications();
  let resent = 0;
  for (const row of pending) {
    let payload;
    try {
      payload = JSON.parse(row.payload);
    } catch {
      logger.error(`無法解析失敗通知 payload: ${row.id}`);
      continue;
    }
    try {
      await notifier.send(taskConfig, payload);
      db.markNotificationSent(row.id);
      resent++;
      logger.info(`手動重發成功: ${row.id}`);
    } catch (err) {
      db.updateNotificationAttempt(row.id, err.message);
      logger.warn(`手動重發失敗: ${row.id}`, { error: err.message });
    }
  }
  return resent;
};

module.exports = TaskRunner;
