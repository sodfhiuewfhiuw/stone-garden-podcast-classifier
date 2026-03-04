'use strict';

/**
 * scripts/resend.js  →  node scripts/resend.js [taskId]
 *
 * Manually re-send all pending failed notifications.
 * Optionally filter by taskId.
 */

const yaml = require('js-yaml');
const fs = require('fs');
const path = require('path');
const Database = require('../core/database');
const Notifier = require('../core/notifier');
const TaskRunner = require('../core/task');
const winston = require('winston');

function makeLogger() {
  return winston.createLogger({
    level: 'info',
    format: winston.format.combine(winston.format.timestamp(), winston.format.simple()),
    transports: [new winston.transports.Console()],
  });
}

function replaceEnvVars(obj) {
  if (typeof obj === 'string') return obj.replace(/\$\{(\w+)\}/g, (_, k) => process.env[k] || '');
  if (Array.isArray(obj)) return obj.map(replaceEnvVars);
  if (obj && typeof obj === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(obj)) out[k] = replaceEnvVars(v);
    return out;
  }
  return obj;
}

async function main() {
  const filterTaskId = process.argv[2];
  const configPath = path.resolve(process.env.CONFIG_PATH || './config/matrix.yaml');
  const raw = yaml.load(fs.readFileSync(configPath, 'utf8'));
  const config = replaceEnvVars(raw);

  const logger = makeLogger();
  const db = new Database(config.system.database.path).init();
  const notifier = new Notifier(config.system.notifications, db, logger);

  let pending = db.getPendingNotifications();
  if (filterTaskId) {
    pending = pending.filter(n => n.task_id === filterTaskId);
  }

  if (pending.length === 0) {
    console.log('No pending notifications.');
    db.close();
    return;
  }

  console.log(`Re-sending ${pending.length} pending notification(s)...`);

  // Build a minimal task config map for lookup
  const taskMap = {};
  for (const tc of (config.tasks || [])) {
    taskMap[tc.id] = tc;
  }

  let resent = 0;
  for (const row of pending) {
    const taskConfig = taskMap[row.task_id] || { id: row.task_id, name: row.task_id, act: {} };
    let payload;
    try {
      payload = JSON.parse(row.payload);
    } catch {
      logger.error(`Cannot parse payload for notification #${row.id}`);
      continue;
    }
    try {
      await notifier.send(taskConfig, payload);
      db.markNotificationSent(row.id);
      resent++;
      logger.info(`Resent #${row.id}`);
    } catch (err) {
      db.updateNotificationAttempt(row.id, err.message);
      logger.warn(`Failed to resend #${row.id}: ${err.message}`);
    }
  }

  console.log(`Done. Resent ${resent}/${pending.length}.`);
  db.close();
}

main().catch(err => {
  console.error('Resend error:', err.message);
  process.exit(1);
});
