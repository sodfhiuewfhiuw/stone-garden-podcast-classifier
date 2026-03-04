'use strict';

/**
 * Tests for core/analyzer.js
 * Covers JSON parsing edge cases and AI call handling.
 */

const Analyzer = require('../core/analyzer');

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeAnalyzer(axiosPost) {
  const logger = { info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() };
  const aiConfig = {
    default_provider: 'gemini',
    providers: {
      gemini: {
        model: 'gemini-2.5-flash',
        api_url: 'https://example.com/api',
        api_key: 'test-key',
      },
    },
  };
  const analyzer = new Analyzer(aiConfig, logger);

  // Inject mock axios via module mock pattern
  analyzer._axiosPost = axiosPost || jest.fn();
  // Patch the internal call to use _axiosPost
  // eslint-disable-next-line no-underscore-dangle
  const origAnalyze = analyzer.analyze.bind(analyzer);
  analyzer.analyze = async (item, orientCfg) => {
    // We test _parseJson directly for parse-edge cases
    return origAnalyze(item, orientCfg);
  };

  return { analyzer, logger };
}

// ── _parseJson tests ──────────────────────────────────────────────────────────

describe('Analyzer._parseJson', () => {
  const { analyzer } = makeAnalyzer();

  test('parses valid JSON string', () => {
    const result = analyzer._parseJson('{"email":"a@b.com","phone":"0912345678"}');
    expect(result).toEqual({ email: 'a@b.com', phone: '0912345678' });
  });

  test('parses JSON wrapped in markdown code fence', () => {
    const raw = '```json\n{"email":"x@y.com"}\n```';
    const result = analyzer._parseJson(raw);
    expect(result).toEqual({ email: 'x@y.com' });
  });

  test('parses JSON wrapped in plain code fence', () => {
    const raw = '```\n{"salary":"50k"}\n```';
    expect(analyzer._parseJson(raw)).toEqual({ salary: '50k' });
  });

  test('extracts first JSON object from prose', () => {
    const raw = 'Here is the result: {"email":"test@test.com"} done.';
    expect(analyzer._parseJson(raw)).toEqual({ email: 'test@test.com' });
  });

  test('returns empty object for unparseable text', () => {
    const result = analyzer._parseJson('No JSON here at all');
    expect(result).toEqual({});
  });

  test('returns empty object for empty string', () => {
    expect(analyzer._parseJson('')).toEqual({});
  });

  test('handles boolean AI fields', () => {
    const raw = '{"is_taichung":true,"is_job_posting":false}';
    const result = analyzer._parseJson(raw);
    expect(result.is_taichung).toBe(true);
    expect(result.is_job_posting).toBe(false);
  });

  test('handles nested JSON object', () => {
    const raw = '{"extracted":{"email":"nested@a.com"},"is_taichung":true}';
    const result = analyzer._parseJson(raw);
    expect(result.extracted.email).toBe('nested@a.com');
  });

  test('handles JSON array gracefully', () => {
    // Arrays are valid JSON but not expected; should not crash
    const result = analyzer._parseJson('[{"email":"e@f.com"}]');
    // It will fail JSON.parse for object match but won't throw
    expect(result).toBeDefined();
  });

  test('handles deeply escaped unicode', () => {
    const raw = '{"content":"\\u53f0\\u4e2d"}';
    const result = analyzer._parseJson(raw);
    expect(result.content).toBe('\u53f0\u4e2d');
  });
});

// ── analyze() - skips when no api_key ────────────────────────────────────────

describe('Analyzer.analyze', () => {
  test('returns empty object when api_key missing', async () => {
    const logger = { warn: jest.fn(), info: jest.fn(), debug: jest.fn(), error: jest.fn() };
    const analyzer = new Analyzer({ default_provider: 'gemini', providers: { gemini: { api_url: 'http://x', api_key: '' } } }, logger);
    const result = await analyzer.analyze({ content: 'test' }, {});
    expect(result).toEqual({});
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('未配置'));
  });

  test('returns empty object when item has no content', async () => {
    const logger = { warn: jest.fn(), info: jest.fn(), debug: jest.fn(), error: jest.fn() };
    const analyzer = new Analyzer({
      default_provider: 'gemini',
      providers: { gemini: { api_url: 'http://x', api_key: 'key' } },
    }, logger);
    const result = await analyzer.analyze({}, {});
    expect(result).toEqual({});
  });
});
