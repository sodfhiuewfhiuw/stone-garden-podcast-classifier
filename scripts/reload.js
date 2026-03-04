'use strict';

/**
 * scripts/reload.js  →  npm run reload
 *
 * Triggers a hot-reload by touching the config file.
 * The running engine's chokidar watcher will detect the change and reload.
 */

const fs = require('fs');
const path = require('path');

const configPath = path.resolve(process.env.CONFIG_PATH || './config/matrix.yaml');

if (!fs.existsSync(configPath)) {
  console.error(`Config not found: ${configPath}`);
  process.exit(1);
}

const now = new Date();
fs.utimesSync(configPath, now, now);
console.log(`Touched ${configPath} — engine will hot-reload shortly.`);
