// Fetches current weather (temperature + rain indicator) from the National
// Weather Service. NWS asks for a contact-bearing User-Agent and is fine with
// a few requests per minute — we cache the hourly forecast for 10 minutes.
//
// Two-step protocol:
//   1. /points/{lat},{lon}  → returns gridpoint URLs (immutable for a fixed
//      location, so we cache indefinitely in-memory).
//   2. <forecastHourly URL> → returns 156 hourly periods; we read [0].

const NWS_BASE = 'https://api.weather.gov';
const USER_AGENT = 'subway-sign (https://github.com/jensenmatlock/subway-sign)';
const FORECAST_TTL = 10 * 60 * 1000;
const RAIN_PROB_THRESHOLD = 40;
const RAIN_FORECAST_RE = /rain|shower|drizzle|thunderstorm/i;

let pointsCache = null;
let forecastCache = { data: null, timestamp: 0 };

async function nwsFetch(url) {
  const res = await fetch(url, { headers: { 'User-Agent': USER_AGENT, 'Accept': 'application/geo+json' } });
  if (!res.ok) {
    throw new Error(`NWS ${res.status} on ${url}`);
  }
  return res.json();
}

async function getForecastHourlyUrl(lat, lon) {
  if (pointsCache) return pointsCache;
  const data = await nwsFetch(`${NWS_BASE}/points/${lat},${lon}`);
  pointsCache = data.properties.forecastHourly;
  return pointsCache;
}

function buildResult(period) {
  const probability = period.probabilityOfPrecipitation?.value ?? 0;
  const forecastText = period.shortForecast || '';
  const rain = probability >= RAIN_PROB_THRESHOLD || RAIN_FORECAST_RE.test(forecastText);
  return {
    temperature: Math.round(period.temperature),
    unit: period.temperatureUnit || 'F',
    rain,
  };
}

export async function getWeather(lat, lon) {
  const now = Date.now();
  if (forecastCache.data && (now - forecastCache.timestamp) < FORECAST_TTL) {
    return { ...forecastCache.data, stale: false, ageMs: now - forecastCache.timestamp };
  }
  try {
    const forecastHourlyUrl = await getForecastHourlyUrl(lat, lon);
    const forecast = await nwsFetch(forecastHourlyUrl);
    const period = forecast.properties.periods[0];
    const result = buildResult(period);
    forecastCache = { data: result, timestamp: now };
    return { ...result, stale: false, ageMs: 0 };
  } catch (err) {
    console.error('Weather fetch failed:', err.message);
    if (forecastCache.data) {
      return { ...forecastCache.data, stale: true, ageMs: now - forecastCache.timestamp };
    }
    return null;
  }
}
