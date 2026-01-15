import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const stopsFile = join(__dirname, '..', '..', 'data', 'stops.txt');

let stopsCache = null;

/**
 * Load and parse the MTA stops.txt file
 * @returns {Object} Map of stop IDs to stop names
 */
export function loadStops() {
  if (stopsCache) return stopsCache;

  if (!existsSync(stopsFile)) {
    console.warn('stops.txt not found. Station name lookup will be unavailable.');
    console.warn('Download from: http://web.mta.info/developers/data/nyct/subway/google_transit.zip');
    return {};
  }

  const content = readFileSync(stopsFile, 'utf-8');
  const lines = content.split('\n');

  // Parse CSV header to find column indices
  const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
  const idIndex = headers.indexOf('stop_id');
  const nameIndex = headers.indexOf('stop_name');

  if (idIndex === -1 || nameIndex === -1) {
    console.error('Invalid stops.txt format');
    return {};
  }

  stopsCache = {};

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    // Simple CSV parsing (handles quoted fields)
    const values = parseCSVLine(line);
    if (values.length <= Math.max(idIndex, nameIndex)) continue;

    const stopId = values[idIndex];
    const stopName = values[nameIndex];
    stopsCache[stopId] = stopName;
  }

  return stopsCache;
}

/**
 * Parse a single CSV line, handling quoted fields
 */
function parseCSVLine(line) {
  const values = [];
  let current = '';
  let inQuotes = false;

  for (const char of line) {
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      values.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  values.push(current.trim());

  return values;
}

/**
 * Get the name of a station by stop ID
 * @param {string} stopId - Stop ID (with or without direction suffix)
 * @returns {string} Station name or the stop ID if not found
 */
export function getStopName(stopId) {
  const stops = loadStops();
  // Try exact match first
  if (stops[stopId]) return stops[stopId];
  // Try without direction suffix (N/S)
  const baseId = stopId.replace(/[NS]$/, '');
  return stops[baseId] || stopId;
}

/**
 * Search for stations by name
 * @param {string} searchTerm - Search term (case-insensitive)
 * @returns {Array} Array of matching stations with id and name
 */
export function findStopsByName(searchTerm) {
  const stops = loadStops();
  const term = searchTerm.toLowerCase();

  return Object.entries(stops)
    .filter(([id, name]) => {
      // Exclude direction-suffixed entries (N/S) to avoid duplicates
      if (/[NS]$/.test(id)) return false;
      return name.toLowerCase().includes(term);
    })
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
