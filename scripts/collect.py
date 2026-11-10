"""Fetch current weather for some cities and append it to the history log.

Handy for building up history without opening the app (argparse, as in session 14):

    uv run python scripts/collect.py Madrid Venice London        # once
    uv run python scripts/collect.py --file cities.txt            # cities from a file
    uv run python scripts/collect.py --continent Europe Asia      # preset continent cities
    uv run python scripts/collect.py --continent all              # all 42 preset cities
    uv run python scripts/collect.py --set "Hot vs cold"          # one analysis set
    uv run python scripts/collect.py --set all                    # every set: 262 cities, ~10 min
    uv run python scripts/collect.py --set all --no-air           # skip air quality: ~5 min

Air quality is fetched too unless you pass --no-air (one extra request per city).
The client pauses automatically to stay under the free plan's 60 requests per minute.
"""

import argparse
import sys
from datetime import datetime

from weather_app.client import OpenWeatherClient
from weather_app.config import get_api_key
from weather_app.regions import CITY_SETS, CONTINENTS, cities_for, plan_batches
from weather_app.storage import WeatherLog

DEFAULT_CITIES = ["Madrid,ES", "Venice,IT", "London,GB", "Oslo,NO", "New York,US"]  # country codes avoid e.g. Venice, Florida


def parse_args():
    parser = argparse.ArgumentParser(description="Log current weather for a list of cities.")
    parser.add_argument("cities", nargs="*", help="City names (default: a built-in list)")
    parser.add_argument("--file", help="Text file with one city per line")
    parser.add_argument("--continent", nargs="+", metavar="NAME",
                        choices=list(CONTINENTS) + ["all"],
                        help=f"Add preset cities for these continents: {', '.join(CONTINENTS)}, or all")
    parser.add_argument("--set", nargs="+", metavar="NAME", dest="sets",
                        choices=list(CITY_SETS) + ["all"],
                        help=f"Add the cities of these sets: {', '.join(CITY_SETS)}, or all "
                             "(use quotes for names with spaces)")
    parser.add_argument("--no-air", action="store_true",
                        help="Don't fetch air quality (halves the number of requests)")
    return parser.parse_args()


def collect_once(client, log, cities, with_air_quality=True):
    """One round: fetch every city, print the results, append to the log."""
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M}] Fetching {len(cities)} cities...")
    snapshots, errors = client.fetch_many(cities, with_air_quality=with_air_quality)
    for snap in snapshots:
        print(f"  ✓ {snap}")
    for city, message in errors.items():
        print(f"  ✗ {city}: {message}", file=sys.stderr)
    written = log.append(snapshots)
    print(f"Logged {written} new observation(s). Total in log: {len(log)}.")
    return bool(snapshots)


def main():
    args = parse_args()
    cities = list(args.cities)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            cities += [line.strip() for line in f if line.strip()]
    if args.continent:
        cities += cities_for("all" if "all" in args.continent else args.continent)
    if args.sets:
        names = list(CITY_SETS) if "all" in args.sets else args.sets
        cities += [city for _, batch in plan_batches(names) for city in batch]
    # remove duplicates, keeping the first occurrence
    seen = set()
    cities = [c for c in cities if not (c.lower() in seen or seen.add(c.lower()))]
    cities = cities or DEFAULT_CITIES

    try:
        client = OpenWeatherClient(get_api_key())
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    client.on_wait = lambda secs: print(f"  ⏸ pausing {secs:.0f}s (free plan: 60 requests/minute)")
    log = WeatherLog()
    return 0 if collect_once(client, log, cities, with_air_quality=not args.no_air) else 1


if __name__ == "__main__":
    sys.exit(main())
