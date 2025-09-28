#!/usr/bin/env python3
"""
data_fetch.py

All remote data fetchers for weather, Blackhawks, MLB, etc.,
with resilient retries via a shared requests.Session.
"""

import datetime
import logging

import pytz
import requests

from http_client import NHL_HEADERS, get_session

from config import (
    OWM_API_KEY,
    ONE_CALL_URL,
    LATITUDE,
    LONGITUDE,
    NHL_API_URL,
    MLB_API_URL,
    MLB_CUBS_TEAM_ID,
    MLB_SOX_TEAM_ID,
    CENTRAL_TIME,
    OPEN_METEO_URL,
    OPEN_METEO_PARAMS,
)

# ─── Shared HTTP session ─────────────────────────────────────────────────────
_session = get_session()

# Track last time we received a 429 from OWM
_last_owm_429 = None

# -----------------------------------------------------------------------------
# WEATHER
# -----------------------------------------------------------------------------
def fetch_weather():
    """
    Fetch weather from OpenWeatherMap OneCall, falling back to Open-Meteo on errors
    or if recently rate-limited.
    """
    global _last_owm_429
    now = datetime.datetime.now()
    # If we got a 429 within the last 2 hours, skip OWM and fallback
    if _last_owm_429 and (now - _last_owm_429) < datetime.timedelta(hours=2):
        logging.warning("Skipping OpenWeatherMap due to recent 429; using fallback")
        return fetch_weather_fallback()

    try:
        params = {
            "lat": LATITUDE,
            "lon": LONGITUDE,
            "appid": OWM_API_KEY,
            "units": "imperial",
        }
        r = _session.get(ONE_CALL_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    except requests.exceptions.HTTPError as http_err:
        if r.status_code == 429:
            logging.warning("HTTP 429 from OWM; falling back and pausing OWM for 2h")
            _last_owm_429 = datetime.datetime.now()
            return fetch_weather_fallback()
        logging.error("HTTP error fetching weather: %s", http_err)
        return None

    except Exception as e:
        logging.error("Error fetching weather: %s", e)
        return None


def fetch_weather_fallback():
    """
    Fallback using Open-Meteo API for weather data.
    """
    try:
        r = _session.get(OPEN_METEO_URL, params=OPEN_METEO_PARAMS, timeout=10)
        r.raise_for_status()
        data = r.json()
        logging.debug("Weather data (Open-Meteo): %s", data)

        current = data.get("current_weather", {})
        daily   = data.get("daily", {})

        mapped = {
            "current": {
                "temp":        current.get("temperature"),
                "feels_like":  current.get("temperature"),
                "weather": [{
                    "description": weather_code_to_description(
                        current.get("weathercode", -1)
                    )
                }],
                "wind_speed":  current.get("windspeed"),
                "wind_deg":    current.get("winddirection"),
                "humidity":    (daily.get("relativehumidity_2m") or [0])[0],
                "pressure":    (daily.get("surface_pressure")   or [0])[0],
                "uvi":         0,
                "sunrise":     (daily.get("sunrise")  or [None])[0],
                "sunset":      (daily.get("sunset")   or [None])[0],
            },
            "daily": [{
                "temp": {
                    "max": (daily.get("temperature_2m_max") or [None])[0],
                    "min": (daily.get("temperature_2m_min") or [None])[0],
                },
                "sunrise": (daily.get("sunrise") or [None])[0],
                "sunset":  (daily.get("sunset")  or [None])[0],
            }],
        }
        return mapped

    except Exception as e:
        logging.error("Error fetching fallback weather: %s", e)
        return None


def weather_code_to_description(code):
    mapping = {
        0:  "Clear sky",     1: "Mainly clear",  2: "Partly cloudy", 3: "Overcast",
        45: "Fog",           48: "Rime fog",     51: "Light drizzle", 53: "Mod. drizzle",
        55: "Dense drizzle", 61: "Slight rain",  63: "Mod. rain",     65: "Heavy rain",
        80: "Rain showers",  81: "Mod. showers", 82: "Violent showers",
        95: "Thunderstorm",  96: "Thunder w/ hail", 99: "Thunder w/ hail"
    }
    return mapping.get(code, f"Code {code}")


# -----------------------------------------------------------------------------
# NHL — Blackhawks
# -----------------------------------------------------------------------------
def fetch_blackhawks_next_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        fut   = [g for g in games if g.get("gameState") == "FUT"]

        for g in fut:
            if not g.get("startTimeCentral"):
                utc = g.get("startTimeUTC")
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                else:
                    g["startTimeCentral"] = "TBD"

        fut.sort(key=lambda g: g.get("gameDate", ""))
        return fut[0] if fut else None

    except Exception as e:
        logging.error("Error fetching next Blackhawks game: %s", e)
        return None


def fetch_blackhawks_next_home_game():
    try:
        next_game = fetch_blackhawks_next_game()
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        home  = []

        for g in games:
            if g.get("gameState") != "FUT":
                continue
            team = g.get("homeTeam", {}) or g.get("home_team", {})
            name = (team.get("commonName") or team.get("name", "")).lower()
            if name == "blackhawks" and (not next_game or g["gameDate"] != next_game["gameDate"]):
                utc = g.get("startTimeUTC")
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                else:
                    g["startTimeCentral"] = "TBD"
                home.append(g)

        home.sort(key=lambda g: g.get("gameDate", ""))
        return home[0] if home else None

    except Exception as e:
        logging.error("Error fetching next home Blackhawks game: %s", e)
        return None


def fetch_blackhawks_last_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        data  = r.json()
        games = []

        if "dates" in data:
            for di in data["dates"]:
                games.extend(di.get("games", []))
        else:
            games = data.get("games", [])

        offs = [g for g in games if g.get("gameState") == "OFF"]
        if offs:
            offs.sort(key=lambda g: g.get("gameDate", ""))
            return offs[-1]
        return None

    except Exception as e:
        logging.error("Error fetching last Blackhawks game: %s", e)
        return None


def fetch_blackhawks_live_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        for g in games:
            state = g.get("gameState", "").lower()
            if state in ("live", "in progress"):
                if not g.get("startTimeCentral"):
                    utc = g.get("startTimeUTC")
                    if utc:
                        dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                        dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                        g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                    else:
                        g["startTimeCentral"] = "TBD"
                return g
        return None

    except Exception as e:
        logging.error("Error fetching live Blackhawks game: %s", e)
        return None


# -----------------------------------------------------------------------------
# MLB — schedule helper + Cubs/Sox wrappers
# -----------------------------------------------------------------------------
def _fetch_mlb_schedule(team_id):
    try:
        today = datetime.datetime.now(CENTRAL_TIME).date()
        start = today - datetime.timedelta(days=3)
        end   = today + datetime.timedelta(days=3)

        url = (
            f"{MLB_API_URL}"
            f"?sportId=1&teamId={team_id}"
            f"&startDate={start}&endDate={end}&hydrate=team,linescore"
        )
        r = _session.get(url, timeout=10)
        r.raise_for_status()
        data   = r.json()
        result = {"next_game": None, "live_game": None, "last_game": None}
        finished = []

        for di in data.get("dates", []):
            day = datetime.datetime.strptime(di["date"], "%Y-%m-%d").date()
            for g in di.get("games", []):
                # Convert UTC to Central
                utc = g.get("gameDate")
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                else:
                    g["startTimeCentral"] = "TBD"

                # Determine game state
                status      = g.get("status", {})
                code        = status.get("statusCode", "").upper()
                abstract    = status.get("abstractGameState", "").lower()
                detailed    = status.get("detailedState", "").lower()

                # Live game
                if code == "I" or abstract == "live" or "progress" in detailed:
                    result["live_game"] = g

                # Next game (today scheduled)
                if day == today and (code == "S" or abstract in ("preview","scheduled")):
                    result["next_game"] = g

                # Finished up to today
                if day <= today and code not in ("S","I") and abstract not in ("preview","scheduled","live"):
                    finished.append(g)

        # Fallback next future
        if not result["next_game"]:
            for di in data.get("dates", []):
                day = datetime.datetime.strptime(di["date"], "%Y-%m-%d").date()
                if day > today:
                    for g in di.get("games", []):
                        status   = g.get("status", {})
                        code2    = status.get("statusCode", "").upper()
                        abs2     = status.get("abstractGameState", "").lower()
                        if code2 == "S" or abs2 in ("preview","scheduled"):
                            result["next_game"] = g
                            break
                    if result["next_game"]:
                        break

        # Pick last finished
        if finished:
            finished.sort(key=lambda x: x.get("officialDate",""))
            result["last_game"] = finished[-1]

        return result

    except Exception as e:
        logging.error("Error fetching MLB schedule for %s: %s", team_id, e)
        return {"next_game": None, "live_game": None, "last_game": None}


def fetch_cubs_games():
    return _fetch_mlb_schedule(MLB_CUBS_TEAM_ID)


def fetch_sox_games():
    return _fetch_mlb_schedule(MLB_SOX_TEAM_ID)


# -----------------------------------------------------------------------------
# MLB — standings helper + Cubs/Sox wrappers
# -----------------------------------------------------------------------------
def _fetch_mlb_standings(league_id, division_id, team_id):
    try:
        url = (
            "https://statsapi.mlb.com/api/v1/standings"
            f"?season=2025&leagueId={league_id}&divisionId={division_id}"
        )
        r = _session.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        for rec in data.get("records", []):
            for tr in rec.get("teamRecords", []):
                if tr.get("team", {}).get("id") == int(team_id):
                    return tr

        logging.warning("Team %s not found in standings (L%d/D%d)", team_id, league_id, division_id)
        return None

    except Exception as e:
        logging.error("Error fetching standings for team %s: %s", team_id, e)
        return None


def fetch_cubs_standings():
    return _fetch_mlb_standings(104, 205, MLB_CUBS_TEAM_ID)


def fetch_sox_standings():
    return _fetch_mlb_standings(103, 202, MLB_SOX_TEAM_ID)
