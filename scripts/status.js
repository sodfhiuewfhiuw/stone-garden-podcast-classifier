'use strict';

/**
 * scripts/status.js  →  npm run status
 *
 * Reads the SQLite database and prints a detailed status report.
 * Can be run while the engine is running (WAL mode allows concurrent reads).
 */

const path = require('path');
const yaml = require('js-yaml');
const fs = require('fs');
const Database = require('../core/database');

function loadConfig() {
  const configPath = path.resolve(process.env.CONFIG_PATH || './config/matrix.yaml');
  const content = fs.readFileSync(configPath, 'utf8');
  return yaml.load(content);
}

function formatDuration(ms) {
  if (!ms) return 'N/A';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

async function main() {
  const config = loadConfig();
  const db = new Database(config.system.database.path).init();

  console.log(`\n=== Attention Matrix Status ===`);
  console.log(`System : ${config.system.name} v${config.version}`);
  console.log(`DB     : ${config.system.database.path}`);
  console.log(`Time   : ${new Date().toLocaleString('zh-TW', { timeZone: config.system.timezone })}\n`);

  const allStats = db.getAllStats();

  if (allStats.length === 0) {
    console.log('No task runs recorded yet.\n');
  } else {
    for (const s of allStats) {
      console.log(`Task: ${s.taskId}`);
      console.log(`  Total runs   : ${s.totalRuns}`);
      console.log(`  Success rate : ${s.successRate}`);
      console.log(`  Avg duration : ${formatDuration(s.avgDurationMs)}`);
      console.log(`  Items found  : ${s.totalItemsFound}`);
      console.log(`  Items sent   : ${s.totalItemsSent}`);

      const recent = db.getRecentRuns(s.taskId, 5);
      if (recent.length > 0) {
        console.log('  Recent runs:');
        for (const r of recent) {
          const start = new Date(r.started_at).toLocaleString('zh-TW');
          const dur   = r.finished_at ? formatDuration(r.finished_at - r.started_at) : 'running';
          const err   = r.error ? ` ✗ ${r.error.substring(0, 60)}` : '';
          console.log(`    [${r.status}] ${start} (${dur})${err}`);
        }
      }
      console.log('');
    }
  }

  // Pending notifications
  const pending = db.getPendingNotifications();
  if (pending.length > 0) {
    console.log(`Pending notifications: ${pending.length}`);
    for (const n of pending) {
      console.log(`  #${n.id} task=${n.task_id} attempts=${n.attempts} error=${n.last_error || 'none'}`);
    }
    console.log('');
  }

  db.close();
}

main().catch(err => {
  console.error('Status error:', err.message);
  process.exit(1);
});
