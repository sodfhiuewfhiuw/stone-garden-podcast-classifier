'use strict';

/**
 * RssConnector - RSS/Atom feed polling connector (Task 5)
 *
 * Configuration template in matrix.yaml:
 *
 *   connectors:
 *     rss:
 *       name: "RSS 訂閱源"
 *       type: "polling"
 *       module: "connectors/rss"
 *       status: "ready"
 *
 *   tasks:
 *     - id: "my-rss-task"
 *       observe:
 *         connector: "rss"
 *         config:
 *           feeds:
 *             - url: "https://example.com/feed.xml"
 *               label: "範例網站"
 *             - url: "https://hn.algolia.com/api/v1/search_by_date?tags=story"
 *               label: "Hacker News"
 *               format: "json"      # optional: "xml" (default) or "json"
 *           keywords: ["台中", "工作"]   # optional keyword filter
 *           max_items: 20
 *         schedule: "*/30 * * * *"
 *
 * Usage:
 *   const connector = new RssConnector(config, logger);
 *   await connector.init();
 *   const items = await connector.fetch({
 *     feeds: [{ url: 'https://example.com/feed.xml', label: 'Example' }],
 *     max_items: 10,
 *   });
 *   await connector.close();
 */

const axios = require('axios');
const BaseConnector = require('./base');

// Minimal XML parser for RSS/Atom without external deps
function parseXmlFeed(xml) {
  const items = [];

  // Support both <item> (RSS) and <entry> (Atom)
  const itemRegex = /<(?:item|entry)[^>]*>([\s\S]*?)<\/(?:item|entry)>/gi;
  let match;

  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];

    const title   = extractTag(block, 'title');
    const link    = extractTag(block, 'link') || extractAttr(block, 'link', 'href');
    const summary = extractTag(block, 'summary') || extractTag(block, 'description') || '';
    const content = extractTag(block, 'content') || summary;
    const pubDate = extractTag(block, 'pubDate') || extractTag(block, 'published') || extractTag(block, 'updated');
    const id      = extractTag(block, 'id') || extractTag(block, 'guid') || link;

    const timestamp = pubDate ? new Date(pubDate).getTime() : Date.now();

    items.push({
      post_id:   id   || `rss-${Date.now()}-${Math.random()}`,
      url:       link  || '',
      username:  '',
      content:   stripHtml(`${title ? title + '\n' : ''}${content}`).trim(),
      title,
      timestamp,
    });
  }

  return items;
}

function extractTag(str, tag) {
  const m = str.match(new RegExp(`<${tag}(?:[^>]*)><!\\[CDATA\\[([\\s\\S]*?)\\]\\]></${tag}>`, 'i'))
    || str.match(new RegExp(`<${tag}(?:[^>]*)>([\\s\\S]*?)</${tag}>`, 'i'));
  return m ? m[1].trim() : null;
}

function extractAttr(str, tag, attr) {
  const m = str.match(new RegExp(`<${tag}[^>]*${attr}="([^"]*)"`, 'i'));
  return m ? m[1].trim() : null;
}

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

// Minimal JSON feed parser (Algolia / JSON Feed spec)
function parseJsonFeed(data) {
  const arr = data.hits || data.items || (Array.isArray(data) ? data : []);
  return arr.map(entry => {
    const content = [entry.title, entry.story_text, entry.comment_text, entry.description]
      .filter(Boolean).join('\n');
    return {
      post_id:   String(entry.objectID || entry.id || Math.random()),
      url:       entry.url || entry.story_url || entry.link || '',
      username:  entry.author || entry.by || '',
      content:   stripHtml(content).trim(),
      title:     entry.title || '',
      timestamp: entry.created_at
        ? new Date(entry.created_at).getTime()
        : (entry.date_published ? new Date(entry.date_published).getTime() : Date.now()),
    };
  });
}

class RssConnector extends BaseConnector {
  constructor(config = {}, logger) {
    super(config, logger);
    this._client = null;
  }

  async init() {
    if (this._initialized) return;
    this._client = axios.create({ timeout: 15000 });
    this._initialized = true;
    this.logger.info('RssConnector: 初始化完成');
  }

  /**
   * Fetch items from one or more RSS/Atom/JSON feeds.
   *
   * @param {object}   options
   * @param {object[]} options.feeds      - Array of { url, label, format? }
   * @param {string[]} [options.keywords] - Optional keyword whitelist
   * @param {number}   [options.max_items]
   * @returns {Promise<object[]>}
   */
  async fetch(options = {}) {
    this._assertInitialized();

    const feeds    = options.feeds || [];
    const keywords = (options.keywords || []).map(k => k.toLowerCase());
    const maxItems = options.max_items || 20;
    const all      = [];

    for (const feed of feeds) {
      try {
        this.logger.info(`RssConnector: 抓取 "${feed.label || feed.url}"`);
        const items = await this._fetchFeed(feed);
        all.push(...items);

        // Polite delay between feeds
        await this._sleep(this._randInt(500, 1500));
      } catch (err) {
        this.logger.error(`RssConnector: 抓取失敗 "${feed.url}"`, { error: err.message });
      }
    }

    // Keyword filter
    const filtered = keywords.length
      ? all.filter(item =>
          keywords.some(kw => (item.content || '').toLowerCase().includes(kw))
        )
      : all;

    // Sort by timestamp descending and cap
    filtered.sort((a, b) => b.timestamp - a.timestamp);
    return filtered.slice(0, maxItems);
  }

  async _fetchFeed({ url, format }) {
    const resp = await this._client.get(url, {
      headers: { Accept: 'application/rss+xml, application/atom+xml, application/json, text/xml, */*' },
    });

    const contentType = (resp.headers['content-type'] || '').toLowerCase();
    const isJson = format === 'json'
      || contentType.includes('json')
      || typeof resp.data === 'object';

    if (isJson) {
      const data = typeof resp.data === 'string' ? JSON.parse(resp.data) : resp.data;
      return parseJsonFeed(data);
    }
    return parseXmlFeed(typeof resp.data === 'string' ? resp.data : String(resp.data));
  }

  async close() {
    this._client = null;
    await super.close();
    this.logger.info('RssConnector: 已關閉');
  }
}

module.exports = RssConnector;
