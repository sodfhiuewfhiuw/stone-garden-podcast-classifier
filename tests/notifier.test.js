'use strict';

/**
 * Tests for core/notifier.js
 * Uses mock Telegram bot to avoid real network calls.
 */

const Notifier = require('../core/notifier');

// ── Mock Telegram bot factory ─────────────────────────────────────────────────

function makeBot(sendMessageImpl) {
  return {
    sendMessage: sendMessageImpl || jest.fn().mockResolvedValue({ message_id: 1 }),
  };
}

function makeNotifier({ sendMessage, enabled = true, bot_token = 'tok', chat_id = '123' } = {}) {
  const logger = { info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() };
  const notifConfig = {
    default_channel: 'telegram',
    channels: {
      telegram: { enabled, bot_token, chat_id },
    },
  };
  const db = {};
  const notifier = new Notifier(notifConfig, db, logger);

  // Inject mock bot into _bots map
  const mockBot = makeBot(sendMessage);
  notifier._bots.set('telegram', { bot: mockBot, chatId: chat_id });

  return { notifier, logger, mockBot };
}

const dummyTask = {
  id: 'test-task',
  name: '測試任務',
  act: {},
};

const dummyItem = {
  username: 'user123',
  content: '台中誠徵工程師，薪資面議',
  email: 'hr@company.com',
  phone: '0912345678',
  salary: '50k',
  url: 'https://threads.net/post/abc',
  _score: 45,
};

// ── send() ────────────────────────────────────────────────────────────────────

describe('Notifier.send', () => {
  test('calls bot.sendMessage with Markdown', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, dummyItem);
    expect(mockBot.sendMessage).toHaveBeenCalledTimes(1);
    const [chatId, text, opts] = mockBot.sendMessage.mock.calls[0];
    expect(chatId).toBe('123');
    expect(text).toContain('測試任務');
    expect(opts.parse_mode).toBe('Markdown');
  });

  test('message includes username', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, dummyItem);
    const text = mockBot.sendMessage.mock.calls[0][1];
    expect(text).toContain('user123');
  });

  test('message includes email', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, dummyItem);
    const text = mockBot.sendMessage.mock.calls[0][1];
    expect(text).toContain('hr@company.com');
  });

  test('message includes phone', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, dummyItem);
    const text = mockBot.sendMessage.mock.calls[0][1];
    expect(text).toContain('0912345678');
  });

  test('message includes score', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, dummyItem);
    const text = mockBot.sendMessage.mock.calls[0][1];
    expect(text).toContain('45');
  });

  test('throws when channel is disabled', async () => {
    const logger = { info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() };
    const notifier = new Notifier({
      default_channel: 'telegram',
      channels: { telegram: { enabled: false, bot_token: 'x', chat_id: '1' } },
    }, {}, logger);
    await expect(notifier.send(dummyTask, dummyItem)).rejects.toThrow('未啟用');
  });

  test('throws when bot_token is missing', async () => {
    const logger = { info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() };
    const notifier = new Notifier({
      default_channel: 'telegram',
      channels: { telegram: { enabled: true, bot_token: '', chat_id: '1' } },
    }, {}, logger);
    await expect(notifier.send(dummyTask, dummyItem)).rejects.toThrow('bot_token');
  });

  test('throws when chat_id is missing', async () => {
    const { notifier } = makeNotifier({ chat_id: '' });
    await expect(notifier.send(dummyTask, dummyItem)).rejects.toThrow('chat_id');
  });

  test('propagates bot.sendMessage error', async () => {
    const { notifier } = makeNotifier({
      sendMessage: jest.fn().mockRejectedValue(new Error('Network error')),
    });
    await expect(notifier.send(dummyTask, dummyItem)).rejects.toThrow('Network error');
  });

  test('works with minimal item (no optional fields)', async () => {
    const { notifier, mockBot } = makeNotifier();
    await notifier.send(dummyTask, { content: 'minimal content' });
    expect(mockBot.sendMessage).toHaveBeenCalledTimes(1);
  });

  test('truncates long content to 300 chars', async () => {
    const { notifier, mockBot } = makeNotifier();
    const longItem = { ...dummyItem, content: 'x'.repeat(500) };
    await notifier.send(dummyTask, longItem);
    const text = mockBot.sendMessage.mock.calls[0][1];
    // The content section should not exceed 300 chars of 'x'
    const match = text.match(/x+/);
    expect(match[0].length).toBeLessThanOrEqual(300);
  });
});
