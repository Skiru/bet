#!/usr/bin/env python3
"""Fetch weather data for outdoor sport venues using Open-Meteo (free, no API key).

Usage:
    python3 scripts/fetch_weather.py --date 2026-04-30
    python3 scripts/fetch_weather.py --lat 51.5 --lon -0.1 --date 2026-04-30
    python3 scripts/fetch_weather.py --venues venues.json

Open-Meteo API: https://open-meteo.com/en/docs
Free tier: unlimited requests, no API key needed.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("[weather] requests not installed — run: pip install requests")
    sys.exit(1)

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Known venue coordinates for major football/outdoor sport venues
# Extend as needed — fallback to city coordinates
VENUE_COORDS = {
    # Football — major cities
    "london": (51.50, -0.13),
    "manchester": (53.48, -2.24),
    "liverpool": (53.40, -2.99),
    "madrid": (40.42, -3.70),
    "barcelona": (41.39, 2.17),
    "paris": (48.86, 2.35),
    "munich": (48.14, 11.58),
    "dortmund": (51.51, 7.45),
    "berlin": (52.52, 13.40),
    "rome": (41.90, 12.50),
    "milan": (45.46, 9.19),
    "turin": (45.07, 7.69),
    "amsterdam": (52.37, 4.90),
    "lisbon": (38.72, -9.14),
    "istanbul": (41.01, 28.98),
    "warsaw": (52.23, 21.01),
    "krakow": (50.06, 19.94),
    "wroclaw": (51.11, 17.04),
    "poznan": (52.41, 16.93),
    "vienna": (48.21, 16.37),
    "zurich": (47.38, 8.54),
    "brussels": (50.85, 4.35),
    "copenhagen": (55.68, 12.57),
    "stockholm": (59.33, 18.07),
    "oslo": (59.91, 10.75),
    "helsinki": (60.17, 24.94),
    "athens": (37.98, 23.73),
    "buenos aires": (34.60, -58.38),
    "sao paulo": (-23.55, -46.63),
    "rio de janeiro": (-22.91, -43.17),
    "mexico city": (19.43, -99.13),
    "bogota": (4.71, -74.07),
    "lima": (-12.05, -77.04),
    "santiago": (-33.45, -70.65),
    "tokyo": (35.68, 139.69),
    "seoul": (37.57, 126.98),
    # US cities
    "new york": (40.71, -74.01),
    "los angeles": (34.05, -118.24),
    "chicago": (41.88, -87.63),
    "boston": (42.36, -71.06),
    "denver": (39.74, -104.99),
    "miami": (25.76, -80.19),
    "phoenix": (33.45, -112.07),
    # Altitude venues (betting-relevant)
    "la paz": (-16.50, -68.15),
    "quito": (-0.18, -78.47),
}


def fetch_weather(lat: float, lon: float, date: str) -> dict | None:
    """Fetch weather forecast for a location on a date.

    Returns dict with temperature, wind, rain, humidity data.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,weathercode",
        "hourly": "temperature_2m,relativehumidity_2m,rain,windspeed_10m,weathercode",
        "start_date": date,
        "end_date": date,
        "timezone": "Europe/Warsaw",
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[weather] Error fetching weather for ({lat}, {lon}): {e}")
        return None

    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    # Extract key metrics
    result = {
        "date": date,
        "lat": lat,
        "lon": lon,
        "temp_max_c": _safe_first(daily.get("temperature_2m_max")),
        "temp_min_c": _safe_first(daily.get("temperature_2m_min")),
        "precipitation_mm": _safe_first(daily.get("precipitation_sum")),
        "wind_max_kmh": _safe_first(daily.get("windspeed_10m_max")),
        "weather_code": _safe_first(daily.get("weathercode")),
    }

    # Extract hourly data for match-time analysis
    if hourly:
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("windspeed_10m", [])
        rains = hourly.get("rain", [])
        result["hourly_temps"] = temps
        result["hourly_winds"] = winds
        result["hourly_rain"] = rains

    # Add weather description
    result["conditions"] = _weather_code_to_text(result.get("weather_code", 0))

    # Betting-relevant flags
    result["flags"] = []
    if result.get("precipitation_mm", 0) > 5:
        result["flags"].append("RAIN_HEAVY")
    elif result.get("precipitation_mm", 0) > 1:
        result["flags"].append("RAIN_LIGHT")
    if result.get("wind_max_kmh", 0) > 40:
        result["flags"].append("WIND_STRONG")
    elif result.get("wind_max_kmh", 0) > 25:
        result["flags"].append("WIND_MODERATE")
    if result.get("temp_max_c", 20) > 35:
        result["flags"].append("EXTREME_HEAT")
    if result.get("temp_min_c", 10) < 0:
        result["flags"].append("FREEZING")

    return result


def _safe_first(lst):
    """Safely get first element of a list."""
    if isinstance(lst, list) and lst:
        return lst[0]
    return None


def _weather_code_to_text(code) -> str:
    """Convert WMO weather code to text description."""
    if code is None:
        return "Unknown"
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
    }
    return codes.get(int(code), f"Code {code}")


def resolve_venue_coords(venue_name: str) -> tuple[float, float] | None:
    """Try to resolve a venue/city name to coordinates."""
    name_lower = venue_name.lower().strip()
    # Direct match
    if name_lower in VENUE_COORDS:
        return VENUE_COORDS[name_lower]
    # Partial match
    for key, coords in VENUE_COORDS.items():
        if key in name_lower or name_lower in key:
            return coords
    return None


def fetch_weather_for_fixtures(fixtures: list[dict], date: str) -> dict:
    """Fetch weather for a list of fixtures. Returns dict keyed by fixture description."""
    results = {}
    seen_coords = {}  # Cache to avoid duplicate API calls

    for fixture in fixtures:
        # Try to determine venue location
        home = fixture.get("home_team", "")
        competition = fixture.get("competition", "")
        sport = fixture.get("sport", "football")

        # Only fetch weather for outdoor sports
        outdoor_sports = {"football", "baseball", "speedway", "mma", "padel"}
        if sport not in outdoor_sports:
            continue

        # Try to resolve coordinates
        coords = None
        for name in [home, competition]:
            coords = resolve_venue_coords(name)
            if coords:
                break

        if not coords:
            continue

        # Cache-check
        coord_key = f"{coords[0]:.2f},{coords[1]:.2f}"
        if coord_key in seen_coords:
            results[f"{home} vs {fixture.get('away_team', '')}"] = seen_coords[coord_key]
            continue

        weather = fetch_weather(coords[0], coords[1], date)
        if weather:
            fixture_key = f"{home} vs {fixture.get('away_team', '')}"
            results[fixture_key] = weather
            seen_coords[coord_key] = weather

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch weather data for betting analysis")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--city", help="City name to resolve coordinates")
    parser.add_argument("--fixtures", help="Path to fixtures JSON file")
    args = parser.parse_args()

    # Validate date format
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.date):
        print(f"[weather] Invalid date format: {args.date} (expected YYYY-MM-DD)")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.lat and args.lon:
        result = fetch_weather(args.lat, args.lon, args.date)
        if result:
            print(json.dumps(result, indent=2))
    elif args.city:
        coords = resolve_venue_coords(args.city)
        if coords:
            result = fetch_weather(coords[0], coords[1], args.date)
            if result:
                print(json.dumps(result, indent=2))
        else:
            print(f"[weather] Could not resolve coordinates for: {args.city}")
    elif args.fixtures:
        fixtures_path = Path(args.fixtures)
        if not fixtures_path.exists():
            # Try default fixtures path
            fixtures_path = DATA_DIR / f"fixtures_{args.date}.json"
        if fixtures_path.exists():
            data = json.loads(fixtures_path.read_text(encoding="utf-8"))
            fixtures = data.get("fixtures", data) if isinstance(data, dict) else data
        else:
            print(f"[weather] Fixtures file not found: {fixtures_path}")
            fixtures = []
        if fixtures:
            results = fetch_weather_for_fixtures(fixtures, args.date)
            out_path = DATA_DIR / f"weather_{args.date}.json"
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[weather] Fetched weather for {len(results)} venues → {out_path}")
    else:
        # Default: DB-first, then JSON fallback
        fixtures = None
        try:
            from db_data_loader import load_fixtures_from_db
            db_fixtures = load_fixtures_from_db(args.date)
            if db_fixtures:
                print(f"[weather] DB: loaded {len(db_fixtures)} fixtures")
                fixtures = db_fixtures
        except Exception as e:
            print(f"[weather] DB read failed, falling back to JSON: {e}")

        if not fixtures:
            fixtures_path = DATA_DIR / f"fixtures_{args.date}.json"
            if fixtures_path.exists():
                data = json.loads(fixtures_path.read_text(encoding="utf-8"))
                fixtures = data.get("fixtures", [])
            else:
                print(f"[weather] No fixtures file found for {args.date}")
                fixtures = []

        if fixtures:
            results = fetch_weather_for_fixtures(fixtures, args.date)
            out_path = DATA_DIR / f"weather_{args.date}.json"
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[weather] Fetched weather for {len(results)} venues → {out_path}")


if __name__ == "__main__":
    main()
