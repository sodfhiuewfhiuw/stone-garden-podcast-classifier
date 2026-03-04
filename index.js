'use strict';

/**
 * Attention Matrix v1.0-alpha - Entry Point
 *
 * Usage:
 *   npm start           # Start the system
 *   node index.js       # Same as above
 *
 * Environment variables:
 *   CONFIG_PATH         - Path to matrix.yaml (default: ./config/matrix.yaml)
 *   TELEGRAM_BOT_TOKEN  - Telegram bot token
 *   TELEGRAM_CHAT_ID    - Telegram chat ID
 *   AI_API_KEY          - AI provider API key
 */

const AttentionMatrix = require('./core/engine');

async function main() {
  const matrix = new AttentionMatrix(
    process.env.CONFIG_PATH || './config/matrix.yaml'
  );

  // Graceful shutdown
  const shutdown = async (signal) => {
    matrix.logger.info(`收到信號 ${signal}，關閉中...`);
    await matrix.stop();
    process.exit(0);
  };

  process.on('SIGINT',  () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  process.on('uncaughtException', (err) => {
    matrix.logger.error('未捕獲的異常', { error: err.message, stack: err.stack });
  });

  process.on('unhandledRejection', (reason) => {
    matrix.logger.error('未處理的 Promise 拒絕', { reason: String(reason) });
  });

  try {
    await matrix.init();
    await matrix.start();

    // Print status on startup
    const status = matrix.getStatus();
    console.log('\n=== Attention Matrix 狀態 ===');
    console.log(`系統: ${status.system} v${status.version}`);
    console.log(`任務數: ${status.tasks.length}`);
    for (const t of status.tasks) {
      console.log(`  [${t.cronActive ? '✓' : '✗'}] ${t.id} (${t.schedule || 'no schedule'})`);
    }
    console.log('===========================\n');

  } catch (err) {
    console.error('系統啟動失敗:', err.message);
    process.exit(1);
  }
}

main();
