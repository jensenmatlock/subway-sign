import { Router } from 'express';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { fetchAllFeeds } from '../lib/gtfs-fetcher.js';
import { getArrivalsForStop, formatArrivalsForDisplay } from '../lib/arrival-parser.js';
import { findStopsByName, getStopName } from '../lib/station-lookup.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(
  readFileSync(join(__dirname, '..', '..', 'config.json'), 'utf-8')
);

const router = Router();

// Feed cache with TTL
let feedCache = { data: null, timestamp: 0 };
const CACHE_TTL = 15000; // 15 seconds

/**
 * Get cached feeds or fetch fresh data
 */
async function getCachedFeeds() {
  const now = Date.now();
  if (feedCache.data && (now - feedCache.timestamp) < CACHE_TTL) {
    return feedCache.data;
  }

  console.log('Fetching fresh feed data...');
  feedCache.data = await fetchAllFeeds(config.feeds);
  feedCache.timestamp = now;
  return feedCache.data;
}

/**
 * GET /api/arrivals
 * Main endpoint - returns arrivals for all configured rows
 */
router.get('/arrivals', async (req, res) => {
  try {
    const feeds = await getCachedFeeds();
    const direction = config.direction;

    const result = {
      timestamp: Date.now(),
      direction,
      rows: {}
    };

    // Process each row from config
    for (const [rowKey, rowConfig] of Object.entries(config.layout)) {
      const stationConfig = config.stations[rowConfig.station];
      const feed = feeds[rowConfig.feed];

      const arrivals = getArrivalsForStop(
        feed,
        stationConfig.id,
        direction,
        rowConfig.lines
      );

      result.rows[rowKey] = {
        label: rowConfig.label,
        station: stationConfig.name,
        stationId: stationConfig.id,
        lines: rowConfig.lines,
        arrivals: formatArrivalsForDisplay(arrivals, 2, 4)
      };
    }

    res.json(result);
  } catch (error) {
    console.error('Error fetching arrivals:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/arrivals/raw
 * Debug endpoint - returns raw arrival data without formatting
 */
router.get('/arrivals/raw', async (req, res) => {
  try {
    const feeds = await getCachedFeeds();
    const direction = config.direction;

    const result = {
      timestamp: Date.now(),
      feedStatus: {},
      rows: {}
    };

    // Report feed status
    for (const [name, feed] of Object.entries(feeds)) {
      result.feedStatus[name] = feed ? `OK (${feed.entity?.length || 0} entities)` : 'ERROR';
    }

    // Process each row
    for (const [rowKey, rowConfig] of Object.entries(config.layout)) {
      const stationConfig = config.stations[rowConfig.station];
      const feed = feeds[rowConfig.feed];

      result.rows[rowKey] = getArrivalsForStop(
        feed,
        stationConfig.id,
        direction,
        rowConfig.lines
      );
    }

    res.json(result);
  } catch (error) {
    console.error('Error fetching arrivals:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/stations?search=<term>
 * Search for stations by name
 */
router.get('/stations', (req, res) => {
  const search = req.query.search || '';

  if (search.length < 2) {
    return res.status(400).json({
      error: 'Search term must be at least 2 characters'
    });
  }

  const results = findStopsByName(search);
  res.json(results);
});

/**
 * GET /api/station/:id
 * Get station name by ID
 */
router.get('/station/:id', (req, res) => {
  const name = getStopName(req.params.id);
  res.json({ id: req.params.id, name });
});

/**
 * GET /api/config
 * Return current configuration (useful for display client)
 */
router.get('/config', (req, res) => {
  res.json({
    stations: config.stations,
    direction: config.direction,
    layout: config.layout,
    display: config.display,
    refreshInterval: config.server.refreshInterval
  });
});

/**
 * GET /api/health
 * Health check endpoint
 */
router.get('/health', async (req, res) => {
  try {
    const feeds = await getCachedFeeds();
    const feedStatus = {};

    for (const [name, feed] of Object.entries(feeds)) {
      feedStatus[name] = feed !== null;
    }

    res.json({
      status: 'ok',
      timestamp: Date.now(),
      cacheAge: Date.now() - feedCache.timestamp,
      feeds: feedStatus
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
});

export default router;
