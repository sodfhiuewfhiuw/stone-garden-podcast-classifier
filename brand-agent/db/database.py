"""
Database module for Brand Content Strategy Agent.
Handles SQLite initialization and CRUD operations for:
- accounts: tracked competitor and own accounts
- posts: fetched posts from Threads/Instagram
- metrics: performance metrics per post/account
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "brand_agent.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize all database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT NOT NULL,          -- 'threads' | 'instagram'
            account_type TEXT NOT NULL,          -- 'own' | 'competitor'
            username    TEXT NOT NULL,
            account_id  TEXT,                   -- platform-specific ID
            display_name TEXT,
            follower_count INTEGER DEFAULT 0,
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(platform, username)
        );

        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL,
            account_id      INTEGER NOT NULL REFERENCES accounts(id),
            post_id         TEXT NOT NULL,      -- platform-specific post ID
            post_type       TEXT,               -- 'text' | 'image' | 'carousel' | 'reels' | 'video'
            content         TEXT,
            media_url       TEXT,
            permalink       TEXT,
            hashtags        TEXT,               -- JSON array
            published_at    TEXT,
            like_count      INTEGER DEFAULT 0,
            comment_count   INTEGER DEFAULT 0,
            share_count     INTEGER DEFAULT 0,
            reply_count     INTEGER DEFAULT 0,
            reach           INTEGER DEFAULT 0,
            impressions     INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0.0,
            fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(platform, post_id)
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id      INTEGER NOT NULL REFERENCES accounts(id),
            metric_date     TEXT NOT NULL,
            follower_count  INTEGER DEFAULT 0,
            follower_delta  INTEGER DEFAULT 0,
            total_reach     INTEGER DEFAULT 0,
            total_impressions INTEGER DEFAULT 0,
            avg_engagement_rate REAL DEFAULT 0.0,
            post_count      INTEGER DEFAULT 0,
            best_post_id    INTEGER REFERENCES posts(id),
            recorded_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(account_id, metric_date)
        );

        CREATE TABLE IF NOT EXISTS ai_analyses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type   TEXT NOT NULL,      -- 'competitor' | 'content_calendar' | 'weekly_report'
            account_id      INTEGER REFERENCES accounts(id),
            period_start    TEXT,
            period_end      TEXT,
            result_json     TEXT,               -- JSON blob from Claude
            summary_text    TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_posts_account_published
            ON posts(account_id, published_at DESC);

        CREATE INDEX IF NOT EXISTS idx_metrics_account_date
            ON metrics(account_id, metric_date DESC);
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized database at {DB_PATH}")


# ── Account CRUD ─────────────────────────────────────────────────────────────

def upsert_account(platform: str, account_type: str, username: str,
                   account_id: str = None, display_name: str = None,
                   follower_count: int = 0) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO accounts (platform, account_type, username, account_id, display_name, follower_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(platform, username) DO UPDATE SET
            account_id    = excluded.account_id,
            display_name  = excluded.display_name,
            follower_count = excluded.follower_count,
            updated_at    = datetime('now')
    """, (platform, account_type, username, account_id, display_name, follower_count))
    conn.commit()
    row_id = cursor.lastrowid or cursor.execute(
        "SELECT id FROM accounts WHERE platform=? AND username=?", (platform, username)
    ).fetchone()["id"]
    conn.close()
    return row_id


def get_accounts(platform: str = None, account_type: str = None) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM accounts WHERE is_active=1"
    params = []
    if platform:
        query += " AND platform=?"
        params.append(platform)
    if account_type:
        query += " AND account_type=?"
        params.append(account_type)
    rows = cursor.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_account(platform: str, username: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE accounts SET is_active=0, updated_at=datetime('now') WHERE platform=? AND username=?",
        (platform, username)
    )
    conn.commit()
    conn.close()


# ── Post CRUD ─────────────────────────────────────────────────────────────────

def upsert_post(platform: str, account_id: int, post_id: str, **kwargs) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    fields = ["platform", "account_id", "post_id"] + list(kwargs.keys())
    values = [platform, account_id, post_id] + list(kwargs.values())
    placeholders = ", ".join(["?"] * len(fields))
    col_names = ", ".join(fields)
    update_clause = ", ".join(
        f"{k} = excluded.{k}" for k in kwargs.keys()
    ) + ", fetched_at = datetime('now')"

    cursor.execute(f"""
        INSERT INTO posts ({col_names})
        VALUES ({placeholders})
        ON CONFLICT(platform, post_id) DO UPDATE SET {update_clause}
    """, values)
    conn.commit()
    row_id = cursor.lastrowid or cursor.execute(
        "SELECT id FROM posts WHERE platform=? AND post_id=?", (platform, post_id)
    ).fetchone()["id"]
    conn.close()
    return row_id


def get_posts(account_id: int = None, platform: str = None,
              limit: int = 50, since: str = None) -> list:
    conn = get_connection()
    query = "SELECT * FROM posts WHERE 1=1"
    params = []
    if account_id:
        query += " AND account_id=?"
        params.append(account_id)
    if platform:
        query += " AND platform=?"
        params.append(platform)
    if since:
        query += " AND published_at >= ?"
        params.append(since)
    query += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_posts(account_id: int, limit: int = 5) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM posts
        WHERE account_id=?
        ORDER BY engagement_rate DESC, like_count DESC
        LIMIT ?
    """, (account_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Metrics CRUD ──────────────────────────────────────────────────────────────

def upsert_metric(account_id: int, metric_date: str, **kwargs) -> None:
    conn = get_connection()
    fields = ["account_id", "metric_date"] + list(kwargs.keys())
    values = [account_id, metric_date] + list(kwargs.values())
    placeholders = ", ".join(["?"] * len(fields))
    col_names = ", ".join(fields)
    update_clause = ", ".join(f"{k} = excluded.{k}" for k in kwargs.keys())

    conn.execute(f"""
        INSERT INTO metrics ({col_names})
        VALUES ({placeholders})
        ON CONFLICT(account_id, metric_date) DO UPDATE SET {update_clause}
    """, values)
    conn.commit()
    conn.close()


def get_metrics(account_id: int, days: int = 30) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM metrics
        WHERE account_id=?
        ORDER BY metric_date DESC
        LIMIT ?
    """, (account_id, days)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI Analyses ───────────────────────────────────────────────────────────────

def save_analysis(analysis_type: str, result_json: str, summary_text: str = None,
                  account_id: int = None, period_start: str = None, period_end: str = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_analyses
            (analysis_type, account_id, period_start, period_end, result_json, summary_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (analysis_type, account_id, period_start, period_end, result_json, summary_text))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_latest_analysis(analysis_type: str, account_id: int = None) -> Optional[dict]:
    conn = get_connection()
    query = "SELECT * FROM ai_analyses WHERE analysis_type=?"
    params = [analysis_type]
    if account_id:
        query += " AND account_id=?"
        params.append(account_id)
    query += " ORDER BY created_at DESC LIMIT 1"
    row = conn.execute(query, params).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Settings ──────────────────────────────────────────────────────────────────

def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
    """, (key, value))
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = None) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


if __name__ == "__main__":
    init_db()
    print("[DB] Schema created successfully.")
