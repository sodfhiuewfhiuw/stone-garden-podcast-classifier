'use strict';

/**
 * Notifier - Act layer
 * Currently supports Telegram. Designed for easy extension to other channels.
 */

const TelegramBot = require('node-telegram-bot-api');

function formatMessage(taskConfig, item) {
  const name = taskConfig.name || taskConfig.id;
  const lines = [
    `*[${name}]* 新發現 🔔`,
    '',
  ];

  if (item.username) lines.push(`👤 @${item.username}`);
  if (item.content) lines.push(`📝 ${item.content.substring(0, 300)}`);
  if (item.email)   lines.push(`📧 ${item.email}`);
  if (item.phone)   lines.push(`📞 ${item.phone}`);
  if (item.salary)  lines.push(`💰 ${item.salary}`);
  if (item.url)     lines.push(`🔗 ${item.url}`);
  if (item._score !== undefined) lines.push(`⭐ 分數: ${item._score}`);

  return lines.join('\n');
}

class Notifier {
  /**
   * @param {object} notifConfig - system.notifications from matrix.yaml
   * @param {object} db          - Database instance
   * @param {object} logger      - Winston logger
   */
  constructor(notifConfig = {}, db, logger) {
    this.config = notifConfig;
    this.db = db;
    this.logger = logger;
    this._bots = new Map();
  }

  _getBot(channelName) {
    if (this._bots.has(channelName)) return this._bots.get(channelName);

    const channelCfg = this.config?.channels?.[channelName];
    if (!channelCfg || !channelCfg.enabled) {
      throw new Error(`通知頻道未啟用: ${channelName}`);
    }
    if (!channelCfg.bot_token) {
      throw new Error(`Telegram bot_token 未設定`);
    }

    const bot = new TelegramBot(channelCfg.bot_token, { polling: false });
    this._bots.set(channelName, { bot, chatId: channelCfg.chat_id });
    return { bot, chatId: channelCfg.chat_id };
  }

  /**
   * Send a notification for one item.
   *
   * @param {object} taskConfig - Task config (for name / channel override)
   * @param {object} item       - Enriched item to notify about
   */
  async send(taskConfig, item) {
    const channelName = taskConfig?.act?.channel || this.config?.default_channel || 'telegram';
    const { bot, chatId } = this._getBot(channelName);

    if (!chatId) {
      throw new Error(`Telegram chat_id 未設定`);
    }

    const text = formatMessage(taskConfig, item);
    this.logger.debug('發送通知', { channel: channelName, chatId });

    await bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    this.logger.info('通知已發送', { taskId: taskConfig.id, channel: channelName });
  }
}

module.exports = Notifier;
