/**
 * test-yourator-api.js
 * Explore and validate the Yourator public API.
 * Run: node test-yourator-api.js [keyword]
 *
 * Examples:
 *   node test-yourator-api.js
 *   node test-yourator-api.js "software engineer"
 *   node test-yourator-api.js "backend"
 */

const https = require('https');

const BASE_URL = 'https://www.yourator.co/api/v4/jobs';
const keyword = process.argv[2] || 'engineer';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { Accept: 'application/json', 'User-Agent': 'JobHunterTest/1.0' } }, (res) => {
      let raw = '';
      res.on('data', (c) => { raw += c; });
      res.on('end', () => {
        console.log(`  HTTP ${res.statusCode} — ${url}`);
        try {
          resolve({ status: res.statusCode, data: JSON.parse(raw), raw });
        } catch {
          resolve({ status: res.statusCode, data: null, raw });
        }
      });
    }).on('error', reject);
  });
}

function section(title) {
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`  ${title}`);
  console.log('─'.repeat(60));
}

function printJobSample(job, index) {
  console.log(`\n  [${index + 1}] ${job.title || '(no title)'}`);
  console.log(`      Company : ${job.company?.brand_name || job.company?.name || '—'}`);
  console.log(`      Location: ${job.location || job.address || '—'}`);
  console.log(`      Salary  : ${job.salary_min || '—'} ~ ${job.salary_max || '—'}`);
  console.log(`      URL     : ${job.url || '—'}`);
  console.log(`      Tags    : ${(job.tags || []).map((t) => t.name || t).join(', ') || '—'}`);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

async function testBasicFetch() {
  section('Test 1: Basic fetch (page 1, no keyword)');
  const url = `${BASE_URL}?page=1`;
  const { status, data } = await fetchJson(url);

  if (status !== 200) { console.log(`  FAIL: expected 200, got ${status}`); return; }
  if (!data) { console.log('  FAIL: response is not JSON'); return; }

  console.log('  PASS: API is accessible and returns JSON');
  console.log(`  Response keys: ${Object.keys(data).join(', ')}`);
  const jobs = data.jobs || data.data || [];
  console.log(`  Jobs on page 1: ${jobs.length}`);
  console.log(`  Total count   : ${data.total_count ?? '(not in response)'}`);
  console.log(`  Total pages   : ${data.total_pages ?? '(not in response)'}`);
  if (jobs.length > 0) {
    console.log('\n  Sample job fields:', Object.keys(jobs[0]).join(', '));
    printJobSample(jobs[0], 0);
    if (jobs[1]) printJobSample(jobs[1], 1);
  }
}

async function testKeywordSearch() {
  section(`Test 2: Keyword search — "${keyword}"`);
  const params = new URLSearchParams({ page: '1', keyword });
  const url = `${BASE_URL}?${params}`;
  const { status, data } = await fetchJson(url);

  if (status !== 200 || !data) { console.log(`  FAIL: status=${status}`); return; }

  const jobs = data.jobs || data.data || [];
  console.log(`  PASS: keyword search works`);
  console.log(`  Jobs returned: ${jobs.length}`);
  console.log(`  Total count  : ${data.total_count ?? '?'}`);

  if (jobs.length > 0) {
    console.log('\n  Top 3 results:');
    jobs.slice(0, 3).forEach(printJobSample);
  }
}

async function testPagination() {
  section('Test 3: Pagination (page 2)');
  const params = new URLSearchParams({ page: '2', keyword });
  const url = `${BASE_URL}?${params}`;
  const { status, data } = await fetchJson(url);

  const jobs = data?.jobs || data?.data || [];
  if (status === 200 && jobs.length > 0) {
    console.log(`  PASS: page 2 returns ${jobs.length} results`);
  } else {
    console.log(`  INFO: page 2 returned ${jobs.length} results (may be last page)`);
  }
}

async function testConnector() {
  section('Test 4: Yourator connector (normalizeJob)');
  try {
    const connector = require('./connectors/yourator');
    const jobs = await connector.fetchPage({ keyword, page: 1 });
    console.log(`  PASS: connector.fetchPage() returned ${jobs.jobs.length} normalized jobs`);
    if (jobs.jobs.length > 0) {
      const j = jobs.jobs[0];
      console.log(`\n  Normalized job sample:`);
      console.log(`    platform  : ${j.platform}`);
      console.log(`    title     : ${j.title}`);
      console.log(`    company   : ${j.company}`);
      console.log(`    location  : ${j.location}`);
      console.log(`    salary    : ${j.salary}`);
      console.log(`    url       : ${j.url}`);
      console.log(`    tags      : ${j.tags.join(', ') || '—'}`);
      console.log(`    remote    : ${j.remote}`);
    }
  } catch (err) {
    console.log(`  FAIL: ${err.message}`);
  }
}

async function testMultiPlatform() {
  section('Test 5: MultiPlatformConnector');
  try {
    const multi = require('./connectors/index');
    console.log(`  Available platforms: ${multi.availablePlatforms().join(', ')}`);
    const { results, errors } = await multi.search(keyword, { maxPages: 1 });
    console.log(`  PASS: search returned ${results.length} jobs, ${errors.length} errors`);
    if (errors.length > 0) {
      errors.forEach((e) => console.log(`    ERROR [${e.platform}]: ${e.error}`));
    }
  } catch (err) {
    console.log(`  FAIL: ${err.message}`);
  }
}

// ─── Run ──────────────────────────────────────────────────────────────────────

(async () => {
  console.log('\n=== Yourator API Explorer ===');
  console.log(`  Base URL : ${BASE_URL}`);
  console.log(`  Keyword  : ${keyword}`);
  console.log(`  Date     : ${new Date().toISOString()}`);

  try {
    await testBasicFetch();
    await testKeywordSearch();
    await testPagination();
    await testConnector();
    await testMultiPlatform();
  } catch (err) {
    console.error('\nFATAL:', err.message);
    process.exit(1);
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log('  All tests complete.');
  console.log('='.repeat(60));
})();
