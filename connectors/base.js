'use strict';

/**
 * BaseConnector - Abstract base class for all connectors.
 *
 * Subclasses must implement:
 *   async init()           - Prepare resources (browser, HTTP client, etc.)
 *   async fetch(options)   - Return an array of items
 *   async close()          - Release resources
 *
 * Each item returned by fetch() should conform to:
 * {
 *   post_id   : string   (unique identifier for deduplication)
 *   url       : string   (canonical URL of the post/entry)
 *   username  : string   (author handle / feed name)
 *   content   : string   (main text body)
 *   timestamp : number   (Unix ms)
 *   // optional extra fields
 * }
 */

class BaseConnector {
  /**
   * @param {object} config  - Connector config from matrix.yaml connectors section
   * @param {object} logger  - Winston logger
   */
  constructor(config = {}, logger) {
    this.config = config;
    this.logger = logger || console;
    this._initialized = false;
  }

  async init() {
    throw new Error(`${this.constructor.name}.init() must be implemented`);
  }

  async fetch(options = {}) {
    throw new Error(`${this.constructor.name}.fetch() must be implemented`);
  }

  async close() {
    // Default no-op; override if cleanup is needed
    this._initialized = false;
  }

  _assertInitialized() {
    if (!this._initialized) {
      throw new Error(`${this.constructor.name} is not initialized. Call init() first.`);
    }
  }

  /**
   * Simple helper: pause for ms milliseconds.
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Random integer between min and max (inclusive).
   */
  _randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }
}

module.exports = BaseConnector;
