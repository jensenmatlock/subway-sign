import GtfsRealtimeBindings from 'gtfs-realtime-bindings';

/**
 * Fetch and decode a single GTFS-RT feed from the MTA API
 * @param {string} url - The MTA feed URL
 * @returns {Promise<Object>} Decoded protobuf feed message
 */
const FEED_TIMEOUT_MS = 8000;

export async function fetchFeed(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(FEED_TIMEOUT_MS) });

  if (!response.ok) {
    throw new Error(`Feed fetch failed: ${response.status} ${response.statusText}`);
  }

  const buffer = await response.arrayBuffer();
  const feed = GtfsRealtimeBindings.transit_realtime.FeedMessage.decode(
    new Uint8Array(buffer)
  );

  return feed;
}

// Last successfully decoded feed per name. On a transient fetch failure we serve
// the previous feed instead of null so the row keeps its arrivals rather than
// dropping to "---". No age cap is needed: getArrivalsForStop filters out
// arrivals whose arrivalTime is in the past, so a stale feed's row self-empties
// within the normal arrival horizon if the feed stays down.
const lastGoodFeeds = {};

/**
 * Fetch multiple GTFS-RT feeds in parallel
 * @param {Object} feedUrls - Object mapping feed names to URLs
 * @returns {Promise<Object>} Object mapping feed names to decoded feeds. On
 *   failure, falls back to the last good feed for that name, or null if none.
 */
export async function fetchAllFeeds(feedUrls) {
  const entries = Object.entries(feedUrls);
  const results = await Promise.all(
    entries.map(async ([name, url]) => {
      try {
        const feed = await fetchFeed(url);
        lastGoodFeeds[name] = feed;
        return [name, feed];
      } catch (error) {
        console.error(`Error fetching ${name} feed:`, error.message);
        return [name, lastGoodFeeds[name] ?? null];
      }
    })
  );

  return Object.fromEntries(results);
}
