'use strict';

/**
 * CircuitBreaker - 斷路器
 *
 * 三種狀態：
 *   CLOSED   - 正常運行，呼叫直接執行
 *   OPEN     - 已斷開，直接拒絕呼叫，等待冷卻後進入 HALF_OPEN
 *   HALF_OPEN - 試探性恢復，成功則回到 CLOSED，失敗則重新 OPEN
 *
 * Usage:
 *   const cb = new CircuitBreaker({ name: 'ai-api', failureThreshold: 5, resetTimeoutMs: 60000, logger });
 *   const result = await cb.call(() => axios.post(...));
 */

const STATES = Object.freeze({ CLOSED: 'CLOSED', OPEN: 'OPEN', HALF_OPEN: 'HALF_OPEN' });

class CircuitBreaker {
  /**
   * @param {object} opts
   * @param {string}  opts.name              - 識別名稱（用於日誌）
   * @param {number}  opts.failureThreshold  - 連續失敗幾次後開啟斷路器（預設 5）
   * @param {number}  opts.resetTimeoutMs    - 斷開後冷卻多久才嘗試恢復，毫秒（預設 60000）
   * @param {object}  opts.logger            - Winston-compatible logger
   */
  constructor({ name = 'cb', failureThreshold = 5, resetTimeoutMs = 60000, logger } = {}) {
    this.name = name;
    this.failureThreshold = failureThreshold;
    this.resetTimeoutMs = resetTimeoutMs;
    this.logger = logger || console;

    this._state = STATES.CLOSED;
    this._failures = 0;
    this._openedAt = null;
  }

  get state() { return this._state; }

  /**
   * Execute fn through the circuit breaker.
   * Throws immediately if state is OPEN and cooldown hasn't passed.
   *
   * @param {Function} fn - Async function to call
   * @returns {Promise<*>} Result of fn()
   */
  async call(fn) {
    if (this._state === STATES.OPEN) {
      const elapsed = Date.now() - this._openedAt;
      if (elapsed < this.resetTimeoutMs) {
        const remaining = Math.round((this.resetTimeoutMs - elapsed) / 1000);
        throw new Error(`[CB:${this.name}] 斷路器已開啟，冷卻剩餘 ${remaining}s`);
      }
      // Cooldown passed — try recovery
      this._state = STATES.HALF_OPEN;
      this.logger.info(`[CB:${this.name}] 進入 HALF_OPEN，嘗試恢復`);
    }

    try {
      const result = await fn();
      this._onSuccess();
      return result;
    } catch (err) {
      this._onFailure();
      throw err;
    }
  }

  _onSuccess() {
    if (this._state === STATES.HALF_OPEN) {
      this.logger.info(`[CB:${this.name}] 恢復成功，切換為 CLOSED`);
    }
    this._state = STATES.CLOSED;
    this._failures = 0;
    this._openedAt = null;
  }

  _onFailure() {
    this._failures++;
    if (this._state === STATES.HALF_OPEN || this._failures >= this.failureThreshold) {
      this._state = STATES.OPEN;
      this._openedAt = Date.now();
      this.logger.warn(
        `[CB:${this.name}] 斷路器開啟（連續失敗 ${this._failures} 次）`,
        { failureThreshold: this.failureThreshold, resetTimeoutMs: this.resetTimeoutMs }
      );
    }
  }

  /**
   * Force-reset to CLOSED (useful for testing or admin override).
   */
  reset() {
    this._state = STATES.CLOSED;
    this._failures = 0;
    this._openedAt = null;
    this.logger.info(`[CB:${this.name}] 手動重置`);
  }

  /**
   * Return a plain-object snapshot of current state (for status API).
   */
  getState() {
    return {
      name: this.name,
      state: this._state,
      failures: this._failures,
      openedAt: this._openedAt,
    };
  }
}

module.exports = CircuitBreaker;
