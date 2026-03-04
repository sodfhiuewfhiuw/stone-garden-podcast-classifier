'use strict';

/**
 * End-to-end tests for the full OODA pipeline.
 * Uses in-memory SQLite and mocked connector/analyzer/notifier.
 */

const path = require('path');
const os = require('os');
const fs = require('fs');
const Database = require('../core/database');
const TaskRunner = require('../core/task');

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeTmpDb() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-test-'));
  const dbPath = path.join(dir, 'test.db');
  const db = new Database(dbPath).init();
  return { db, cleanup: () => { db.close(); fs.rmSync(dir, { recursive: true }); } };
}

function makeLogger() {
  return {
    info: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
    error: jest.fn(),
  };
}

function makeMockConnector(items) {
  return {
    init: jest.fn().mockResolvedValue(undefined),
    fetch: jest.fn().mockResolvedValue(items),
  };
}

function makeMockAnalyzer(enrichment = {}) {
  return {
    analyze: jest.fn().mockResolvedValue(enrichment),
  };
}

function makeMockNotifier(sendImpl) {
  return {
    send: sendImpl || jest.fn().mockResolvedValue(undefined),
  };
}

const BASE_TASK_CONFIG = {
  id: 'test-task',
  name: '端到端測試任務',
  enabled: true,
  observe: {
    connector: 'mock',
    config: { keywords: ['測試'], max_posts: 5 },
    schedule: '* * * * *',
  },
  orient: { ai_analysis: false },
  decide: {
    priority_scoring: { has_email: 20, has_phone: 10, mentions_salary: 15 },
    min_score: 0,
    deduplicate_window: '1h',
  },
  act: { notify: true, store: true },
};

// ── Full pipeline ──────────────────────────────────────────────────────────────

describe('End-to-end pipeline', () => {
  let db, cleanup;

  beforeEach(() => {
    ({ db, cleanup } = makeTmpDb());
  });

  afterEach(() => cleanup());

  test('run() processes items and returns stats', async () => {
    const items = [
      { post_id: 'p1', url: 'https://t.net/p/1', username: 'user1', content: '台中徵才', timestamp: Date.now() },
      { post_id: 'p2', url: 'https://t.net/p/2', username: 'user2', content: '台北徵才', timestamp: Date.now() },
    ];

    const runner = new TaskRunner({
      config: BASE_TASK_CONFIG,
      connector: makeMockConnector(items),
      analyzer: makeMockAnalyzer(),
      notifier: makeMockNotifier(),
      db,
      logger: makeLogger(),
    });

    const result = await runner.run();
    expect(result.itemsFound).toBe(2);
    expect(result.itemsSent).toBe(2);
    expect(result.error).toBeNull();
  });

  test('run() deduplicates repeated items across two runs', async () => {
    const items = [
      { post_id: 'dup1', url: 'https://t.net/p/dup1', username: 'u', content: 'same', timestamp: Date.now() },
    ];

    const notifier = makeMockNotifier();

    for (let i = 0; i < 2; i++) {
      const runner = new TaskRunner({
        config: BASE_TASK_CONFIG,
        connector: makeMockConnector(items),
        analyzer: makeMockAnalyzer(),
        notifier,
        db,
        logger: makeLogger(),
      });
      await runner.run();
    }

    // Notifier should only be called once (second run deduplicates)
    expect(notifier.send).toHaveBeenCalledTimes(1);
  });

  test('run() skips items below min_score', async () => {
    const taskCfg = {
      ...BASE_TASK_CONFIG,
      decide: { ...BASE_TASK_CONFIG.decide, min_score: 30 },
    };
    const items = [
      { post_id: 's1', url: 'https://t.net/p/s1', username: 'u', content: 'no contact info', timestamp: Date.now() },
    ];

    const notifier = makeMockNotifier();
    const runner = new TaskRunner({
      config: taskCfg,
      connector: makeMockConnector(items),
      analyzer: makeMockAnalyzer(),
      notifier,
      db,
      logger: makeLogger(),
    });

    const result = await runner.run();
    expect(result.itemsSent).toBe(0);
    expect(notifier.send).not.toHaveBeenCalled();
  });

  test('run() scores items correctly', async () => {
    const notifier = makeMockNotifier();
    const items = [
      { post_id: 'scored', url: 'https://t.net/p/s', username: 'u', content: 'c', email: 'x@y.com', phone: '0912', salary: '50k', timestamp: Date.now() },
    ];
    const runner = new TaskRunner({
      config: BASE_TASK_CONFIG,
      connector: makeMockConnector(items),
      analyzer: makeMockAnalyzer({ email: 'x@y.com', phone: '0912', salary: '50k' }),
      notifier,
      db,
      logger: makeLogger(),
    });

    const result = await runner.run();
    expect(result.itemsSent).toBe(1);
    // Score = has_email(20) + has_phone(10) + mentions_salary(15) = 45 >= min_score(0)
    expect(notifier.send).toHaveBeenCalledTimes(1);
  });

  test('run() records failure when connector throws', async () => {
    const connector = {
      init: jest.fn().mockResolvedValue(undefined),
      fetch: jest.fn().mockRejectedValue(new Error('Connector boom')),
    };

    const runner = new TaskRunner({
      config: BASE_TASK_CONFIG,
      connector,
      analyzer: makeMockAnalyzer(),
      notifier: makeMockNotifier(),
      db,
      logger: makeLogger(),
    });

    const result = await runner.run();
    expect(result.error).toBe('Connector boom');
    expect(result.itemsSent).toBe(0);
  });

  test('run() saves failed notification to DB when notifier throws', async () => {
    const items = [
      { post_id: 'fn1', url: 'https://t.net/p/fn1', username: 'u', content: 'c', timestamp: Date.now() },
    ];
    const notifier = makeMockNotifier(jest.fn().mockRejectedValue(new Error('TG down')));

    const runner = new TaskRunner({
      config: BASE_TASK_CONFIG,
      connector: makeMockConnector(items),
      analyzer: makeMockAnalyzer(),
      notifier,
      db,
      logger: makeLogger(),
    });

    await runner.run();
    const pending = db.getPendingNotifications();
    expect(pending.length).toBe(1);
    expect(pending[0].task_id).toBe('test-task');
  });

  test('run() does not run if already running', async () => {
    const connector = {
      init: jest.fn().mockResolvedValue(undefined),
      fetch: jest.fn().mockImplementation(() => new Promise(r => setTimeout(() => r([]), 200))),
    };
    const runner = new TaskRunner({
      config: BASE_TASK_CONFIG,
      connector,
      analyzer: makeMockAnalyzer(),
      notifier: makeMockNotifier(),
      db,
      logger: makeLogger(),
    });

    const [r1, r2] = await Promise.all([runner.run(), runner.run()]);
    // Only one actual fetch should happen
    expect(connector.fetch).toHaveBeenCalledTimes(1);
    expect(r2).toBeUndefined(); // second run skipped
  });
});

// ── Database stats ─────────────────────────────────────────────────────────────

describe('Database stats', () => {
  let db, cleanup;

  beforeEach(() => ({ db, cleanup } = makeTmpDb()));
  afterEach(() => cleanup());

  test('getStats returns zeros for unknown task', () => {
    const stats = db.getStats('nonexistent');
    expect(stats.totalRuns).toBe(0);
    expect(stats.successRate).toBe('N/A');
  });

  test('getStats accumulates success/failure', () => {
    const id = 'stat-task';
    const r1 = db.startRun(id);
    db.finishRun(r1, { status: 'success', itemsFound: 5, itemsSent: 3 });
    const r2 = db.startRun(id);
    db.finishRun(r2, { status: 'failed', error: 'oops' });

    const stats = db.getStats(id);
    expect(stats.totalRuns).toBe(2);
    expect(stats.successRuns).toBe(1);
    expect(stats.failedRuns).toBe(1);
    expect(stats.successRate).toBe('50.0%');
    expect(stats.totalItemsFound).toBe(5);
    expect(stats.totalItemsSent).toBe(3);
  });

  test('markSeen returns true for new and false for duplicate', () => {
    expect(db.markSeen('t', 'hash1')).toBe(true);
    expect(db.markSeen('t', 'hash1')).toBe(false);
    expect(db.markSeen('t', 'hash2')).toBe(true);
  });
});
