# Fix the rain droplet over-triggering

## Context

`buildResult` in `server/lib/weather.js:41-50` decides the rain droplet with:

```js
rain = probability >= RAIN_PROB_THRESHOLD || RAIN_FORECAST_RE.test(forecastText)
```

The `||` makes the two signals independent, and NWS puts "Rain"/"Showers" into
`shortForecast` for probabilities as low as ~10%. So the regex fires well below
the 40% threshold and the threshold is effectively dead code for rain — it only
still matters for snow/sleet, which the regex doesn't match.

Confirmed against live NWS data for the configured lat/lon (`config.json:62-66`)
on 2026-08-21:

```
07:00  18%  thresh=False  regex=True  -> RAIN=True  | Slight Chance Rain Showers
08:00   4%  ...all remaining 23 hours Partly Sunny / Mostly Sunny / Partly Cloudy
```

The droplet was lit at 18% on an otherwise sunny day. During an unsettled
stretch NWS holds "Slight Chance Rain Showers" across many consecutive hours,
so the droplet stays on for hours through weather that never produces rain —
which reads as "stuck".

A second, smaller issue: the failure path (`weather.js:64-68`) returns the
cached reading with `stale: true` and **no maximum age**. It does keep retrying
every 30s so it self-heals, but during an NWS outage it serves an arbitrarily
old reading, and `stale` is only ever printed to the log (`display/main.py:361`)
— it has no visual effect, so an hours-old droplet looks identical to a fresh one.

Neither `buildResult` nor `getWeather` has any test coverage: `server/test/`
contains only `gtfs-fetcher.test.js`, and `display/test_weather.py` asserts
colors only.

## User Outcome

What the user experiences after this change is live:

- The droplet no longer appears for "Slight Chance" rain (below 30%). On a day
  like 2026-08-21 the sign shows the temperature with no droplet all day.
- The droplet still appears when rain is genuinely likely (NWS "Chance" or
  better, i.e. ≥30% with rain wording), and still appears for any precipitation
  at ≥40% regardless of wording — so snow/sleet keeps working as it does today.
- If NWS is unreachable for more than an hour, the temperature and droplet
  disappear from the sign entirely rather than showing a stale reading. Train
  rows are unaffected.

## Data Flow

```
NWS /points → forecastHourly → buildResult() → forecastCache (10 min TTL)
  → weatherCache (refreshAll, 30s) → GET /api/arrivals → display fetch_arrivals()
  → _compute_state_key() → draw_weather() → droplet glyph
```

Key handoff points where correctness matters:

1. **`buildResult` → `rain` boolean.** The only place the decision is made. Getting
   the gate wrong here silently changes what the sign shows; there is no
   downstream validation.
2. **`getWeather` failure path → `weatherCache`.** Must distinguish "no reading
   yet" (null) from "old reading" (stale). Returning `null` past the cap makes
   the weather vanish rather than lie.
3. **`weather: null` → `draw_weather`.** `display/main.py:354` already guards
   `if not weather or weather.get('temperature') is None: return`, and
   `_compute_state_key` (`main.py:149-150`) folds weather into the redraw key as
   `(None, None)`, so the droplet is correctly cleared on the next frame. No
   display-side change needed — verify, don't edit.

## Steps

### 1. Gate the text match on probability — `server/lib/weather.js`

Add a floor constant next to the existing threshold (weather.js:13-14):

```js
const RAIN_PROB_THRESHOLD = 40;  // text-independent: catches snow/sleet at any wording
const RAIN_TEXT_FLOOR = 30;      // NWS "Chance" boundary; below this is "Slight Chance"
```

Change the decision in `buildResult` to require the text match to clear the floor:

```js
const rain =
  probability >= RAIN_PROB_THRESHOLD ||
  (probability >= RAIN_TEXT_FLOOR && RAIN_FORECAST_RE.test(forecastText));
```

Update the file header comment, which currently describes the old behavior.

30% is chosen because it is NWS's documented boundary between "Slight Chance"
and "Chance" — not a midpoint — so the rule reads as "show the droplet when NWS
says at least a *chance* of rain."

### 2. Cap staleness — `server/lib/weather.js`

Add `const MAX_STALE_MS = 60 * 60 * 1000;` and apply it in the catch block:

```js
const ageMs = now - forecastCache.timestamp;
if (forecastCache.data && ageMs < MAX_STALE_MS) {
  return { ...forecastCache.data, stale: true, ageMs };
}
return null;
```

Separable from step 1 — drop this step if you'd rather keep the change to one concern.

### 3. Export `buildResult` and add tests — `server/test/weather.test.js` (new)

`buildResult` is pure, so export it and test the decision table directly. Follow
the existing style in `gtfs-fetcher.test.js`: `node:test` + `node:assert/strict`,
`globalThis.fetch` swapped and restored via `t.after`.

Cases, keyed to the real NWS shapes seen in the live fetch:

| probability | shortForecast              | expected |
|-------------|----------------------------|----------|
| 18          | Slight Chance Rain Showers | false — the bug |
| 30          | Chance Rain Showers        | true  |
| 65          | Rain Showers Likely        | true  |
| 80          | Snow                       | true — threshold path, no text match |
| 45          | Partly Cloudy              | true — threshold path |
| 25          | Partly Cloudy              | false |
| null → 0    | Slight Chance Rain Showers | false — `?? 0` coercion |

For step 2, one test with `t.mock.timers.enable({ apis: ['Date'] })`: seed a
success, fail the next fetch, advance past `MAX_STALE_MS`, assert `null`. Requires
Node ≥20.4 — the Pi installs Node 20.x (`scripts/setup-pi.sh:45`) and local is
v22.22.0, so both are fine.

Note: `pointsCache` and `forecastCache` are module-level, so tests touching
`getWeather` share state. Order the `getWeather` tests so the cache is seeded
before the failure cases, or import the module fresh per test.

### 4. Reconciliation

Compare implemented work against steps 1-3 and note each as Done / Adjusted /
Deferred / Skipped. Present the summary.

## Verification

1. `cd server && npm test` — new weather tests plus existing gtfs tests pass.
2. Live check against the real forecast, confirming the flag flips only where intended:
   ```
   node -e "import('./lib/weather.js').then(async m => console.log(await m.getWeather(40.7785, -73.9821)))"
   ```
   Against today's data this should report `rain: false` (18%, "Slight Chance
   Rain Showers") where the current code reports `rain: true`.
3. `curl -s localhost:3000/api/arrivals | python -m json.tool | grep -A4 weather`
   with the server running — confirm the `weather` block still has
   `temperature`/`unit`/`rain`/`stale` and the display's shape expectations
   (`main.py:354-379`) are unchanged.
4. No display-side change; confirm by reading that `draw_weather` and
   `_compute_state_key` already handle `weather: null`.

## Out of scope

- Distinguishing snow from rain in the glyph (a droplet is drawn for snow today
  and still will be) — flag as `// TODO(subway-sign):` if it comes up.
- Surfacing `stale` visually on the sign.

---

## Reconciliation (2026-08-21)

| Step | Status | Notes |
|------|--------|-------|
| 1. Gate the text match on probability | **Done** | `RAIN_TEXT_FLOOR = 30` added; decision is now `>=40 || (>=30 && regex)`. Header comment updated. |
| 2. Cap staleness | **Done** | `MAX_STALE_MS = 60 * 60 * 1000`; catch block computes `ageMs` once and returns `null` past the cap. |
| 3. Export `buildResult` + tests | **Done** | New `server/test/weather.test.js`, 15 tests. Suite is 17 total with the existing gtfs tests; all pass. |
| 4. Reconciliation | **Done** | This section. |

### Adjustments from the plan

- **Test isolation approach.** The plan offered "order the tests or import fresh
  per test". Chose fresh-import (`../lib/weather.js?fresh=N`) so each `getWeather`
  test gets its own `pointsCache`/`forecastCache` and the file has no
  order-dependence. No test-only reset hook was added to production code.
- **Extra decision-table cases.** Added 29% "Chance Rain Showers" (just under the
  floor) and 39% "Mostly Sunny" (just under the threshold) beyond the planned
  table, to pin both boundaries rather than only the bug case.

### Verification results

- `npm test` in `server/` — **17/17 pass**.
- Deletion test: 2 of the 9 decision-table cases fail against the old logic
  (18% and 29% with rain wording) — the tests are load-bearing, and the other 7
  confirm the threshold/snow paths were not regressed.
- Live NWS fetch for the configured lat/lon returned
  `{ temperature: 63, unit: 'F', rain: false, stale: false, ageMs: 0 }`, where the
  old code reported `rain: true` for the same 18% "Slight Chance Rain Showers" hour.
- `GET /api/arrivals` against a running server returned
  `{"temperature":63,"unit":"F","rain":false,"stale":false,"ageMs":0}` — shape
  unchanged, all four fields the display reads are present.
- Display-side handling of `weather: null` confirmed by reading, not editing:
  `display/main.py:354` guards the null case and `_compute_state_key`
  (`main.py:149-150`) folds it to `(None, None)`, so the droplet clears on the
  next frame. No display change was needed.

### Follow-ups not taken (as scoped)

- A droplet is still drawn for snow (`80% "Snow"` -> `rain: true`). Unchanged from
  before; the glyph does not distinguish precipitation type.
- `stale` remains log-only (`display/main.py:361`); it has no visual effect. The
  staleness cap makes this less pressing, since a reading can now only be up to
  an hour old.

---

# Follow-up: split precipitation type from likelihood

Continuation of the above in the same session. Plan:
`C:\Users\jense\.claude\plans\abundant-dancing-wilkes.md` (2nd plan, same file).

## Reconciliation (2026-08-21)

| Step | Status | Notes |
|------|--------|-------|
| 1. Classifier replaces two-trigger gate | **Done** | `classifyPrecip()` exported; single `PRECIP_THRESHOLD = 40`. `RAIN_PROB_THRESHOLD`/`RAIN_TEXT_FLOOR` removed. |
| 2. Snowflake glyph | **Done** | `_draw_snowflake` + `SNOW_COLOR = (200, 225, 255)`; `draw_weather` dispatches on `precip` via a lookup table; `_compute_state_key` updated. |
| 3. Tests | **Done** | `server/test/weather.test.js` rewritten: 47 tests. `display/test_weather.py` extended to 7. |
| 4. Docs | **Done** | `README.md:278`, plus `OPERATIONS.md:79,81-82,124` — note OPERATIONS.md is gitignored (`.gitignore:27`), so those edits are on disk but will never appear in a commit diff. |
| 5. Reconciliation | **Done** | This section. |

### Adjustments from the plan

- **Glyph dispatch shape.** Plan said "dispatch on it"; implemented as a
  `{precip: (drawFn, color)}` lookup with a `(None, None)` default rather than
  an if/elif chain, so adding a third symbol is one table row plus a glyph.
- **Extra doc fix.** Also corrected `OPERATIONS.md:80` to document the 60-minute
  staleness cap, which the previous change added but never documented.
- **Test count.** Plan sketched a 14-row table; shipped 26 classify cases + 10
  gate cases, all but the winter/fallback rows verbatim from the sample.

### Verification results

- `server`: **47/47 pass**. `display`: **7/7 pass**.
- **Full-corpus replay** (the load-bearing check): re-fetched all 22 locations,
  3,432 periods / 34 distinct wordings, through the real `classifyPrecip` and
  `buildResult`. At each wording's max observed PoP: 9 -> droplet, 9 -> snowflake,
  16 -> nothing. **Snow wordings >=40% not drawing a snowflake: none.**
- Fog: `"Areas Of Fog" @51% -> null`, `"Patchy Fog" @4% -> null` — the dry-list
  correctly beats the fallback above the gate.
- Mixed: `"Rain And Snow Showers Likely" @66% -> snow`.
- No-"Rain"-token: `"Showers And Thunderstorms" @92% -> rain`.
- Live `/api/arrivals`: `{"temperature":63,"unit":"F","precip":null,"stale":false,"ageMs":0}`
  — legacy `rain` key absent, confirmed programmatically.
- Consumer sweep for `rain` found only the string literal `'rain'` and comments.

### Known gap

The snowflake has **not** been seen on real hardware — there was no snow in the
NYC forecast to trigger it, and there is no matrix on the dev machine (tests run
in simulation mode). `SNOW_COLOR` is unit-tested for distinctness and dim
survival; the 5x5 **pattern itself has no test at all** and was checked only by
ASCII preview (an earlier draft of this note claimed unit-test coverage for the
pattern — it never had any). Worth a look on the Pi the first time it renders,
and `SNOW_COLOR` may need tuning against the panel's actual output.
