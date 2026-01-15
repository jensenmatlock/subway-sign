/**
 * Extract arrival times for a specific stop from a GTFS-RT feed
 * @param {Object} feed - Decoded GTFS-RT feed
 * @param {string} stopId - Base stop ID (e.g., "A22")
 * @param {string} direction - Direction suffix ("N" or "S")
 * @param {string[]} routes - Array of route IDs to filter (e.g., ["A", "C"])
 * @returns {Array} Sorted array of arrival objects
 */
export function getArrivalsForStop(feed, stopId, direction, routes) {
  if (!feed || !feed.entity) return [];

  const arrivals = [];
  const now = Math.floor(Date.now() / 1000);
  const fullStopId = stopId + direction;

  for (const entity of feed.entity) {
    if (!entity.tripUpdate) continue;

    const tripUpdate = entity.tripUpdate;
    const routeId = tripUpdate.trip?.routeId;

    // Filter by routes if specified
    if (routes && routes.length > 0 && !routes.includes(routeId)) continue;

    for (const stopTime of tripUpdate.stopTimeUpdate || []) {
      // Match stop ID with direction suffix
      if (stopTime.stopId !== fullStopId) continue;

      // Get arrival time - handle both Long object and plain number formats
      const arrivalTime = stopTime.arrival?.time?.low ?? stopTime.arrival?.time;
      if (!arrivalTime || arrivalTime < now) continue;

      const minutesUntil = Math.round((arrivalTime - now) / 60);

      arrivals.push({
        route: routeId,
        stopId: stopTime.stopId,
        arrivalTime,
        minutesUntil
      });
    }
  }

  // Sort by arrival time
  return arrivals.sort((a, b) => a.arrivalTime - b.arrivalTime);
}

/**
 * Format arrivals for display, grouping by route and limiting results
 * @param {Array} arrivals - Array of arrival objects
 * @param {number} maxPerRoute - Max arrivals to show per route (default 2)
 * @param {number} maxTotal - Max total arrivals to return (default 4)
 * @returns {Array} Formatted arrivals for display
 */
export function formatArrivalsForDisplay(arrivals, maxPerRoute = 2, maxTotal = 4) {
  const byRoute = new Map();

  for (const arrival of arrivals) {
    if (!byRoute.has(arrival.route)) {
      byRoute.set(arrival.route, []);
    }
    const routeArrivals = byRoute.get(arrival.route);
    if (routeArrivals.length < maxPerRoute) {
      routeArrivals.push(arrival);
    }
  }

  // Flatten and sort by arrival time, then limit
  const result = [];
  for (const [route, routeArrivals] of byRoute) {
    result.push(...routeArrivals);
  }

  return result
    .sort((a, b) => a.arrivalTime - b.arrivalTime)
    .slice(0, maxTotal);
}
