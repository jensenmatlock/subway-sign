// Fetches current weather (temperature + precipitation indicator) from the
// National Weather Service. NWS asks for a contact-bearing User-Agent and is
// fine with a few requests per minute — we cache the hourly forecast for 10 min.
//
// Two independent questions decide the glyph, and keeping them independent is
// the point: shortForecast says *what kind* of precipitation (classifyPrecip),
// probabilityOfPrecipitation says *whether it's likely enough to show*. An
// earlier version OR'd the two, which let rain wording light the glyph at any
// probability.
//
// Two-step protocol:
//   1. /points/{lat},{lon}  → returns gridpoint URLs (immutable for a fixed
//      location, so we cache indefinitely in-memory).
//   2. <forecastHourly URL> → returns 156 hourly periods; we read [0].

const NWS_BASE = 'https://api.weather.gov';
const USER_AGENT = 'subway-sign (https://github.com/jensenmatlock/subway-sign)';
const FORECAST_TTL = 10 * 60 * 1000;
// Past this age a cached reading is dropped rather than served: a glyph from an
// hours-old forecast is indistinguishable on the sign from a fresh one, so
// showing nothing beats showing something wrong.
const MAX_STALE_MS = 60 * 60 * 1000;
// Below this, no glyph regardless of type. NWS wording alone is too eager:
// "Slight Chance Rain Showers" appears from ~10% up.
const PRECIP_THRESHOLD = 40;
// Order matters — see classifyPrecip.
// "freezing" is spelled out rather than matched bare: NWS also emits
// "Freezing Fog", which is not precipitation and must fall through to DRY_RE.
const SNOW_RE = /snow|flurr|blizzard|sleet|ice pellet|wintry|freezing (rain|drizzle)/i;
const RAIN_RE = /rain|shower|drizzle|thunderstorm|hail/i;
const DRY_RE = /fog|haze|smoke|dust|sunny|clear|cloudy|windy|breezy/i;
// Bound every NWS request so a hung weather fetch can't extend the shared
// /api/arrivals response past the display client's timeout. A timeout rejects
// the fetch, which getWeather's try/catch turns into a stale/null reading.
const WEATHER_TIMEOUT_MS = 6000;

let pointsCache = null;
let forecastCache = { data: null, timestamp: 0 };

async function nwsFetch(url) {
  const res = await fetch(url, {
    headers: { 'User-Agent': USER_AGENT, 'Accept': 'application/geo+json' },
    signal: AbortSignal.timeout(WEATHER_TIMEOUT_MS),
  });
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

// Maps an NWS shortForecast to the glyph to draw: 'rain', 'snow', or null for
// nothing. shortForecast is generated from structured (coverage, weather,
// intensity) codes, so this matches a bounded vocabulary rather than prose.
//
// The ordering is load-bearing:
//   1. Snow first — "Snow Showers" also matches RAIN_RE via "Shower", so a
//      rain-first check would draw a droplet for snow. This also resolves mixed
//      wording ("Rain And Snow Showers Likely") to snow, which is the more
//      useful signal of the two.
//   2. Then rain — RAIN_RE must keep shower/thunderstorm because the most
//      common wet wording, "Showers And Thunderstorms", contains no "Rain".
//   3. Then dry — fog reaches 51% probability, clearing the threshold below
//      without being precipitation, so it has to short-circuit the fallback.
//   4. Fallback to rain for precipitation we don't have wording for yet
//      (freezing rain, sleet, wintry mix and friends are unverified here).
export function classifyPrecip(shortForecast) {
  const text = shortForecast || '';
  if (SNOW_RE.test(text)) return 'snow';
  if (RAIN_RE.test(text)) return 'rain';
  if (DRY_RE.test(text)) return null;
  return 'rain';
}

export function buildResult(period) {
  const probability = period.probabilityOfPrecipitation?.value ?? 0;
  const precip =
    probability >= PRECIP_THRESHOLD ? classifyPrecip(period.shortForecast) : null;
  return {
    temperature: Math.round(period.temperature),
    unit: period.temperatureUnit || 'F',
    precip,
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
    const ageMs = now - forecastCache.timestamp;
    if (forecastCache.data && ageMs < MAX_STALE_MS) {
      return { ...forecastCache.data, stale: true, ageMs };
    }
    return null;
  }
}
