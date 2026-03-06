/**
 * hunter-config.js
 * Central configuration for the MultiPlatformConnector job hunter.
 * Edit this file to customize search keywords, platforms, and output behaviour.
 */

module.exports = {
  // ─── Search Settings ───────────────────────────────────────────────────────
  search: {
    // Keywords to search for jobs
    keywords: [
      'software engineer',
      'backend engineer',
      'frontend engineer',
      'full stack',
      'data engineer',
    ],

    // Platforms to query (must match keys in connectors/index.js)
    platforms: ['yourator'],

    // Maximum pages to fetch per keyword per platform
    maxPages: 3,

    // Run platforms in parallel for speed
    parallel: true,
  },

  // ─── Platform-Specific Settings ────────────────────────────────────────────
  platforms: {
    yourator: {
      enabled: true,
      // Delay between paginated requests (ms) — be polite to the server
      requestDelayMs: 1000,
      // Maximum pages to fetch (overrides search.maxPages for this platform)
      maxPages: 3,
    },
  },

  // ─── Output Settings ───────────────────────────────────────────────────────
  output: {
    // 'console' | 'json' | 'csv'
    format: 'console',
    // File path for json/csv output (ignored for 'console')
    filePath: './output/jobs.json',
    // Whether to include the raw API response in each job object
    includeRawData: false,
  },

  // ─── Filter Settings ───────────────────────────────────────────────────────
  filters: {
    // Only include remote-friendly jobs
    remoteOnly: false,
    // Minimum salary (TWD, monthly). Set to 0 to disable.
    minSalary: 0,
    // Exclude jobs matching these title keywords (case-insensitive)
    excludeTitles: [],
    // Only include jobs matching these location strings (empty = all locations)
    locations: [],
  },
};
