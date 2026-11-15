# AI collaboration log — Task 1, Head to head (Ahsan Shaik)

Tool used: **Claude (Anthropic), Opus 5.5, in Claude Code inside VS Code.**
Same format as [`PROMPTS.md`](../PROMPTS.md).

---

## Feature: head to head logic, page and tests (session 1)

**Asked (Ahsan, 15 Nov 2026):** "I took Task 1 (Head to head) in TEAM_TASKS.md, and I'm already on
the branch task-1-head-to-head. Build Task 1 exactly as TEAM_TASKS.md describes, changing only my
files: app_pages/head_to_head.py, src/weather_app/head_to_head.py, tests/test_head_to_head.py,
prompts/head_to_head.md. Explain each step in simple words, because I'm still learning pandas. Run
uv run pytest at the end. Don't commit yet; I want to check it first."

**Got:**
- `src/weather_app/head_to_head.py`:
  - `compare_two(df, city_a, city_b)`: takes each city's latest observation
    (`analytics.latest_by_location`) and returns one row per metric (temperature, feels like,
    humidity, wind, comfort, PM2.5, daylight) with columns `metric`, `unit`, `rule`, `a`, `b`,
    `winner`. Rules: higher comfort and daylight win; lower humidity, wind and PM2.5 win;
    temperature **and feels like** closest to 21 °C win. Each value is turned into a score where
    bigger is always better, rounded to 1 decimal, so equal values are a `"Tie"`. If either value
    is missing (e.g. no air-quality data) the winner is `"No data"`. An unknown city raises
    `InvalidInputError`.
  - `verdict(table)`: e.g. "Lisbon, PT wins 6 of 7 categories.", "It's a tie: both cities win
    2 of 7 categories.", with "(1 without data)" added when a category couldn't be scored.
- `app_pages/head_to_head.py`: two select boxes (default Madrid, ES vs Lisbon, PT), the verdict,
  each city's key numbers in two columns (`st.metric`: categories won, temperature + feels like,
  comfort, PM2.5, wind), the comparison table with the winner marked 🏆 and its value highlighted
  green, and a `px.line` chart of both cities' temperature from `analytics.trend`. Same city twice
  → a warning instead of a table; missing air data → "—" in the card, "no data" in the table and a
  note under the cards. `READY = True`.
- `tests/test_head_to_head.py`: 9 tests on a hand-made 4-city table (latest row is used, every
  rule, closer-to-21 beats a higher temperature, a 2-2 tie, missing PM2.5, same city twice, unknown
  city, empty table).

**Changes from the task description:** "feels like" uses the same closer-to-21 °C rule as
temperature (the task only names temperature). The same city picked twice is a valid input for
`compare_two` (all ties), but the page asks for two different cities instead of showing it.

**Checked:**
- Claude ran `uv run pytest` (all passed, 9 new) and a Streamlit `AppTest` smoke test of the page
  on the real log: Madrid vs Lisbon (verdict "Lisbon, PT wins 6 of 7 categories."), the same city
  twice (warning, no crash) and Lisbon with its air-quality data removed ("1 without data").
- Claude's first version of the tie test was not actually a tie (comfort went to Lisbon, 3-1);
  it printed the real values, changed the hand-made data and checked again.
- Ahsan ran the app (`uv run streamlit run app.py`), opened *Head to head* and compared
  Abu Dhabi, AE vs Dubai, AE. Abu Dhabi won temperature (28.0 vs 29.0 °C, closer to 21), comfort
  (77 vs 70) and wind (13 vs 17 km/h); Dubai won PM2.5 (21 vs 42 µg/m³). The verdict
  "Abu Dhabi, AE wins 5 of 7 categories" matched the table and the green highlights.

**Kept as-is / changed / rejected:** Kept as-is. I also accept the choice to judge "feels like" by
closeness to 21 °C, like temperature.
