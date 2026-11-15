# AI collaboration log

One entry per feature/class we asked an AI agent to help with, in the order we worked on them.
Kept running as we go — not reconstructed at the end.

Tool used: **Claude (Anthropic), Opus 5.5, in the claude.ai app** (from 15 Nov also in
Claude Code inside VS Code).

**Teammates' AI sessions** are logged in their own files in [`prompts/`](prompts/), one file per
task (e.g. `prompts/head_to_head.md`), using the same format as the entries below — so several
people can log work at the same time without editing this file.

---

## Feature: first working version of the whole project (session 1)

**Asked (Sebastiano, 31 Oct 2026):** "I would like to start with this project. I am relatively new to
how to use GitHub. I have an account but still need to create the repository and add my team mates.
I have uploaded the group work that needs to be done. I have also included all the notes from
session 1 to session 16. In theory I would like to code using the materials I have but also having
new code which you think is appropriate is fine."
(Claude was given the assignment README, `summary.md`, the starter template and our class notebooks.)

**Got:** a complete first version built on the starter template:
- `exceptions.py` — one exception class per failure mode (new compared to class: we used plain
  `ValueError` in s13; separate classes let the app react differently to each problem).
- `client.py` — `APIClient` → `OpenWeatherClient`, extended from the s13 `CityWeather` pattern and
  `summary.md` §1; `validate_city_name()` with a regex (s05/s06 material); `fetch_many()` batch loop.
- `models.py` — `WeatherSnapshot` with `from_api()`, properties and special methods; comfort index
  written with numpy so it works on single values and pandas columns.
- `storage.py` — `WeatherLog` CSV log that skips duplicate observations.
- `analytics.py` — `trend`, `daily_summary`, `latest_by_location`, `rank_locations`, `extremes`,
  `add_derived_metrics`, `change_vs_previous`.
- `app.py` — 4-view Streamlit app with Plotly charts (s16 style).
- `scripts/collect.py` — argparse CLI (s14 style).
- `tests/` — 44 pytest tests using a fake HTTP session (no key/network needed).

**Changes from the starter template:** `config.py` no longer raises at import time — it exposes
`get_api_key()` so the app shows a friendly message instead of crashing when the key is missing,
and tests can import the package without a key.

**Checked:**
- Claude ran `uv run pytest` (44 passed) and a Streamlit `AppTest` smoke test of all 4 views.
- TODO (team): run the app with a real key, try a bad city ("Atlantis"), an empty field, a wrong
  key, and turning wifi off — confirm each shows its own message.
- TODO (team): verify the comfort index by hand for one city.

**Kept as-is / changed / rejected:** _to fill in after the team has reviewed it._

---

## Feature: 5-day forecast page and automatic logging (session 1, continued)

**Asked (Sebastiano, 31 Oct 2026):** "I would like to create a button that fetches all the data
there is from the API because I have the free version and can only take data of today."
Claude checked OpenWeatherMap's pricing page: historical data is not on the free plan, but the
5-day / 3-hour forecast is. It suggested (a) a forecast page and (b) automatic logging so the
history builds up without remembering to fetch. Sebastiano asked for both.

**Got:**
- `ForecastPoint(WeatherSnapshot)` and `Forecast` in `models.py` (subclass reuses comfort index,
  km/h wind and `__lt__`; `Forecast` has `__len__`, `__iter__`, `warmest`/`coldest`).
- `OpenWeatherClient.forecast()` in `client.py`, reusing the inherited `_get()`.
- `forecast_daily_outlook()` and `best_time_outside()` in `analytics.py`.
- A "5-Day Forecast" page in `app.py` (2 charts, day-by-day table, cached for 10 minutes).
- A guard in `WeatherLog.append()` so forecasts can never be logged as observations.
- `--every HOURS` option in `scripts/collect.py` for automatic logging.
- `tests/test_forecast.py` (9 tests).

**Checked:**
- Claude ran `uv run pytest` (53 passed) and a Streamlit `AppTest` of the new page with a fake
  forecast and with a missing key.
- TODO (team): open the forecast page with the real key for 2-3 cities and compare a few values
  with openweathermap.org.

**Kept as-is / changed / rejected:** _to fill in after the team has reviewed it._
**Later removed (31 Oct):** the `--every HOURS` automatic-logging option — see the next entry.

---

## Feature: continent presets and scheduled automatic logging (session 1, continued)

**Asked (Sebastiano, 31 Oct 2026):** "I would like to create a button that instead of me
selecting each city to fetch data from it will fetch all the data for each continent and
something that will make my computer fetch data automatically every 3 hours."
Claude explained the API has no "whole continent" request (one city per call), so a continent
is a preset list of major cities.

**Got:**
- `src/weather_app/regions.py`: 7 preset cities for each of 6 continents (42 total, under the
  free limit of 60 calls/minute) and a country-code → continent lookup.
- `fetch_many(..., on_progress=...)` callback in `client.py` for a progress bar.
- `add_derived_metrics()` now adds a `continent` column; new `continent_summary()` in `analytics.py`.
- App: "Fetch all continents" button with progress bar, "Add a whole continent" in the sidebar,
  continent filter + continent-average chart on Compare Locations.
- `scripts/collect.py --continent ...` and `scripts/schedule.py` (install / status / remove a
  cron job that runs every N hours; logs to `logs/collect.log`, which is git-ignored).
- `tests/test_continents.py` (9 tests; the cron tests never touch the real crontab).

**Checked:**
- Claude ran `uv run pytest` (62 passed), a Streamlit `AppTest` of both fetch buttons and the
  Compare page with fake data, and `schedule.py` install/status/remove against a stand-in
  `crontab` command (it keeps other cron jobs untouched).

**Kept as-is / changed / rejected:**
- Continent presets, progress bar and continent analytics: kept (team review pending).
- **Rejected the automatic logging.** Sebastiano decided he did not want his computer fetching
  data on a schedule. Asked Claude: "Actually I don't want my computer to automatic logging every
  3 hours anymore, could you delete the things related to that function." Claude removed
  `scripts/schedule.py`, its tests, the `logs/` entry in `.gitignore`, the `--every` option of
  `collect.py` and the matching README sections. The schedule had never been installed, so
  nothing had to be cleaned up on the Mac. Data is now collected only by fetching manually
  (app buttons or `scripts/collect.py`).

---

## Feature: analysis sets fetched in rate-limited batches (session 1, continued)

**Asked (Sebastiano, 31 Oct 2026):** "I would like to record as much data as I can with the
limitations [...] every time I do a manual fetch I would collect 60 cities the first minute,
let's say the continents, then the next minute another 60 cities [...] helpful for example for
this analysis: hot vs cold, humid vs dry, the two hemispheres, Spanish cities vs Madrid."
Before this, Claude explained the trade-offs (60 requests/min, 1M/month, the CSV living in GitHub)
and Sebastiano chose manual fetching about 5 times a day.

**Got:**
- `regions.py`: four themed sets, each split into labelled groups (Hot/Cold, Humid/Dry,
  North/South, Madrid/Rest of Spain); `plan_batches()` makes one batch per set and fetches a city
  shared by two sets only once (107 unique cities over 5 sets).
- A rate limiter in the **base** `APIClient` (`max_calls_per_minute`, private `__call_times`,
  `_wait_for_rate_limit()`); `OpenWeatherClient` uses 55/min. Instead of us timing "one batch per
  minute", the client pauses only when it actually needs to.
- `analytics.py`: `tag_set()`, `set_comparison()`, `fetch_rounds()`, `set_trend()`,
  `difference_vs_reference()`.
- App: "Fetch city sets" panel (choose sets, shows time estimate, progress per batch, pause
  message, saves after every batch) and a new **Analysis Sets** page (3 charts + summary).
- `collect.py --set NAME|all`.
- `tests/test_sets.py` (14 tests, including the rate limiter with a fake clock).

**Bugs found along the way (in our real data):**
- The default city "Venice" (no country code) was resolved by the API to Venice, Florida (US).
  Defaults now include country codes; the existing Venice, US rows are real observations and
  were left in the log.
- pandas reads Namibia's country code "NA" as missing data; `WeatherLog.load()` now only treats
  empty cells as missing.

**Checked:**
- Claude ran `uv run pytest` (72 passed) and an `AppTest` of all pages on a copy of our real log,
  with a fake API: 107 requests, exactly one automatic pause after 55, one failing city skipped.
- TODO (team): run "Fetch city sets" with the real key and note which preset cities (if any) the
  API doesn't recognise; fix their spelling in `regions.py`.

**Kept as-is / changed / rejected:** _to fill in after the team has reviewed it._

---

## Feature: World capitals, extra weather fields and air quality (session 1, continued)

**Asked (Sebastiano, 31 Oct 2026):** "Create a category that is all the cities the API has [...]
it has its own timer which would fetch only 55 every minute until it has taken all of the cities.
Also what does the API provide as data, because I feel we could collect more data per city."
Claude checked the OpenWeatherMap docs: the API knows 200,000+ locations but has no multi-city
request on the free plan, so one full pass would take ~61 hours, only ~5 passes fit in the
1M-requests/month cap, and each pass would add ~40 MB to a log that GitHub caps at 100 MB.
Claude suggested a World capitals set instead (the existing rate limiter already acts as the
"timer"), listed the response fields we weren't saving, and mentioned the free Air Pollution API.
Sebastiano: "Go ahead and add air quality too."

**Got:**
- `regions.py`: `WORLD_CAPITALS` (196 capitals, one per country, by continent); every capital's
  country now has a continent.
- `models.py`: 11 more fields from the same weather response (condition category, rain/snow last
  hour, wind gust/direction, visibility, sunrise/sunset, time zone, sea/ground pressure); new
  properties `daylight_hours`, `local_time`, `is_daytime`; new `AirQuality` class (`label`,
  `__lt__`, `from_api`).
- `client.py`: `air_quality(lat, lon)` and `fetch_many(..., with_air_quality=True)`; if only the
  air-quality request fails, the weather is kept.
- `storage.py`: `_upgrade_columns()` rewrites an older log once with the new header — old values
  untouched (checked cell by cell on a copy of our real log), new columns empty for old rows.
- `analytics.py`: new derived columns and `conditions_mix()`, `air_quality_ranking()`,
  `day_night_difference()`; new metrics selectable on every page.
- App: "Include air quality" checkbox with request count and time estimate, new **Air & Sky**
  page (4 charts), extra info on Live cards and table. `collect.py --no-air`.
- `tests/test_air_and_extra_fields.py` (18 tests).

**Checked:**
- Claude ran `uv run pytest` (90 passed) and an `AppTest` on a copy of our real log with a fake
  API: 262 cities, 524 requests, 9 automatic pauses, air-quality failures kept the weather, every
  page rendered. This found one real bug (no description for the new set on Analysis Sets), fixed.
- TODO (team): run one full fetch with the real key (~10 min), list any capitals the API doesn't
  recognise, and fix their spelling in `regions.py`.

**Kept as-is / changed / rejected:** _to fill in after the team has reviewed it._

---

## Feature: <short name>

**Asked:** <the actual prompt you gave the agent>

**Got:** <what file/function it produced>

**Checked:** <how you verified it — a hand-made test case, a comparison against a known value, etc.>

**Kept as-is / changed / rejected:** <which, and why>

---

## Feature: Home page, Find my city, City profiles, insights and CSV downloads (session 2)

**Asked (Sebastiano, 15 Nov 2026):** how to make the app interesting enough to sell, with the data
we have. Claude suggested turning it from a dashboard into a "where should I go" decision tool for
travellers, remote workers and exchange students, plus a world map, city profiles, a landing
section, plain-language insights and CSV downloads. Sebastiano asked for all of these (and skipped
scheduled automatic data collection, because the presentation is the next day).

**Got:**
- `matching.py` (new): `CityPreferences` frozen dataclass (validates input with
  `InvalidInputError`, readable `__str__`), 5 ready-made `PRESETS`, `match_cities()` giving every
  city a 0-100 match score and a one-line reason, `match_sentence()`.
- `analytics.py`: `last_updated()`, `city_standing()` ("cleaner air than 85 % of tracked
  cities"), `biggest_changes()`, `headline_insights()`.
- App: new **Home**, **Find my city** and **City profile** pages; world map (`scatter_geo`); CSV
  downloads of the full history, the latest snapshot, match results and one city's history.
- `app_pages/`: one file per teammate page, shown only once its `READY = True`, so teammates never
  edit `app.py` and a broken page can't crash the app. Task split in `TEAM_TASKS.md`.
- `tests/test_matching.py` (13 tests).

**Checked:**
- Claude ran `uv run pytest` (103 passed) and an `AppTest` of every page on our real log
  (4,596 observations, 261 cities), including the "View city profile" buttons and a real 5-day
  forecast for Tokyo shown in Tokyo time.
- First version of the match score gave 56 cities 100 %, so the temperature part was changed to
  peak at the middle of the chosen range; ties dropped to a handful.
- Found that Ngerulmud (Palau) failed in the 15 Nov fetch and that the API renames some cities
  (Tunis -> "Tunisia", Zagreb -> "Donji grad") — assigned to Teammate 4 in `TEAM_TASKS.md`.

**Kept as-is / changed / rejected:** _to fill in after the team has reviewed it._

