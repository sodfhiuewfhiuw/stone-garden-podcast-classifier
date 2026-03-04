'use strict';

/**
 * Core Engine - 可編程注意力系統核心
 *
 * Responsibilities:
 *  - Load and hot-reload config/matrix.yaml via chokidar
 *  - Manage connector/plugin lifecycle
 *  - Schedule and orchestrate Task runners
 *  - Expose simple statistics API
 *  - Structured logging via Winston (file + console)
 */

const EventEmitter = require('events');
const yaml = require('js-yaml');
const fs = require('fs');
const path = require('path');
const cron = require('node-cron');
const chokidar = require('chokidar');
const winston = require('winston');

const Database = require('./database');
const TaskRunner = require('./task');
const Analyzer = require('./analyzer');
const Notifier = require('./notifier');

// ── Logger factory ──────────────────────────────────────────────────────────

function createLogger(logLevel = 'info') {
  const logDir = path.resolve('./logs');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }

  return winston.createLogger({
    level: logLevel,
    format: winston.format.combine(
      winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
      winston.format.errors({ stack: true }),
      winston.format.json()
    ),
    transports: [
      new winston.transports.Console({
        format: winston.format.combine(
          winston.format.colorize(),
          winston.format.printf(({ timestamp, level, message, ...meta }) => {
            const extra = Object.keys(meta).length ? ' ' + JSON.stringify(meta) : '';
            return `[${timestamp}] ${level}: ${message}${extra}`;
          })
        ),
      }),
      new winston.transports.File({
        filename: path.join(logDir, 'error.log'),
        level: 'error',
      }),
      new winston.transports.File({
        filename: path.join(logDir, 'combined.log'),
      }),
    ],
  });
}

// ── AttentionMatrix ──────────────────────────────────────────────────────────

class AttentionMatrix extends EventEmitter {
  constructor(configPath = './config/matrix.yaml') {
    super();
    this.configPath = path.resolve(configPath);
    this.config = null;
    this.tasks = new Map();          // taskId -> TaskRunner
    this.cronJobs = new Map();       // taskId -> cron.ScheduledTask
    this.connectors = new Map();     // connectorId -> instance
    this.plugins = new Map();
    this.db = null;
    this.notifier = null;
    this.analyzer = null;
    this.logger = createLogger();    // default level; updated after config load
    this.isRunning = false;
    this._watcher = null;
    this._healthTimer = null;
  }

  // ── Initialization ────────────────────────────────────────────────────────

  async init() {
    this.logger.info('Attention Matrix 初始化中...');
    await this.loadConfig();

    // Recreate logger with configured level
    this.logger = createLogger(this.config.system.log_level || 'info');

    await this.initDatabase();
    this.analyzer = new Analyzer(this.config.system.ai, this.logger);
    this.notifier = new Notifier(this.config.system.notifications, this.db, this.logger);
    await this.loadConnectors();
    await this.loadPlugins();
    await this.registerTasks();
    this.watchConfig();
    this.logger.info('系統初始化完成', {
      name: this.config.system.name,
      version: this.config.version,
      tasks: this.tasks.size,
    });
    return this;
  }

  async loadConfig() {
    if (!fs.existsSync(this.configPath)) {
      throw new Error(`配置檔案不存在: ${this.configPath}`);
    }
    const content = fs.readFileSync(this.configPath, 'utf8');
    this.config = yaml.load(content);
    this.config = this.replaceEnvVars(this.config);
    this.logger.info(`配置載入完成: ${this.config.system.name} v${this.config.version}`);
  }

  replaceEnvVars(obj) {
    if (typeof obj === 'string') {
      return obj.replace(/\$\{(\w+)\}/g, (_, key) => process.env[key] || '');
    }
    if (Array.isArray(obj)) {
      return obj.map(item => this.replaceEnvVars(item));
    }
    if (obj && typeof obj === 'object') {
      const out = {};
      for (const [k, v] of Object.entries(obj)) {
        out[k] = this.replaceEnvVars(v);
      }
      return out;
    }
    return obj;
  }

  async initDatabase() {
    const dbPath = this.config.system.database.path;
    this.db = new Database(dbPath).init();
    this.logger.info('資料庫初始化完成', { path: dbPath });
  }

  async loadConnectors() {
    if (!this.config.connectors) return;
    for (const [id, cfg] of Object.entries(this.config.connectors)) {
      try {
        const ConnectorClass = require(path.resolve(cfg.module));
        const instance = new ConnectorClass(cfg, this.logger);
        this.connectors.set(id, instance);
        this.logger.info(`連接器載入: ${id}`, { type: cfg.type });
      } catch (err) {
        this.logger.error(`連接器載入失敗: ${id}`, { error: err.message });
      }
    }
  }

  async loadPlugins() {
    if (!this.config.plugins) return;
    for (const [id, cfg] of Object.entries(this.config.plugins)) {
      try {
        const PluginClass = require(path.resolve(cfg.module));
        const instance = new PluginClass(cfg, this.logger);
        this.plugins.set(id, instance);
        this.logger.info(`插件載入: ${id}`);
      } catch (err) {
        this.logger.error(`插件載入失敗: ${id}`, { error: err.message });
      }
    }
  }

  // ── Task management (supports runtime add/modify/delete) ──────────────────

  async registerTasks() {
    if (!this.config.tasks) return;
    for (const taskCfg of this.config.tasks) {
      await this.addTask(taskCfg);
    }
  }

  /**
   * Add or update a task at runtime without restarting.
   */
  async addTask(taskCfg) {
    if (!taskCfg.enabled) {
      this.logger.info(`任務已停用，跳過: ${taskCfg.id}`);
      return;
    }

    // If the task already exists, remove it first
    if (this.tasks.has(taskCfg.id)) {
      await this.removeTask(taskCfg.id);
    }

    const connectorId = taskCfg.observe.connector;
    const connector = this.connectors.get(connectorId);
    if (!connector) {
      this.logger.warn(`連接器未找到，任務跳過: ${taskCfg.id}`, { connector: connectorId });
      return;
    }

    const runner = new TaskRunner({
      config: taskCfg,
      connector,
      analyzer: this.analyzer,
      notifier: this.notifier,
      db: this.db,
      logger: this.logger,
    });

    this.tasks.set(taskCfg.id, runner);

    const schedule = taskCfg.observe.schedule;
    if (schedule && cron.validate(schedule)) {
      const job = cron.schedule(schedule, () => runner.run(), { timezone: this.config.system.timezone });
      this.cronJobs.set(taskCfg.id, job);
      this.logger.info(`任務已排程: ${taskCfg.id}`, { schedule });
    } else {
      this.logger.warn(`任務排程無效，不自動執行: ${taskCfg.id}`, { schedule });
    }

    this.emit('taskAdded', taskCfg.id);
  }

  /**
   * Remove a task at runtime.
   */
  async removeTask(taskId) {
    const job = this.cronJobs.get(taskId);
    if (job) {
      job.stop();
      this.cronJobs.delete(taskId);
    }
    this.tasks.delete(taskId);
    this.logger.info(`任務已移除: ${taskId}`);
    this.emit('taskRemoved', taskId);
  }

  /**
   * Immediately run a task by ID.
   */
  async runTask(taskId) {
    const runner = this.tasks.get(taskId);
    if (!runner) throw new Error(`任務不存在: ${taskId}`);
    return runner.run();
  }

  // ── Hot-reload config ────────────────────────────────────────────────────

  watchConfig() {
    if (this._watcher) return;

    this._watcher = chokidar.watch(this.configPath, {
      persistent: true,
      awaitWriteFinish: { stabilityThreshold: 500, pollInterval: 100 },
    });

    this._watcher.on('change', async () => {
      this.logger.info('配置檔案變更，熱重載中...');
      try {
        await this.reload();
      } catch (err) {
        this.logger.error('熱重載失敗', { error: err.message });
      }
    });
  }

  async reload() {
    const previousTaskIds = new Set(this.tasks.keys());

    await this.loadConfig();
    this.logger = createLogger(this.config.system.log_level || 'info');

    // Reload connectors (simple approach: replace all)
    this.connectors.clear();
    await this.loadConnectors();

    // Determine new task IDs
    const newTaskConfigs = (this.config.tasks || []).filter(t => t.enabled);
    const newTaskIds = new Set(newTaskConfigs.map(t => t.id));

    // Remove tasks no longer in config
    for (const id of previousTaskIds) {
      if (!newTaskIds.has(id)) {
        await this.removeTask(id);
      }
    }

    // Add / update tasks
    for (const taskCfg of newTaskConfigs) {
      await this.addTask(taskCfg);
    }

    this.logger.info('熱重載完成', { tasks: this.tasks.size });
    this.emit('reloaded');
  }

  // ── Statistics API ────────────────────────────────────────────────────────

  getStatus() {
    const tasks = [];
    for (const [id, runner] of this.tasks.entries()) {
      const job = this.cronJobs.get(id);
      tasks.push({
        id,
        name: runner.config.name,
        schedule: runner.config.observe.schedule,
        isRunning: runner.isRunning,
        cronActive: !!job,
        stats: this.db.getStats(id),
      });
    }
    const mem = process.memoryUsage();
    return {
      system:  this.config.system.name,
      version: this.config.version,
      uptime:  process.uptime(),
      memory:  { heapMb: Math.round(mem.heapUsed / 1024 / 1024), rssMb: Math.round(mem.rss / 1024 / 1024) },
      circuitBreaker: this.analyzer ? this.analyzer.getCircuitState() : null,
      tasks,
    };
  }

  getTaskStats(taskId) {
    return this.db.getStats(taskId);
  }

  getAllStats() {
    return this.db.getAllStats();
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  async start() {
    this.isRunning = true;
    this._startHealthMonitor();
    this.logger.info('系統已啟動');
    this.emit('started');
  }

  async stop() {
    this.isRunning = false;
    this._stopHealthMonitor();
    for (const [id, job] of this.cronJobs.entries()) {
      job.stop();
      this.logger.info(`排程停止: ${id}`);
    }
    if (this._watcher) {
      await this._watcher.close();
      this._watcher = null;
    }
    if (this.db) this.db.close();
    this.logger.info('系統已停止');
    this.emit('stopped');
  }

  // ── Health monitoring ──────────────────────────────────────────────────────

  _startHealthMonitor() {
    const intervalMs = (this.config.system.health?.check_interval_s || 60) * 1000;
    const heapWarnMb =  this.config.system.health?.heap_warn_mb || 512;

    this._healthTimer = setInterval(() => {
      const mem    = process.memoryUsage();
      const heapMb = Math.round(mem.heapUsed / 1024 / 1024);
      const rssMb  = Math.round(mem.rss      / 1024 / 1024);

      this.logger.info('健康檢查', { heapMb, rssMb, uptime: Math.round(process.uptime()) });

      if (heapMb > heapWarnMb) {
        this.logger.warn('記憶體使用過高', { heapMb, threshold: heapWarnMb });
      }

      // Also log circuit breaker state if analyzer exists
      if (this.analyzer) {
        const cbState = this.analyzer.getCircuitState();
        if (cbState.state !== 'CLOSED') {
          this.logger.warn('AI 斷路器非正常狀態', cbState);
        }
      }
    }, intervalMs);

    this.logger.info('健康監控已啟動', { intervalMs, heapWarnMb });
  }

  _stopHealthMonitor() {
    if (this._healthTimer) {
      clearInterval(this._healthTimer);
      this._healthTimer = null;
    }
  }
}

module.exports = AttentionMatrix;
