'use strict';

/**
 * Analyzer - Orient layer
 * Calls an AI provider (Gemini/OpenAI-compatible) to extract structured data
 * from raw scraped content and apply filter rules.
 *
 * Resilience:
 *  - CircuitBreaker wraps every AI call (OPEN after 5 consecutive failures)
 *  - When CB is OPEN, automatically falls back to regex-based extraction
 */

const axios = require('axios');
const CircuitBreaker = require('./circuit-breaker');

const DEFAULT_PROMPT = `
你是一個資料萃取助理。請從下列文章內容中提取結構化資料，
並以 JSON 格式回應（只回應 JSON，不要加任何說明）。

要提取的欄位：
{fields}

同時請判斷：
- is_taichung: 是否與台中相關（布林值）
- is_job_posting: 是否為徵才/招聘貼文（布林值）

文章內容：
{content}
`.trim();

// ── Fallback: regex-based field extraction ───────────────────────────────────

const EMAIL_RE   = /[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/;
const PHONE_RE   = /(?:09\d{8}|0\d[-\s]?\d{7,8}|\+886\s?\d{9,10})/;
const SALARY_RE  = /(\d[\d,]*)\s*[kK元萬\/月年]/;

function regexExtract(text) {
  const emailMatch  = text.match(EMAIL_RE);
  const phoneMatch  = text.match(PHONE_RE);
  const salaryMatch = text.match(SALARY_RE);
  return {
    email:  emailMatch  ? emailMatch[0]  : null,
    phone:  phoneMatch  ? phoneMatch[0]  : null,
    salary: salaryMatch ? salaryMatch[0] : null,
  };
}

// ── Analyzer ─────────────────────────────────────────────────────────────────

class Analyzer {
  /**
   * @param {object} aiConfig  - system.ai from matrix.yaml
   * @param {object} logger    - Winston logger
   */
  constructor(aiConfig = {}, logger) {
    this.aiConfig = aiConfig;
    this.logger = logger;
    this._getProvider = () => {
      const providerName = aiConfig.default_provider || 'gemini';
      return (aiConfig.providers || {})[providerName] || {};
    };

    // One circuit breaker per analyzer instance (covers all AI calls)
    const cbCfg = aiConfig.circuit_breaker || {};
    this._cb = new CircuitBreaker({
      name: `ai-${aiConfig.default_provider || 'gemini'}`,
      failureThreshold: cbCfg.failure_threshold || 5,
      resetTimeoutMs:   (cbCfg.reset_timeout_s || 60) * 1000,
      logger,
    });
  }

  /**
   * Analyze a single item and return enriched fields.
   * Falls back to regex extraction when AI is unavailable or CB is open.
   *
   * @param {object} item       - Raw item from connector
   * @param {object} orientCfg  - orient section from task config
   * @returns {Promise<object>} Merged fields from AI (or regex fallback)
   */
  async analyze(item, orientCfg = {}) {
    const provider = this._getProvider();
    if (!provider.api_key || !provider.api_url) {
      this.logger.warn('AI 提供商未配置，跳過分析');
      return {};
    }

    const fields  = (orientCfg.extract_fields || []).join(', ');
    const content = [item.content, item.caption, item.text].filter(Boolean).join('\n').substring(0, 3000);

    if (!content) return {};

    const prompt = DEFAULT_PROMPT
      .replace('{fields}', fields || 'email, phone, salary')
      .replace('{content}', content);

    const body = {
      model:       provider.model || 'gemini-2.5-flash',
      messages:    [{ role: 'user', content: prompt }],
      temperature: 0.1,
      max_tokens:  512,
    };

    this.logger.debug('呼叫 AI 分析', { model: body.model, taskItem: item.post_id });

    try {
      const response = await this._cb.call(() =>
        axios.post(provider.api_url, body, {
          headers: {
            Authorization: `Bearer ${provider.api_key}`,
            'Content-Type': 'application/json',
          },
          timeout: 30000,
        })
      );

      const text = response.data?.choices?.[0]?.message?.content || '';
      return this._parseJson(text);

    } catch (err) {
      // CB open or network failure — fall back to regex
      this.logger.warn('AI 分析失敗，改用正則兜底', { reason: err.message });
      return regexExtract(content);
    }
  }

  _parseJson(text) {
    // Strip markdown code fences if present
    const cleaned = text.replace(/```(?:json)?\n?/g, '').replace(/```/g, '').trim();
    try {
      return JSON.parse(cleaned);
    } catch {
      // Try to find the first {...} block
      const match = cleaned.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          return JSON.parse(match[0]);
        } catch {
          // fall through
        }
      }
      this.logger.warn('AI 回應解析失敗', { raw: text.substring(0, 200) });
      return {};
    }
  }

  /**
   * Expose circuit breaker state for status API.
   */
  getCircuitState() {
    return this._cb.getState();
  }
}

module.exports = Analyzer;
