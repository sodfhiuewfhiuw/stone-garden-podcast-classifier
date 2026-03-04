'use strict';

/**
 * ThreadsConnector - Puppeteer-based scraper for Threads (threads.net)
 *
 * Features:
 *  - Keyword-based search via Threads web UI
 *  - Random User-Agent rotation
 *  - Request interval randomization (1-3 s between page navigations)
 *  - Retry 3 times on page load failure
 *  - Cookie injection for authenticated sessions
 *  - Follows BaseConnector interface
 */

const fs = require('fs');
const path = require('path');
const BaseConnector = require('./base');

const MAX_LOAD_RETRIES = 3;
const MIN_DELAY_MS = 1000;
const MAX_DELAY_MS = 3000;

const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) Gecko/20100101 Firefox/122.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
];

class ThreadsConnector extends BaseConnector {
  constructor(config = {}, logger) {
    super(config, logger);
    this.browser = null;
    this.page = null;
    this._userAgent = this._pickUserAgent();
  }

  _pickUserAgent() {
    return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
  }

  // ── BaseConnector interface ────────────────────────────────────────────────

  async init() {
    if (this._initialized) return;

    const puppeteer = require('puppeteer');

    this.logger.info('ThreadsConnector: 啟動瀏覽器...');
    this.browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--window-size=1280,800',
      ],
    });

    this.page = await this.browser.newPage();
    await this.page.setUserAgent(this._userAgent);
    await this.page.setViewport({ width: 1280, height: 800 });

    // Block unnecessary resources to speed up scraping
    await this.page.setRequestInterception(true);
    this.page.on('request', req => {
      const type = req.resourceType();
      if (['image', 'font', 'media', 'stylesheet'].includes(type)) {
        req.abort();
      } else {
        req.continue();
      }
    });

    // Inject cookies if provided
    const cookiesPath = this.config.cookies_path;
    if (cookiesPath) {
      const resolved = path.resolve(cookiesPath);
      if (fs.existsSync(resolved)) {
        const cookies = JSON.parse(fs.readFileSync(resolved, 'utf8'));
        await this.page.setCookie(...cookies);
        this.logger.info('ThreadsConnector: cookies 已載入');
      } else {
        this.logger.warn('ThreadsConnector: cookies 檔案不存在', { path: resolved });
      }
    }

    this._initialized = true;
    this.logger.info('ThreadsConnector: 初始化完成', { userAgent: this._userAgent });
  }

  /**
   * Fetch posts matching options.keywords from Threads search.
   *
   * @param {object} options
   * @param {string[]} options.keywords   - Keywords to search
   * @param {number}   options.max_posts  - Max posts to return per keyword
   * @returns {Promise<object[]>}         - Array of post items
   */
  async fetch(options = {}) {
    this._assertInitialized();

    const keywords = options.keywords || [];
    const maxPosts = options.max_posts || 10;
    const allItems = [];

    for (const keyword of keywords) {
      try {
        this.logger.info(`ThreadsConnector: 搜尋關鍵字 "${keyword}"`);
        const items = await this._searchKeyword(keyword, maxPosts);
        allItems.push(...items);

        // Randomized inter-keyword delay
        const delay = this._randInt(MIN_DELAY_MS, MAX_DELAY_MS);
        this.logger.debug(`ThreadsConnector: 等待 ${delay}ms`);
        await this._sleep(delay);
      } catch (err) {
        this.logger.error(`ThreadsConnector: 關鍵字搜尋失敗 "${keyword}"`, { error: err.message });
      }
    }

    return allItems;
  }

  async close() {
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
      this.page = null;
    }
    await super.close();
    this.logger.info('ThreadsConnector: 瀏覽器已關閉');
  }

  // ── Internal helpers ──────────────────────────────────────────────────────

  async _searchKeyword(keyword, maxPosts) {
    const encodedKw = encodeURIComponent(keyword);
    const url = `https://www.threads.net/search?q=${encodedKw}&serp_type=default`;

    await this._navigateWithRetry(url);
    await this._waitForContent();

    return this._extractPosts(keyword, maxPosts);
  }

  async _navigateWithRetry(url) {
    let lastErr;
    for (let attempt = 1; attempt <= MAX_LOAD_RETRIES; attempt++) {
      try {
        await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        return;
      } catch (err) {
        lastErr = err;
        this.logger.warn(`ThreadsConnector: 頁面載入失敗 (${attempt}/${MAX_LOAD_RETRIES})`, {
          url,
          error: err.message,
        });
        if (attempt < MAX_LOAD_RETRIES) {
          await this._sleep(this._randInt(MIN_DELAY_MS, MAX_DELAY_MS));
        }
      }
    }
    throw lastErr;
  }

  async _waitForContent() {
    try {
      // Threads renders via React; wait for any article or post element
      await this.page.waitForSelector('[role="article"], article, div[data-pressable-container]', {
        timeout: 10000,
      });
    } catch {
      // Page may still have content even if selector not found; continue
      this.logger.debug('ThreadsConnector: 等待元素逾時，繼續嘗試萃取');
    }
  }

  async _extractPosts(keyword, maxPosts) {
    return this.page.evaluate((kw, max) => {
      const items = [];

      // Threads uses various selectors across versions; try multiple
      const candidates = [
        ...document.querySelectorAll('[role="article"]'),
        ...document.querySelectorAll('article'),
        ...document.querySelectorAll('div[data-pressable-container="true"]'),
      ];

      // De-duplicate DOM nodes
      const seen = new Set();
      const unique = candidates.filter(el => {
        if (seen.has(el)) return false;
        seen.add(el);
        return true;
      });

      for (const el of unique.slice(0, max)) {
        try {
          // Username
          const usernameEl = el.querySelector('a[href*="/@"], [data-testid*="username"], span.username');
          const username = usernameEl
            ? (usernameEl.textContent || '').trim().replace('@', '')
            : '';

          // Content text
          const contentEl = el.querySelector('[data-testid*="post-text"], span.text, div.text, p');
          const content = contentEl ? (contentEl.textContent || '').trim() : el.innerText.trim();

          // Post URL / ID
          const linkEl = el.querySelector('a[href*="/post/"]');
          const url = linkEl ? linkEl.href : '';
          const post_id = url.match(/\/post\/([^/?]+)/)?.[1] || `${kw}-${Date.now()}-${Math.random()}`;

          // Timestamp
          const timeEl = el.querySelector('time');
          const timestamp = timeEl
            ? new Date(timeEl.getAttribute('datetime') || Date.now()).getTime()
            : Date.now();

          if (content || username) {
            items.push({ post_id, url, username, content, timestamp, keyword: kw });
          }
        } catch {
          // Skip malformed elements
        }
      }

      return items;
    }, keyword, maxPosts);
  }
}

module.exports = ThreadsConnector;
