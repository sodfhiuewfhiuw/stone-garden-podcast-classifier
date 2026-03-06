/**
 * MultiPlatformConnector
 * Aggregates job listings from multiple platforms with a unified interface.
 * Currently supported platforms: Yourator
 */

const yourator = require('./yourator');

const CONNECTORS = {
  yourator,
};

/**
 * Search for jobs across one or more platforms
 * @param {string} keyword - Search keyword
 * @param {object} [options]
 * @param {string[]} [options.platforms] - Platforms to search (defaults to all)
 * @param {number} [options.maxPages=3] - Max pages per platform
 * @param {boolean} [options.parallel=true] - Run platforms in parallel
 * @returns {Promise<{ results: object[], errors: object[] }>}
 */
async function search(keyword, options = {}) {
  const {
    platforms = Object.keys(CONNECTORS),
    maxPages = 3,
    parallel = true,
  } = options;

  const selectedConnectors = platforms
    .filter((p) => CONNECTORS[p])
    .map((p) => ({ name: p, connector: CONNECTORS[p] }));

  if (selectedConnectors.length === 0) {
    throw new Error(`No valid platforms specified. Available: ${Object.keys(CONNECTORS).join(', ')}`);
  }

  const results = [];
  const errors = [];

  const run = async ({ name, connector }) => {
    try {
      const jobs = await connector.search(keyword, { maxPages });
      results.push(...jobs.map((j) => ({ ...j, platform: j.platform || name })));
    } catch (err) {
      errors.push({ platform: name, error: err.message });
    }
  };

  if (parallel) {
    await Promise.all(selectedConnectors.map(run));
  } else {
    for (const c of selectedConnectors) {
      await run(c);
    }
  }

  return { results, errors };
}

/**
 * List all available platform names
 * @returns {string[]}
 */
function availablePlatforms() {
  return Object.keys(CONNECTORS);
}

/**
 * Get a specific connector by platform name
 * @param {string} platform
 * @returns {object|null}
 */
function getConnector(platform) {
  return CONNECTORS[platform] || null;
}

module.exports = {
  search,
  availablePlatforms,
  getConnector,
  connectors: CONNECTORS,
};
