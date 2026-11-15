# Team tasks — improving Weather Insights

Four tasks, one per person. **Each task only touches its own files**, so you can work at the
same time and merge in any order without breaking anything or getting merge conflicts.

> Write your name next to your task in the group chat. Sebastiano reviews and merges every
> pull request.

## Who owns which files

| Task | Owner | Files you may change or create | 
|---|---|---|
| 1. Head to head page | Teammate 1 | `app_pages/head_to_head.py`, `src/weather_app/head_to_head.py` *(new)*, `tests/test_head_to_head.py` *(new)*, `prompts/head_to_head.md` *(new)* |
| 2. Trip planner page | Teammate 2 | `app_pages/trip_planner.py`, `src/weather_app/trip_planner.py` *(new)*, `tests/test_trip_planner.py` *(new)*, `prompts/trip_planner.md` *(new)* |
| 3. Business case & About page | Teammate 3 | `app_pages/business.py`, `README.md`, `prompts/business.md` *(new)* |
| 4. Data quality & testing | Teammate 4 | `src/weather_app/regions.py`, `src/weather_app/analytics.py`, `PROMPTS.md`, `tests/test_data_quality.py` *(new)* |
| Integration | Sebastiano | `app.py`, `app_pages/__init__.py`, `TEAM_TASKS.md`, `matching.py`, `data/weather_log.csv`, `pyproject.toml`, `uv.lock` |

**Rules that keep things from breaking**

1. **Only change the files in your row.** If you think another file needs a change, ask its owner.
2. **Don't edit `app.py`.** Your page is already plugged in: it appears in the sidebar as soon as
   you set `READY = True` at the top of your page file. Leave it `False` until it works.
3. **Never `import app`** (importing it runs the whole app). Import what you need from
   `weather_app` instead, e.g. `from weather_app import analytics`.
4. **Don't add new packages** (no `uv add`). Changing `pyproject.toml` / `uv.lock` causes conflicts
   for everyone. We already have pandas, numpy, plotly and streamlit.
5. **Don't commit `data/weather_log.csv`** or `variables.env`. If you fetched data while testing,
   undo it before committing: `git checkout data/weather_log.csv`.
6. Your page's `show(history)` gets the logged history with all derived columns (`location`,
   `continent`, `comfort_index`, `aqi_label`, `daylight_hours`, …). Read it; don't modify it.

## How to work (same for everyone)

```bash
# once
git clone https://github.com/sebastianocuniberti/weather_insights.git
cd weather_insights
uv sync
cp variables.env.example variables.env      # then paste YOUR OWN OpenWeatherMap key in it

# if you already cloned it before: get the latest version first
git checkout main
git pull

# start your task on its own branch
git checkout -b task-1-head-to-head          # use your task's name

# ...work, then check nothing is broken:
uv run pytest
uv run streamlit run app.py

# save and send
git status                                   # only YOUR files should be listed
git add <your files>
git commit -m "feat: head to head page"
git push -u origin task-1-head-to-head
```

Then on GitHub click **Compare & pull request** and ask Sebastiano to review it. If he asks for
changes, commit again on the same branch and push: the pull request updates automatically.

**Before you push, check:** `uv run pytest` passes · the app opens and your page works ·
`git status` lists only your files · your AI session is logged in `prompts/<your task>.md`.

**Logging your AI use.** Copy the format of an entry in `PROMPTS.md` (*Asked / Got / Checked /
Kept as-is, changed or rejected*) into your own file in `prompts/`. Be honest about what you
checked and what you changed. Graders read this.

---

## Task 1 — Head to head page (Teammate 1)

**Goal:** pick two cities and see which one has better weather right now, side by side. Good
for "should I go to Lisbon or Barcelona?" in the demo.

1. In `src/weather_app/head_to_head.py`, write `compare_two(df, city_a, city_b)`. It should
   use each city's latest observation (`analytics.latest_by_location`) and return a DataFrame
   with one row per metric (temperature, feels like, humidity, wind, comfort, PM2.5, daylight):
   the value for A, the value for B, and which city is better. Decide what "better" means for each
   metric: higher comfort and daylight are better; lower PM2.5, wind and humidity are better;
   for temperature, closer to 21 °C is better.
2. Add `verdict(table)` that returns a sentence such as *"Lisbon, PT wins 5 of 7 categories"*.
3. In `app_pages/head_to_head.py`: two select boxes (default Madrid, ES vs another city), the two
   cities' key numbers in two columns (`st.metric`), the comparison table with the winner shown
   clearly, the verdict, and a chart of both cities' temperature over time
   (`analytics.trend(history, [a, b], "temperature")` + `plotly.express.line`).
4. Handle the same city picked twice, and a city with missing air-quality data.
5. In `tests/test_head_to_head.py`, test `compare_two` and `verdict` on a small hand-made table
   (copy the style of `tests/test_matching.py`), including a tie and missing data.
6. Set `READY = True`.

## Task 2 — Trip planner page (Teammate 2)

**Goal:** "I can travel in the next 5 days to one of these cities. Which city, and which day?"

1. In `src/weather_app/trip_planner.py`, write `plan_trip(forecasts)`. It takes a dict of
   `{city: forecast DataFrame}` (the table from `Forecast.to_dataframe()`: columns `time`,
   `temperature`, `rain_chance`, `rain_mm`, `comfort_index`, `description`, …) and returns one row
   per city per day with a **day score** (for example: average daytime comfort minus a penalty for
   rain chance; explain your formula in the docstring).
2. Add `best_choice(plan)` that returns the best (city, day) and a sentence like *"Go to Seville
   on Thursday: 24 °C, 0 % chance of rain, comfort 91"*.
3. In `app_pages/trip_planner.py`: a multiselect of up to 3 cities (from
   `history["location"]`), load each forecast with
   `OpenWeatherClient(get_api_key()).forecast(query)` wrapped in `@st.cache_data(ttl=600)`. Use
   the city's `query` column from `history`, e.g. `"Seville,ES"`. Then show a heatmap of city ×
   day coloured by day score (`px.imshow`), the recommendation sentence and a table.
4. Errors: catch `WeatherAppError` (and `RuntimeError` for a missing key) and show `st.warning`,
   like the City profile page does in `app.py`. One failing city should not hide the others.
5. In `tests/test_trip_planner.py`, test `plan_trip` and `best_choice` with hand-made forecast
   tables. No internet needed.
6. Set `READY = True`.

## Task 3 — Business case & About page (Teammate 3)

**Goal:** convince the audience someone would pay for this. This is the "could we sell it" part
of the presentation.

1. In `app_pages/business.py`, build an **About & plans** page:
   - **The problem:** weather apps show one city at a time and no history.
   - **Who it's for:** three short personas (traveller, remote worker, exchange student) with the
     question each one asks.
   - **What makes us different:** our own history, 260 cities, air quality and a match score.
     Show live numbers from `history`: cities, observations, days, and
     `analytics.last_updated(history)`.
   - **Plans:** e.g. Free (Home + Find my city), Pro (€3-5/month: full history, city profiles,
     alerts), Business (data/API access for travel agencies, relocation firms, universities).
     Use `st.columns` with a bordered container per plan.
   - **Roadmap:** automatic data collection several times a day, weather alerts, more cities,
     a mobile layout.
2. In `README.md`, add a **Business case** section (same content, shorter) and fill in the
   **Team** section with everyone's real name and their task. Ask each person for their
   one-line summary.
3. Set `READY = True`.
4. Optional, if time allows: write the presentation outline (who says what, and the demo order:
   Home → switch profile → City profile → Find my city → teammates' pages).

## Task 4 — Data quality & testing (Teammate 4)

**Goal:** the data and the docs are correct, and the open "TODO (team)" items in `PROMPTS.md`
are done. Graders check these.

1. **A capital that fails:** *Ngerulmud,PW* (Palau) is the one city that failed in the 15 Nov fetch.
   Find a name the API accepts (try `Melekeok,PW` or `Koror,PW` with
   `uv run python scripts/collect.py Melekeok,PW` and see which works). Then fix it in
   `regions.py` and undo the log change (`git checkout data/weather_log.csv`).
2. **Odd city names:** the API returns some cities under odd names, for example Tunis →
   "Tunisia", Zagreb → "Donji grad", Paramaribo → "Distrikt Paramaribo", Murmansk → "Murmansk
   Oblast". Make the app show the name we asked for: in `analytics.add_derived_metrics`, build
   `location` from the city part of the `query` column when it exists (title-cased), and fall
   back to the API's `city` when it doesn't. `location` is used as the key everywhere, so
   afterwards run `uv run pytest` and click through every page.
3. **Error checks** (open TODO in `PROMPTS.md`): run the app and try a fake city (`Atlantis`), an
   empty field, a wrong API key and wifi off. Write down the message each one shows in
   `PROMPTS.md`.
4. **Comfort index by hand:** pick one real row from the log, compute the comfort index on paper
   with the formula in the README, and turn it into a test in `tests/test_data_quality.py`.
   Add tests for steps 1 and 2 too.
5. **PROMPTS.md:** fill in the *"Kept as-is / changed / rejected"* lines with the team's real
   decisions, and replace the TODO items you've done with what you found.
