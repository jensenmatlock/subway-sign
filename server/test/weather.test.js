import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildResult, classifyPrecip } from '../lib/weather.js';

// --- classifyPrecip: symbol selection --------------------------------------
//
// Every shortForecast below is a verbatim NWS wording observed in a 3,432-period
// sample across 22 US locations, except the winter and fallback cases at the end
// which August couldn't produce.

const CLASSIFY = [
  // [shortForecast, expected symbol, why]
  ['Snow Showers', 'snow', 'contains "Shower" — the rain pattern matches it too'],
  ['Snow Showers Likely', 'snow', 'ordering: snow must win over the shower match'],
  ['Chance Snow Showers', 'snow', 'ordering'],
  ['Scattered Snow Showers', 'snow', 'ordering'],
  ['Isolated Snow Showers', 'snow', 'ordering'],
  ['Light Snow Likely', 'snow', 'plain snow wording'],
  ['Chance Light Snow', 'snow', 'plain snow wording'],
  ['Snow Showers Likely And Areas Of Blowing Snow', 'snow', 'compound, all snow'],
  ['Rain And Snow Showers Likely', 'snow', 'mixed resolves to snow'],
  ['Scattered Rain And Snow Showers', 'snow', 'mixed resolves to snow'],
  ['Chance Showers And Thunderstorms', 'rain', 'no "Rain" token at all'],
  ['Showers And Thunderstorms', 'rain', 'no "Rain" token at all'],
  ['Showers And Thunderstorms Likely', 'rain', 'no "Rain" token at all'],
  ['Chance Rain Showers', 'rain', 'plain rain wording'],
  ['Scattered Rain Showers', 'rain', 'plain rain wording'],
  ['Light Rain Likely', 'rain', 'plain rain wording'],
  ['Areas Of Fog', null, 'not precipitation — must beat the fallback'],
  ['Patchy Fog', null, 'not precipitation'],
  ['Sunny', null, 'dry'],
  ['Mostly Cloudy', null, 'dry'],
  // Winter vocabulary the August sample could not produce.
  ['Freezing Rain', 'snow', 'freezing beats the rain match'],
  ['Freezing Drizzle', 'snow', 'freezing beats the drizzle match'],
  ['Areas Of Freezing Fog', null, 'freezing fog is not precipitation'],
  ['Ice Fog', null, 'not precipitation'],
  ['Wintry Mix', 'snow', 'winter wording'],
  ['Blizzard Conditions', 'snow', 'winter wording'],
  ['Sleet', 'snow', 'winter wording'],
  ['Drizzle', 'rain', 'rain wording'],
  // Nothing in the sample reached the fallback; this pins its behaviour anyway.
  ['Volcanic Ash', 'rain', 'unrecognised precipitation falls back to rain'],
];

for (const [text, expected, why] of CLASSIFY) {
  test(`classify "${text}" -> ${expected} (${why})`, () => {
    assert.equal(classifyPrecip(text), expected);
  });
}

test('snow is tested before rain', () => {
  // "Snow Showers" matches both patterns. If the rain branch is ever moved
  // ahead of the snow branch this is the test that fails, and it is the only
  // symptom — the display has no way to detect a droplet drawn for snow.
  assert.equal(classifyPrecip('Snow Showers'), 'snow');
});

test('missing shortForecast does not throw', () => {
  assert.equal(classifyPrecip(undefined), 'rain');
  assert.equal(classifyPrecip(''), 'rain');
});

// --- buildResult: the probability gate -------------------------------------

function period(probability, shortForecast, temperature = 72) {
  return {
    probabilityOfPrecipitation: { value: probability },
    shortForecast,
    temperature,
    temperatureUnit: 'F',
  };
}

const GATE = [
  // [probability, shortForecast, expected precip, why]
  // A single-period window, so the gate is exercised on its own without the
  // look-ahead in play. Multi-period behaviour is covered further down.
  [18, 'Slight Chance Rain Showers', null, 'below the gate'],
  [39, 'Chance Rain Showers', null, 'just below the gate'],
  [40, 'Chance Rain Showers', 'rain', 'at the gate'],
  [54, 'Chance Showers And Thunderstorms', 'rain', 'above the gate'],
  [92, 'Showers And Thunderstorms', 'rain', 'above the gate'],
  [24, 'Isolated Snow Showers', null, 'snow below the gate shows nothing'],
  [71, 'Snow Showers Likely', 'snow', 'snow above the gate'],
  [66, 'Rain And Snow Showers Likely', 'snow', 'mixed above the gate'],
  [51, 'Areas Of Fog', null, 'clears the gate but is not precipitation'],
  [4, 'Patchy Fog', null, 'below the gate and not precipitation'],
];

for (const [probability, shortForecast, expected, why] of GATE) {
  test(`precip=${expected} at ${probability}% "${shortForecast}" (${why})`, () => {
    assert.equal(buildResult([period(probability, shortForecast)]).precip, expected);
  });
}

test('a null probabilityOfPrecipitation coerces to 0, not to precipitation', () => {
  const result = buildResult([{
    probabilityOfPrecipitation: { value: null },
    shortForecast: 'Chance Rain Showers',
    temperature: 61,
  }]);
  assert.equal(result.precip, null);
});

test('a missing probabilityOfPrecipitation coerces to 0, not to precipitation', () => {
  const result = buildResult([{ shortForecast: 'Rain Showers', temperature: 61 }]);
  assert.equal(result.precip, null);
});

test('temperature is rounded and the unit defaults to F', () => {
  const result = buildResult([{
    probabilityOfPrecipitation: { value: 0 },
    shortForecast: 'Sunny',
    temperature: 71.6,
  }]);
  assert.equal(result.temperature, 72);
  assert.equal(result.unit, 'F');
});

test('the payload carries precip and no legacy rain field', () => {
  const result = buildResult([period(80, 'Snow Showers')]);
  assert.deepEqual(Object.keys(result).sort(), ['precip', 'temperature', 'unit']);
});

// --- buildResult: the look-ahead window ------------------------------------
//
// periods[0] is the hour we are currently inside; the glyph answers for the
// first LOOKAHEAD_PERIODS of them. These tests pin the window's width from
// both directions, its tie-break, and the split between which period supplies
// the temperature and which supplies the glyph.

test('rain in the next hour lights the glyph while the current hour is dry', () => {
  // The reported bug, verbatim: at 07:46 on 2026-08-27 the 07:00 period read
  // 1% / "Partly Sunny" and the 08:00 period read 40% / "Chance Rain Showers".
  // Reading periods[0] alone showed nothing 14 minutes before the rain window.
  const result = buildResult([
    period(1, 'Partly Sunny', 72),
    period(40, 'Chance Rain Showers', 73),
  ]);
  assert.equal(result.precip, 'rain');
  assert.equal(result.temperature, 72, 'temperature still reads the current hour');
});

test('rain in the last hour of the window still lights the glyph', () => {
  // Pins the window's width from below: the third period is the last one
  // inside it. Narrowing LOOKAHEAD_PERIODS is what this test catches.
  const result = buildResult([
    period(1, 'Partly Sunny'),
    period(4, 'Mostly Cloudy'),
    period(65, 'Rain Showers Likely'),
  ]);
  assert.equal(result.precip, 'rain');
});

test('rain past the window does not light the glyph', () => {
  // Pins the width from above: the fourth period is outside the window.
  // Widening LOOKAHEAD_PERIODS is what this test catches. Together with the
  // test above, the pair fixes the window at exactly 3 rather than "at least".
  const result = buildResult([
    period(1, 'Partly Sunny'),
    period(4, 'Mostly Cloudy'),
    period(2, 'Sunny'),
    period(90, 'Showers And Thunderstorms Likely'),
  ]);
  assert.equal(result.precip, null);
});

test('the glyph is classified from the wettest period, not the current one', () => {
  // Pairing the later hour's probability with the current hour's wording would
  // pass "Mostly Cloudy" to classifyPrecip and draw nothing; pairing it with a
  // rain wording would draw a droplet for snow. Both are wrong here.
  const result = buildResult([
    period(2, 'Mostly Cloudy'),
    period(85, 'Snow Showers Likely'),
  ]);
  assert.equal(result.precip, 'snow');
});

test('a dry later hour does not suppress precipitation happening now', () => {
  // The window takes a max, not the last period — rain now and clearing later
  // still warrants the glyph.
  const result = buildResult([
    period(75, 'Rain Showers'),
    period(3, 'Sunny'),
  ]);
  assert.equal(result.precip, 'rain');
});

test('an equal probability across the window describes the nearer hour', () => {
  // Pins the `>` in the reduce against a drift to `>=`. Identical probabilities
  // with differing wording is the only input that tells the two apart, and NWS
  // does emit flat probabilities across adjacent hours (40/40/40 in the
  // 2026-08-27 sample above).
  const result = buildResult([
    period(60, 'Rain Showers'),
    period(60, 'Snow Showers'),
  ]);
  assert.equal(result.precip, 'rain');
});

test('a window shorter than LOOKAHEAD_PERIODS is handled', () => {
  // slice() past the end is safe; this pins that the tail of the forecast
  // doesn't need special casing, at both one and two periods short.
  assert.equal(buildResult([period(80, 'Rain Showers')]).precip, 'rain');
  assert.equal(
    buildResult([period(3, 'Sunny'), period(80, 'Rain Showers')]).precip,
    'rain',
  );
});

test('no forecast periods throws rather than returning a bogus reading', () => {
  // getWeather's catch turns this into a stale-or-null reading. Returning a
  // half-built object instead would put NaN on the sign.
  assert.throws(() => buildResult([]), /no forecast periods/);
});

// --- getWeather: staleness cap --------------------------------------------
//
// pointsCache and forecastCache are module-level, so each of these imports the
// module under a fresh specifier to get its own cache rather than inheriting
// whatever a previous test left behind.

let moduleCounter = 0;
function freshWeatherModule() {
  moduleCounter += 1;
  return import(`../lib/weather.js?fresh=${moduleCounter}`);
}

function stubFetch(t, handler) {
  const realFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = realFetch; });
  globalThis.fetch = handler;
}

// Answers the /points lookup, then defers the forecast to `forecast()` so a
// test can flip the forecast from success to failure mid-run.
function nwsStub(forecast) {
  return async (url) => {
    if (String(url).includes('/points/')) {
      return {
        ok: true,
        json: async () => ({ properties: { forecastHourly: 'https://nws.test/hourly' } }),
      };
    }
    return forecast();
  };
}

// A dry second period, so these cache tests turn on the first period alone and
// stay independent of the look-ahead window's width.
function okForecast(probability, shortForecast, temperature) {
  return {
    ok: true,
    json: async () => ({
      properties: {
        periods: [
          period(probability, shortForecast, temperature),
          period(0, 'Sunny', temperature),
        ],
      },
    }),
  };
}

test('serves a cached reading as stale while it is under the cap', async (t) => {
  t.mock.timers.enable({ apis: ['Date'] });
  const { getWeather } = await freshWeatherModule();

  let fail = false;
  stubFetch(t, nwsStub(() => {
    if (fail) throw new Error('simulated NWS outage');
    return okForecast(50, 'Chance Rain Showers', 68);
  }));

  const fresh = await getWeather(40.7785, -73.9821);
  assert.equal(fresh.temperature, 68);
  assert.equal(fresh.stale, false);

  // Past the 10 min TTL so the next call refetches, but well under the 60 min cap.
  fail = true;
  t.mock.timers.tick(11 * 60 * 1000);

  const stale = await getWeather(40.7785, -73.9821);
  assert.equal(stale.temperature, 68, 'still the last good reading');
  assert.equal(stale.stale, true);
  assert.equal(stale.ageMs, 11 * 60 * 1000);
});

test('drops the reading entirely once it passes the staleness cap', async (t) => {
  t.mock.timers.enable({ apis: ['Date'] });
  const { getWeather } = await freshWeatherModule();

  let fail = false;
  stubFetch(t, nwsStub(() => {
    if (fail) throw new Error('simulated NWS outage');
    return okForecast(50, 'Chance Rain Showers', 68);
  }));

  await getWeather(40.7785, -73.9821);

  fail = true;
  t.mock.timers.tick(61 * 60 * 1000);

  // null rather than an hour-old droplet the sign would render as current.
  assert.equal(await getWeather(40.7785, -73.9821), null);
});

test('a reading exactly at the cap is dropped', async (t) => {
  // Pins `ageMs < MAX_STALE_MS` against a drift to `<=`. 60 min on the dot is
  // the only input that tells the two apart.
  t.mock.timers.enable({ apis: ['Date'] });
  const { getWeather } = await freshWeatherModule();

  let fail = false;
  stubFetch(t, nwsStub(() => {
    if (fail) throw new Error('simulated NWS outage');
    return okForecast(50, 'Chance Rain Showers', 68);
  }));

  await getWeather(40.7785, -73.9821);

  fail = true;
  t.mock.timers.tick(60 * 60 * 1000);

  assert.equal(await getWeather(40.7785, -73.9821), null);
});

test('a reading one tick under the cap is still served', async (t) => {
  t.mock.timers.enable({ apis: ['Date'] });
  const { getWeather } = await freshWeatherModule();

  let fail = false;
  stubFetch(t, nwsStub(() => {
    if (fail) throw new Error('simulated NWS outage');
    return okForecast(50, 'Chance Rain Showers', 68);
  }));

  await getWeather(40.7785, -73.9821);

  fail = true;
  t.mock.timers.tick(60 * 60 * 1000 - 1);

  const stale = await getWeather(40.7785, -73.9821);
  assert.equal(stale.temperature, 68);
  assert.equal(stale.stale, true);
});

test('returns null when a fetch has never succeeded', async (t) => {
  const { getWeather } = await freshWeatherModule();
  stubFetch(t, async () => { throw new Error('simulated NWS outage'); });

  assert.equal(await getWeather(40.7785, -73.9821), null);
});

// --- getWeather: the periods handoff ---------------------------------------

test('a wet later hour reaches the glyph through getWeather', async (t) => {
  // Pins the seam buildResult's own tests cannot reach: getWeather has to hand
  // over the whole periods array. A regression to buildResult([periods[0]])
  // would leave every window test above passing and silently restore the
  // original bug — a dry current hour hiding rain an hour out.
  //
  // The periods are the real NWS readings from 2026-08-27, the morning the bug
  // was reported: 07:00 was 1% / "Partly Sunny" while 08:00 had already gone
  // to 40% / "Chance Rain Showers".
  const { getWeather } = await freshWeatherModule();
  stubFetch(t, nwsStub(() => ({
    ok: true,
    json: async () => ({
      properties: {
        periods: [
          period(1, 'Partly Sunny', 72),
          period(40, 'Chance Rain Showers', 73),
          period(40, 'Chance Rain Showers', 76),
        ],
      },
    }),
  })));

  const result = await getWeather(40.7785, -73.9821);
  assert.equal(result.precip, 'rain');
  assert.equal(result.temperature, 72, 'temperature still reads the current hour');
});
