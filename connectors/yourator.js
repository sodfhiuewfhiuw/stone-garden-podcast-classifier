/**
 * Yourator Connector
 * Platform: https://www.yourator.co
 * API: Public JSON API, no authentication required
 * Endpoint: https://www.yourator.co/api/v4/jobs
 */

const https = require('https');

const YOURATOR_BASE_URL = 'https://www.yourator.co/api/v4/jobs';
const DEFAULT_PAGE_SIZE = 20; // API returns 20 per page
const REQUEST_DELAY_MS = 1000; // Delay between requests to be polite

/**
 * Make an HTTP GET request and return parsed JSON
 * @param {string} url
 * @returns {Promise<object>}
 */
function fetchJson(url) {
  return new Promise((resolve, reject) => {
    const options = {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; JobHunter/1.0)',
      },
    };

    https.get(url, options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (err) {
          reject(new Error(`Failed to parse JSON from ${url}: ${err.message}`));
        }
      });
    }).on('error', (err) => {
      reject(new Error(`Request failed for ${url}: ${err.message}`));
    });
  });
}

/**
 * Sleep for a given number of milliseconds
 * @param {number} ms
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Normalize a Yourator job object to the standard format
 * @param {object} job - Raw job from Yourator API
 * @returns {object} Standardized job object
 */
function normalizeJob(job) {
  return {
    platform: 'yourator',
    id: String(job.id || ''),
    title: job.title || '',
    company: job.company?.brand_name || job.company?.name || '',
    location: job.location || job.address || '',
    salary: formatSalary(job),
    description: job.description || job.content || '',
    requirements: job.requirement || '',
    url: buildJobUrl(job),
    tags: extractTags(job),
    experience: job.experience_requirement || '',
    jobType: job.job_type || '',
    remote: isRemote(job),
    postedAt: job.updated_at || job.created_at || '',
    rawData: job,
  };
}

/**
 * Format salary information from a Yourator job object
 * @param {object} job
 * @returns {string}
 */
function formatSalary(job) {
  if (!job.salary_min && !job.salary_max) return '';
  if (job.salary_min && job.salary_max) {
    return `TWD ${job.salary_min.toLocaleString()} - ${job.salary_max.toLocaleString()}`;
  }
  if (job.salary_min) return `TWD ${job.salary_min.toLocaleString()}+`;
  if (job.salary_max) return `up to TWD ${job.salary_max.toLocaleString()}`;
  return '';
}

/**
 * Build the full job URL
 * @param {object} job
 * @returns {string}
 */
function buildJobUrl(job) {
  if (job.url) return job.url;
  if (job.company?.path && job.path) {
    return `https://www.yourator.co/companies/${job.company.path}/jobs/${job.path}`;
  }
  if (job.id) return `https://www.yourator.co/jobs/${job.id}`;
  return 'https://www.yourator.co';
}

/**
 * Extract tags/skills from a job
 * @param {object} job
 * @returns {string[]}
 */
function extractTags(job) {
  const tags = [];
  if (Array.isArray(job.tags)) tags.push(...job.tags.map((t) => t.name || t));
  if (Array.isArray(job.categories)) tags.push(...job.categories.map((c) => c.name || c));
  if (Array.isArray(job.tools)) tags.push(...job.tools.map((t) => t.name || t));
  return [...new Set(tags)];
}

/**
 * Check if a job is remote-friendly
 * @param {object} job
 * @returns {boolean}
 */
function isRemote(job) {
  const remoteFields = [job.remote, job.is_remote, job.job_type];
  return remoteFields.some((f) => typeof f === 'string' && f.toLowerCase().includes('remote'))
    || Boolean(job.remote === true || job.is_remote === true);
}

/**
 * Fetch jobs from Yourator API for a given page
 * @param {object} options
 * @param {string} [options.keyword] - Search keyword
 * @param {number} [options.page=1] - Page number (1-indexed)
 * @returns {Promise<{ jobs: object[], totalPages: number, totalCount: number }>}
 */
async function fetchPage({ keyword = '', page = 1 } = {}) {
  const params = new URLSearchParams({ page: String(page) });
  if (keyword) params.append('keyword', keyword);

  const url = `${YOURATOR_BASE_URL}?${params.toString()}`;
  const data = await fetchJson(url);

  // Yourator API response shape (discovered via exploration):
  // { jobs: [...], total_count: N, total_pages: N, current_page: N }
  const jobs = data.jobs || data.data || data || [];
  const totalCount = data.total_count || data.meta?.total_count || 0;
  const totalPages = data.total_pages || data.meta?.total_pages
    || Math.ceil(totalCount / DEFAULT_PAGE_SIZE) || 1;

  return {
    jobs: Array.isArray(jobs) ? jobs.map(normalizeJob) : [],
    totalPages,
    totalCount,
  };
}

/**
 * Fetch all jobs matching the given keyword (handles pagination automatically)
 * @param {object} options
 * @param {string} [options.keyword] - Search keyword
 * @param {number} [options.maxPages=5] - Maximum pages to fetch
 * @param {Function} [options.onProgress] - Progress callback(currentPage, totalPages)
 * @returns {Promise<object[]>} Array of normalized job objects
 */
async function fetchJobs({ keyword = '', maxPages = 5, onProgress } = {}) {
  const allJobs = [];
  let page = 1;
  let totalPages = 1;

  do {
    if (typeof onProgress === 'function') onProgress(page, totalPages);

    const result = await fetchPage({ keyword, page });
    allJobs.push(...result.jobs);
    totalPages = result.totalPages;

    if (page < Math.min(totalPages, maxPages)) {
      await sleep(REQUEST_DELAY_MS);
    }

    page += 1;
  } while (page <= Math.min(totalPages, maxPages));

  return allJobs;
}

/**
 * Search Yourator jobs by keyword
 * @param {string} keyword
 * @param {object} [options]
 * @param {number} [options.maxPages=3]
 * @returns {Promise<object[]>}
 */
async function search(keyword, options = {}) {
  return fetchJobs({ keyword, maxPages: options.maxPages || 3, ...options });
}

module.exports = {
  platform: 'yourator',
  search,
  fetchJobs,
  fetchPage,
  normalizeJob,
};
