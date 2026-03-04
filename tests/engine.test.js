'use strict';

/**
 * Tests for core/engine.js
 * Uses temp files and mocked dependencies to test lifecycle and hot-reload.
 */

const path = require('path');
const os   = require('os');
const fs   = require('fs');

// ── Helpers ───────────────────────────────────────────────────────────────────

function writeTmpConfig(dir, cfg) {
  const p = path.join(dir, 'matrix.yaml');
  const yaml = require('js-yaml');
  fs.writeFileSync(p, yaml.dump(cfg));
  return p;
}

function makeMinimalConfig(overrides = {}) {
  return {
    version: '1.0-alpha',
    system: {
      name: 'test-matrix',
      timezone: 'Asia/Taipei',
      log_level: 'error',   // suppress log noise during tests
      database: { path: '' }, // filled per-test
      notifications: {
        default_channel: 'telegram',
        channels: { telegram: { enabled: false, bot_token: 'x', chat_id: '1' } },
      },
      ai: {
        default_provider: 'gemini',
        providers: { gemini: { model: 'm', api_url: 'http://x', api_key: '' } },
      },
    },
    tasks: [],
    connectors: {},
    plugins: {},
    ...overrides,
  };
}

function makeTmpEnv() {
  const dir    = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-test-'));
  const dbPath = path.join(dir, 'test.db');
  return { dir, dbPath, cleanup: () => fs.rmSync(dir, { recursive: true }) };
}

// ── Engine lifecycle ──────────────────────────────────────────────────────────

describe('AttentionMatrix lifecycle', () => {
  let AttentionMatrix;

  beforeAll(() => {
    AttentionMatrix = require('../core/engine');
  });

  test('init() loads config and returns engine instance', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await expect(engine.init()).resolves.toBe(engine);
    await engine.stop();
    cleanup();
  });

  test('init() throws when config file is missing', async () => {
    const engine = new AttentionMatrix('/nonexistent/path/matrix.yaml');
    await expect(engine.init()).rejects.toThrow('配置檔案不存在');
  });

  test('start() sets isRunning = true', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();

    expect(engine.isRunning).toBe(true);
    await engine.stop();
    cleanup();
  });

  test('stop() sets isRunning = false', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();
    await engine.stop();

    expect(engine.isRunning).toBe(false);
    cleanup();
  });

  test('emits started and stopped events', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();

    const events = [];
    engine.on('started', () => events.push('started'));
    engine.on('stopped', () => events.push('stopped'));

    await engine.start();
    await engine.stop();

    expect(events).toEqual(['started', 'stopped']);
    cleanup();
  });
});

// ── getStatus() ───────────────────────────────────────────────────────────────

describe('AttentionMatrix.getStatus()', () => {
  let AttentionMatrix;
  beforeAll(() => { AttentionMatrix = require('../core/engine'); });

  test('returns expected fields', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();

    const status = engine.getStatus();
    expect(status).toHaveProperty('system', 'test-matrix');
    expect(status).toHaveProperty('version', '1.0-alpha');
    expect(status).toHaveProperty('uptime');
    expect(status).toHaveProperty('memory');
    expect(status.memory).toHaveProperty('heapMb');
    expect(status.memory).toHaveProperty('rssMb');
    expect(status).toHaveProperty('circuitBreaker');
    expect(status).toHaveProperty('tasks');
    expect(Array.isArray(status.tasks)).toBe(true);

    await engine.stop();
    cleanup();
  });

  test('tasks array is empty when no tasks configured', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();

    expect(engine.getStatus().tasks).toHaveLength(0);
    await engine.stop();
    cleanup();
  });
});

// ── Hot-reload ────────────────────────────────────────────────────────────────

describe('AttentionMatrix.reload()', () => {
  let AttentionMatrix;
  beforeAll(() => { AttentionMatrix = require('../core/engine'); });

  test('reload() re-reads config without error', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();

    await expect(engine.reload()).resolves.toBeUndefined();

    await engine.stop();
    cleanup();
  });

  test('reload() emits reloaded event', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();

    const reloaded = new Promise(resolve => engine.once('reloaded', resolve));
    await engine.reload();
    await expect(reloaded).resolves.toBeUndefined();

    await engine.stop();
    cleanup();
  });
});

// ── Task management ───────────────────────────────────────────────────────────

describe('AttentionMatrix task management', () => {
  let AttentionMatrix;
  beforeAll(() => { AttentionMatrix = require('../core/engine'); });

  test('disabled tasks are not registered', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig({
      tasks: [
        {
          id: 'disabled-task', name: 'Disabled', enabled: false,
          observe: { connector: 'none', config: {}, schedule: '* * * * *' },
          orient: {}, decide: {}, act: {},
        },
      ],
    });
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();

    expect(engine.tasks.size).toBe(0);
    await engine.stop();
    cleanup();
  });

  test('removeTask() removes task from map', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();

    // Manually inject a fake task
    engine.tasks.set('fake-task', { config: { name: 'fake' }, isRunning: false });
    expect(engine.tasks.size).toBe(1);

    await engine.removeTask('fake-task');
    expect(engine.tasks.size).toBe(0);

    await engine.stop();
    cleanup();
  });
});

// ── Circuit breaker integration ───────────────────────────────────────────────

describe('AttentionMatrix circuit breaker', () => {
  let AttentionMatrix;
  beforeAll(() => { AttentionMatrix = require('../core/engine'); });

  test('getStatus().circuitBreaker is CLOSED on fresh start', async () => {
    const { dir, dbPath, cleanup } = makeTmpEnv();
    const cfg = makeMinimalConfig();
    cfg.system.database.path = dbPath;
    writeTmpConfig(dir, cfg);

    const engine = new AttentionMatrix(path.join(dir, 'matrix.yaml'));
    await engine.init();
    await engine.start();

    const { circuitBreaker } = engine.getStatus();
    expect(circuitBreaker.state).toBe('CLOSED');
    expect(circuitBreaker.failures).toBe(0);

    await engine.stop();
    cleanup();
  });
});
