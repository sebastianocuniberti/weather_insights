# Weather Insights 🌤️

A Streamlit app that tracks the weather in the cities you care about, **builds its own history**
from every fetch (the free OpenWeatherMap tier only gives current conditions), and turns that
history into analytics you can actually use.

**Who it's for:** travellers, remote workers and exchange students deciding *where to go*.
Instead of checking cities one by one in a phone app, they describe the weather they want and
get every tracked city ranked by how well it fits, with air quality and daylight included.
Our own history of observations (the free API has none) is the part competitors don't have,
and it's downloadable as CSV for anyone who wants to buy or reuse the data.

- **Home** — who it's for, when the data was last updated, the top 3 matches right now for a
  chosen profile, a world map of all cities (temperature, comfort, PM2.5 or daylight), plain-
  language headlines ("Coldest capital: Ulaanbaatar, −10 °C") and CSV downloads.
- **Find my city** — set a temperature range, maximum humidity, air quality, sky and minimum
  daylight (or start from a profile: remote work, beach break, sightseeing, snow trip). Every
  city gets a 0-100 match score with a one-line reason, on a map and in a downloadable table.
- **City profile** — one city's latest conditions, how it ranks worldwide ("cleaner air than
  85 % of tracked cities"), its logged history, how often it's clear or rainy, and its 5-day
  forecast with the best time to go outside, all in the city's local time.
- **Live Conditions** — current weather for your tracked cities, warmest first, with a comfort
  score and the change since the last logged observation. One button fetches all five **city
  sets** (262 cities, including every national capital) in batches, with air quality,
  pausing automatically to respect the free API limit (about 10 minutes).
- **Compare Locations** — rank cities by any metric, filter by continent, compare continent
  averages, spot the hottest / coldest / windiest / most comfortable place right now, and see
  temperature vs humidity at a glance.
- **Air & Sky** — air quality ranking (PM2.5, AQI), daylight vs latitude, how often each city
  is clear / cloudy / rainy, and how much warmer days are than nights.
- **Analysis Sets** — themed comparisons: *Continents*, *World capitals*, *Hot vs cold*, *Humid vs dry*,
  *Hemispheres* (same latitude, opposite seasons) and *Spain vs Madrid*. For each: group
  averages, every city ranked and coloured by group, group averages per fetch round over time,
  and for Spain each city's difference from Madrid.
- **Trends** — any metric over time for several cities, plus each city's daily min → max
  temperature range.
- **5-Day Forecast** — OpenWeatherMap's free 3-hourly forecast: temperature vs feels-like,
  chance of rain, a day-by-day outlook and the best time to go outside. Shown only, never logged.
- **How it works** — what each derived metric means and how it is computed.
- **About & plans** — the problem we solve, who it is for, live numbers from our history,
  the Free / Pro / Business plans and the roadmap.

## Setup

You need [uv](https://docs.astral.sh/uv/) and a free [OpenWeatherMap API key](https://home.openweathermap.org/api_keys)
(new keys can take up to 2 hours to activate).

```bash
git clone <this-repo-url>
cd weather-insights
uv sync
cp variables.env.example variables.env     # Windows: copy variables.env.example variables.env
```

Open `variables.env` and replace `your_key_here` with your key. This file is in `.gitignore` —
**never commit it**.

## Run the app

```bash
uv run streamlit run app.py
```

Pick a city in the sidebar (e.g. `Valencia,ES` — the country code helps with ambiguous names),
then press **Fetch now** on *Live Conditions*. Each successful fetch is appended to
`data/weather_log.csv`; the *Compare* and *Trends* views read from that file.

### Logging without opening the app

```bash
uv run python scripts/collect.py Madrid,ES Venice,IT
uv run python scripts/collect.py --continent Europe Asia
uv run python scripts/collect.py --set "Hot vs cold"
uv run python scripts/collect.py --set all          # all 6 sets: 262 cities + air quality, ~10 min
uv run python scripts/collect.py --set all --no-air # weather only, ~5 min
```

Add the country code (`Venice,IT`): without it the API may pick a namesake (Venice, Florida).
Remember to commit `data/weather_log.csv` afterwards.

## Run the tests

```bash
uv run pytest
```

The tests use hand-made data and a fake HTTP session, so they need **no API key and no internet**.

## Project structure

```
.
├── app.py                        # Streamlit entry point (5 views)
├── scripts/collect.py            # CLI: fetch + log cities or whole continents (argparse)
├── src/weather_app/
│   ├── config.py                 # loads variables.env with python-dotenv
│   ├── exceptions.py             # one exception class per failure mode
│   ├── client.py                 # APIClient (generic) -> OpenWeatherClient (specific)
│   ├── models.py                 # WeatherSnapshot, AirQuality, ForecastPoint, Forecast
│   ├── storage.py                # WeatherLog: append/load the CSV history
│   ├── regions.py                # continent + analysis-set presets, batch planning
│   ├── matching.py               # CityPreferences + match_cities(): the "Find my city" score
│   └── analytics.py              # trend / comparison / derived-metric views
├── data/weather_log.csv          # our accumulated history (committed on purpose)
├── tests/                        # pytest suite
├── PROMPTS.md                    # AI collaboration log
├── pyproject.toml
└── variables.env.example         # template — copy to variables.env
```

## Design notes

| Requirement | Where |
|---|---|
| Inheritance with a real reason | `APIClient` handles requests, timeouts and HTTP status codes for *any* JSON API; `OpenWeatherClient` only adds the endpoints, the key's parameter name (`appid`) and the JSON parsing — its `current()` and `forecast()` both reuse the inherited `_get()`. `ForecastPoint(WeatherSnapshot)` reuses comfort index, km/h wind and temperature sorting, adding only rain chance/amount. |
| Encapsulation | `__api_key` is name-mangled so only `APIClient` can read it and it never appears in `repr()`; `_get`, `_handle_error`, `_auth_param_name` are protected hooks the subclass uses/overrides; `base_url`, `timeout`, `current()`, `fetch_many()` are public. |
| Special methods | `AirQuality.__lt__` (cleanest air first), `WeatherSnapshot.__lt__` (so `sorted()` orders by temperature), `__eq__`/`__hash__` (same city + same observation time = duplicate), `__str__`/`__repr__`; `WeatherLog.__len__`; `Forecast.__len__`/`__iter__`. |
| `@property` | `comfort_index`, `comfort_label`, `feels_like_delta`, `wind_kmh`, `label`, `rain_chance_pct`, `Forecast.warmest`/`coldest`, `daylight_hours`, `local_time`, `is_daytime`, `AirQuality.label`. |
| Specific error handling | `InvalidInputError` (checked *before* calling the API), `LocationNotFoundError` (404), `InvalidAPIKeyError` (401), `RateLimitError` (429), `APIServiceError` (timeout, no connection, 5xx). |
| Rate limiting | `APIClient` (base class, so any provider gets it) never makes more than `max_calls_per_minute` requests in 60 s; `OpenWeatherClient` sets 55 (free limit 60). Recent request times are kept in the private `__call_times`. |
| Graceful multi-city fetch | `OpenWeatherClient.fetch_many()` returns the good snapshots plus a dict of per-city errors — so "Fetch all continents" (42 cities) still loads 41 if one fails. |
| Log upgrades | New columns are only ever added at the end of `WeatherSnapshot.FIELDS`; `WeatherLog._upgrade_columns()` rewrites an older log once with the new header, leaving old values untouched and new columns empty. |
| Analytics | Trend: `trend()`, `daily_summary()`. Comparison: `rank_locations()`, `extremes()`, `continent_summary()`, `set_comparison()`, `difference_vs_reference()`; set trend: `set_trend()` (one point per fetch round). Derived: comfort index, feels-like gap, daily range, match score (`matching.py`). Insights: `headline_insights()`, `city_standing()`, `biggest_changes()`, `last_updated()`. Forecast: `forecast_daily_outlook()`, `best_time_outside()`. Air & sky: `conditions_mix()`, `air_quality_ranking()`, `day_night_difference()`; derived daylight hours, local hour, day/night, hemisphere. |

**Match score (0-100):** weighted average of temperature (40 %, best at the middle of the
chosen range, −10 points per °C outside it), humidity (15 %), air quality (20 %), sky (15 %)
and daylight (10 %); parts the user doesn't mind are left out, missing data counts as half.
`CityPreferences` is a frozen dataclass that validates its input (`InvalidInputError`) and has
a readable `__str__`.

**Comfort index (0-100):** start at 100, minus 3 per °C away from 21 °C, minus 0.5 per % humidity
outside 40-60 %, minus 4 per m/s of wind above 3 m/s; clipped to 0-100.

## Business case

**The problem.** Weather apps show one city at a time and only today. Someone deciding *where*
to go has to open ten tabs, and still can't tell whether a city is usually like this or just
lucky today. Air quality and daylight are hidden in other apps, if they're shown at all.

**Who it's for.**
- *Traveller:* "Where in Europe will it be sunny and 20-25 °C this weekend?"
- *Remote worker:* "Which city has mild weather, clean air and long days right now?"
- *Exchange student:* "How do these partner cities really compare, day after day?"

**What makes us different.** We keep our own history of observations (the free API has none),
compare 260+ cities at once, show air quality and daylight next to the temperature, and give
every city a 0-100 match score. The *About & plans* page shows the live numbers.

**Plans.**

| Plan | Price | Includes |
|---|---|---|
| Free | €0 | Home, Find my city with the preset profiles, latest conditions |
| Pro | €4 / month | Full history and trends, city profiles, forecast, Head to head, Trip planner, alerts |
| Business | from €99 / month | Data downloads and API access for travel agencies, relocation firms and universities |

**Roadmap.** Automatic data collection several times a day, weather and air-quality alerts,
more cities (beach towns, ski resorts, university cities) and a mobile-friendly layout.

## Team

- Sebastiano Cuniberti — repository setup, API client, data model, analytics and integration
- _Teammate 1_ — Head to head page: compare two cities side by side
- Daniel Rodriguez — Trip planner: best city and day in the next 5 days, from the forecast
- Daniella Jimenez — Business case: About & plans page and this README section
- _Teammate 4_ — Data quality and testing: city name fixes, error checks, comfort index test
