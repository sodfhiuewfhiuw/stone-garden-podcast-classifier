'use strict';

/**
 * Unit tests for core/task.js
 * Covers retry logic, scoring, deduplication, and the full OODA loop.
 */

const path = require('path');
const os   = require('os');
const fs   = require('fs');
const Database  = require('../core/database');
const TaskRunner = require('../core/task');

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeTmpDb() {
  const dir    = fs.mkdtempSync(path.join(os.tmpdir(), 'task-test-'));
  const dbPath = path.join(dir, 'test.db');
  const db     = new Database(dbPath).init();
  return { db, cleanup: () => { db.close(); fs.rmSync(dir, { recursive: true }); } };
}

function makeLogger() {
  return { info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() };
}

function makeConnector(items) {
  return {
    init:  jest.fn().mockResolvedValue(undefined),
    fetch: jest.fn().mockResolvedValue(items),
  };
}

function makeAnalyzer(enrichment = {}) {
  return { analyze: jest.fn().mockResolvedValue(enrichment) };
}

function makeNotifier() {
  return { send: jest.fn().mockResolvedValue(undefined) };
}

const BASE_CONFIG = {
  id:   'unit-task',
  name: '單元測試任務',
  enabled: true,
  observe: {
    connector: 'mock',
    config:    { keywords: ['test'] },
    schedule:  '* * * * *',
  },
  orient: { ai_analysis: false },
  decide: {
    priority_scoring: { has_email: 20, has_phone: 10, mentions_salary: 15 },
    min_score: 0,
    deduplicate_window: '1h',
  },
  act: { notify: true, store: true },
};

function makeRunner(overrides = {}) {
  const { db, cleanup } = makeTmpDb();
  const runner = new TaskRunner({
    config:    BASE_CONFIG,
    connector: makeConnector([]),
    analyzer:  makeAnalyzer(),
    notifier:  makeNotifier(),
    db,
    logger:    makeLogger(),
    ...overrides,
  });
  return { runner, db, cleanup };
}

// ── Concurrency guard ─────────────────────────────────────────────────────────

describe('TaskRunner - concurrency guard', () => {
  test('second run() is skipped while first is running', async () => {
    const { runner, cleanup } = makeRunner({
      connector: {
        init:  jest.fn().mockResolvedValue(undefined),
        fetch: jest.fn().mockImplementation(() => new Promise(r => setTimeout(() => r([]), 100))),
      },
    });
    const [r1, r2] = await Promise.all([runner.run(), runner.run()]);
    expect(r2).toBeUndefined();
    cleanup();
  });
});

// ── Retry logic ───────────────────────────────────────────────────────────────

describe('TaskRunner - retry logic', () => {
  test('retries connector up to 3 times then propagates error', async () => {
    const { runner, db, cleanup } = makeRunner({
      connector: {
        init:  jest.fn().mockResolvedValue(undefined),
        fetch: jest.fn().mockRejectedValue(new Error('timeout')),
      },
    });

    const result = await runner.run();
    expect(result.error).toBe('timeout');
    expect(result.itemsSent).toBe(0);

    const stats = db.getStats('unit-task');
    expect(stats.failedRuns).toBe(1);
    cleanup();
  });

  test('succeeds after transient connector failure', async () => {
    let calls = 0;
    const item = { post_id: 'r1', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() };
    const { runner, cleanup } = makeRunner({
      connector: {
        init:  jest.fn().mockResolvedValue(undefined),
        fetch: jest.fn().mockImplementation(() => {
          calls++;
          if (calls < 3) throw new Error('transient');
          return Promise.resolve([item]);
        }),
      },
    });

    const result = await runner.run();
    expect(result.itemsFound).toBe(1);
    expect(result.error).toBeNull();
    cleanup();
  });
});

// ── Scoring ───────────────────────────────────────────────────────────────────

describe('TaskRunner - scoring', () => {
  test('item with all fields scores 45 (20+10+15)', async () => {
    const notifier = makeNotifier();
    const item = {
      post_id: 'sc1', url: 'http://x', username: 'u', content: 'c',
      email: 'a@b.com', phone: '0912345678', salary: '50k',
      timestamp: Date.now(),
    };
    const { runner, cleanup } = makeRunner({
      connector: makeConnector([item]),
      notifier,
    });

    const result = await runner.run();
    expect(result.itemsSent).toBe(1);
    const sentItem = notifier.send.mock.calls[0][1];
    expect(sentItem._score).toBe(45);
    cleanup();
  });

  test('item with only email scores 20', async () => {
    const notifier = makeNotifier();
    const item = {
      post_id: 'sc2', url: 'http://x', username: 'u', content: 'c',
      email: 'a@b.com', timestamp: Date.now(),
    };
    const { runner, cleanup } = makeRunner({ connector: makeConnector([item]), notifier });

    await runner.run();
    const sentItem = notifier.send.mock.calls[0][1];
    expect(sentItem._score).toBe(20);
    cleanup();
  });

  test('item with no contact info scores 0', async () => {
    const notifier = makeNotifier();
    const item = { post_id: 'sc3', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() };
    const { runner, cleanup } = makeRunner({ connector: makeConnector([item]), notifier });

    await runner.run();
    const sentItem = notifier.send.mock.calls[0][1];
    expect(sentItem._score).toBe(0);
    cleanup();
  });

  test('item below min_score is not sent', async () => {
    const notifier = makeNotifier();
    const cfg = { ...BASE_CONFIG, decide: { ...BASE_CONFIG.decide, min_score: 30 } };
    const item = { post_id: 'sc4', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() };
    const { db, cleanup } = makeTmpDb();
    const runner = new TaskRunner({
      config: cfg, connector: makeConnector([item]),
      analyzer: makeAnalyzer(), notifier, db, logger: makeLogger(),
    });

    const result = await runner.run();
    expect(result.itemsSent).toBe(0);
    expect(notifier.send).not.toHaveBeenCalled();
    cleanup();
  });
});

// ── Deduplication ─────────────────────────────────────────────────────────────

describe('TaskRunner - deduplication', () => {
  test('same item across two runs is only notified once', async () => {
    const notifier = makeNotifier();
    const item = { post_id: 'dup', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() };
    const { db, cleanup } = makeTmpDb();

    for (let i = 0; i < 2; i++) {
      const runner = new TaskRunner({
        config: BASE_CONFIG, connector: makeConnector([item]),
        analyzer: makeAnalyzer(), notifier, db, logger: makeLogger(),
      });
      await runner.run();
    }

    expect(notifier.send).toHaveBeenCalledTimes(1);
    cleanup();
  });

  test('different items are each notified', async () => {
    const notifier = makeNotifier();
    const items = [
      { post_id: 'a', url: 'http://a', username: 'u', content: 'alpha', timestamp: Date.now() },
      { post_id: 'b', url: 'http://b', username: 'u', content: 'beta',  timestamp: Date.now() },
    ];
    const { runner, cleanup } = makeRunner({ connector: makeConnector(items), notifier });

    await runner.run();
    expect(notifier.send).toHaveBeenCalledTimes(2);
    cleanup();
  });
});

// ── Notifier failure ──────────────────────────────────────────────────────────

describe('TaskRunner - notifier failure', () => {
  test('failed notification is saved to DB', async () => {
    const item = { post_id: 'fn1', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() };
    const failingNotifier = { send: jest.fn().mockRejectedValue(new Error('TG down')) };
    const { db, cleanup } = makeTmpDb();
    const runner = new TaskRunner({
      config: BASE_CONFIG, connector: makeConnector([item]),
      analyzer: makeAnalyzer(), notifier: failingNotifier, db, logger: makeLogger(),
    });

    await runner.run();
    const pending = db.getPendingNotifications();
    expect(pending.length).toBe(1);
    expect(pending[0].task_id).toBe('unit-task');
    cleanup();
  });

  test('one notifier failure does not block other items', async () => {
    let callCount = 0;
    const notifier = {
      send: jest.fn().mockImplementation(() => {
        callCount++;
        // Fail the first item, succeed the rest
        if (callCount === 1) return Promise.reject(new Error('first fails'));
        return Promise.resolve();
      }),
    };
    const items = [
      { post_id: 'i1', url: 'http://a', username: 'u', content: 'a', timestamp: Date.now() },
      { post_id: 'i2', url: 'http://b', username: 'u', content: 'b', timestamp: Date.now() },
    ];
    const { db, cleanup } = makeTmpDb();
    const runner = new TaskRunner({
      config: BASE_CONFIG, connector: makeConnector(items),
      analyzer: makeAnalyzer(), notifier, db, logger: makeLogger(),
    });

    const result = await runner.run();
    // First item exhausts 3 retries (all fail) → saved to DB
    // Second item succeeds on first attempt
    expect(result.itemsSent).toBe(1);
    cleanup();
  });
});

// ── AI orient ────────────────────────────────────────────────────────────────

describe('TaskRunner - orient (AI)', () => {
  test('ai_analysis merges enrichment into item', async () => {
    const notifier = makeNotifier();
    const cfg = { ...BASE_CONFIG, orient: { ai_analysis: true } };
    const item = { post_id: 'o1', url: 'http://x', username: 'u', content: '台中徵才', timestamp: Date.now() };
    const analyzer = makeAnalyzer({ email: 'hr@company.com', is_taichung: true });
    const { db, cleanup } = makeTmpDb();
    const runner = new TaskRunner({
      config: cfg, connector: makeConnector([item]),
      analyzer, notifier, db, logger: makeLogger(),
    });

    await runner.run();
    expect(analyzer.analyze).toHaveBeenCalledWith(item, cfg.orient);
    const sentItem = notifier.send.mock.calls[0][1];
    expect(sentItem.email).toBe('hr@company.com');
    cleanup();
  });

  test('ai_analysis failure falls back to raw item', async () => {
    const notifier = makeNotifier();
    const cfg = { ...BASE_CONFIG, orient: { ai_analysis: true } };
    const item = { post_id: 'o2', url: 'http://x', username: 'u', content: 'test', timestamp: Date.now() };
    const failAnalyzer = { analyze: jest.fn().mockRejectedValue(new Error('AI down')) };
    const { db, cleanup } = makeTmpDb();
    const runner = new TaskRunner({
      config: cfg, connector: makeConnector([item]),
      analyzer: failAnalyzer, notifier, db, logger: makeLogger(),
    });

    const result = await runner.run();
    // Item still sent using raw data
    expect(result.itemsSent).toBe(1);
    cleanup();
  });
});

// ── DB stats recording ────────────────────────────────────────────────────────

describe('TaskRunner - DB recording', () => {
  test('successful run is recorded in DB', async () => {
    const items = [{ post_id: 'db1', url: 'http://x', username: 'u', content: 'c', timestamp: Date.now() }];
    const { runner, db, cleanup } = makeRunner({ connector: makeConnector(items) });

    await runner.run();
    const stats = db.getStats('unit-task');
    expect(stats.totalRuns).toBe(1);
    expect(stats.successRuns).toBe(1);
    expect(stats.totalItemsFound).toBe(1);
    cleanup();
  });

  test('failed run is recorded in DB', async () => {
    const { runner, db, cleanup } = makeRunner({
      connector: {
        init:  jest.fn().mockResolvedValue(undefined),
        fetch: jest.fn().mockRejectedValue(new Error('boom')),
      },
    });

    await runner.run();
    const stats = db.getStats('unit-task');
    expect(stats.totalRuns).toBe(1);
    expect(stats.failedRuns).toBe(1);
    cleanup();
  });
});
