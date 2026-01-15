import GtfsRealtimeBindings from 'gtfs-realtime-bindings';

/**
 * Fetch and decode a single GTFS-RT feed from the MTA API
 * @param {string} url - The MTA feed URL
 * @returns {Promise<Object>} Decoded protobuf feed message
 */
export async function fetchFeed(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Feed fetch failed: ${response.status} ${response.statusText}`);
  }

  const buffer = await response.arrayBuffer();
  const feed = GtfsRealtimeBindings.transit_realtime.FeedMessage.decode(
    new Uint8Array(buffer)
  );

  return feed;
}

/**
 * Fetch multiple GTFS-RT feeds in parallel
 * @param {Object} feedUrls - Object mapping feed names to URLs
 * @returns {Promise<Object>} Object mapping feed names to decoded feeds (or null on error)
 */
export async function fetchAllFeeds(feedUrls) {
  const entries = Object.entries(feedUrls);
  const results = await Promise.all(
    entries.map(async ([name, url]) => {
      try {
        const feed = await fetchFeed(url);
        return [name, feed];
      } catch (error) {
        console.error(`Error fetching ${name} feed:`, error.message);
        return [name, null];
      }
    })
  );

  return Object.fromEntries(results);
}
