// Fetches current weather (temperature + precipitation indicator) from the
// National Weather Service. NWS asks for a contact-bearing User-Agent and is
// fine with a few requests per minute — we cache the hourly forecast for 10 min.
//
// Three independent questions decide the glyph, and keeping them independent is
// the point: the look-ahead window says *which hour* to answer for,
// shortForecast says *what kind* of precipitation (classifyPrecip), and
// probabilityOfPrecipitation says *whether it's likely enough to show*. An
// earlier version OR'd the last two, which let rain wording light the glyph at
// any probability.
//
// Two-step protocol:
//   1. /points/{lat},{lon}  → returns gridpoint URLs (immutable for a fixed
//      location, so we cache indefinitely in-memory).
//   2. <forecastHourly URL> → returns 156 hourly periods; we read the first
//      LOOKAHEAD_PERIODS of them.

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
// How many hourly periods the glyph answers for, counting the one we're in.
// A sign by the door is read as "do I need an umbrella", not "is it raining
// this instant" — reading periods[0] alone meant a 40% window opening at 08:00
// was invisible at 07:59. periods[0] is the current, partially elapsed hour, so
// three periods reach between 2h and 3h ahead depending on where in the hour we
// land; the 2h floor is the number that matters, and it covers leaving the
// house and coming back. Widening this further trades warning time for a glyph
// that sits lit through a dry morning because of an afternoon thunderstorm.
const LOOKAHEAD_PERIODS = 3;
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
//   4. Fallback to rain for wording none of the three patterns claim — a
//      droplet is the safer default for an unknown code than nothing at all.
//      Winter wording is NOT this case: sleet, wintry mix and freezing
//      rain/drizzle are all matched by SNOW_RE at step 1. Genuine fallback
//      material is rarer still ("Ice Crystals", "Volcanic Ash").
export function classifyPrecip(shortForecast) {
  const text = shortForecast || '';
  if (SNOW_RE.test(text)) return 'snow';
  if (RAIN_RE.test(text)) return 'rain';
  if (DRY_RE.test(text)) return null;
  return 'rain';
}

// A period's precipitation probability, absent or null both meaning zero.
function probabilityOf(period) {
  return period.probabilityOfPrecipitation?.value ?? 0;
}

// Temperature always comes from the hour we're in; the glyph comes from the
// wettest hour in the look-ahead window. Those are deliberately different
// periods — the temperature is a reading of now, the glyph is a warning.
export function buildResult(periods) {
  const window = periods.slice(0, LOOKAHEAD_PERIODS);
  if (window.length === 0) {
    throw new Error('NWS returned no forecast periods');
  }
  const current = window[0];
  // The wettest hour in the window is the one worth warning about, and it must
  // carry its own shortForecast into classifyPrecip: pairing a later hour's
  // probability with the current hour's wording would draw a droplet for
  // "Partly Sunny". `>` rather than `>=` keeps the earlier period on a tie,
  // so an unchanged probability across the window describes the nearer hour.
  const wettest = window.reduce((a, b) => (probabilityOf(b) > probabilityOf(a) ? b : a));
  const probability = probabilityOf(wettest);
  const precip =
    probability >= PRECIP_THRESHOLD ? classifyPrecip(wettest.shortForecast) : null;
  return {
    temperature: Math.round(current.temperature),
    unit: current.temperatureUnit || 'F',
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
    const result = buildResult(forecast.properties.periods);
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
