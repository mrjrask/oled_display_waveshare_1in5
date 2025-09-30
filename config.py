# config.py

#!/usr/bin/env python3
import datetime
import glob
import os
import subprocess

import pytz
from PIL import ImageFont

# ─── Project paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR  = os.path.join(SCRIPT_DIR, "images")

# ─── Feature flags ────────────────────────────────────────────────────────────
ENABLE_SCREENSHOTS   = True
ENABLE_VIDEO         = False
VIDEO_FPS            = 30
ENABLE_WIFI_MONITOR  = True

WIFI_RETRY_DURATION  = 180
WIFI_CHECK_INTERVAL  = 60
WIFI_OFF_DURATION    = 180

VRNOF_CACHE_TTL      = 1800

def get_current_ssid():
    try:
        return subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip()
    except Exception:
        return None

CURRENT_SSID = get_current_ssid()

if CURRENT_SSID == "Verano":
    ENABLE_WEATHER = True
    OWM_API_KEY    = "48e7a54016d568a9712e62eef0e47830"
    LATITUDE       = 41.9103
    LONGITUDE      = -87.6340
    TRAVEL_MODE    = "to_home"
elif CURRENT_SSID == "wiffy":
    ENABLE_WEATHER = True
    OWM_API_KEY    = "1dddbb920891c2797fe01427f4500ecd"
    LATITUDE       = 42.13444
    LONGITUDE      = -87.876389
    TRAVEL_MODE    = "to_work"
else:
    ENABLE_WEATHER = True
    OWM_API_KEY    = "48e7a54016d568a9712e62eef0e47830"
    LATITUDE       = 41.9103
    LONGITUDE      = -87.6340
    TRAVEL_MODE    = "to_home"

GOOGLE_MAPS_API_KEY = "AIzaSyBcRMSzun06PSffz9FWjV1NZg9MkjtFNq8"

# ─── Display configuration ─────────────────────────────────────────────────────
WIDTH                    = 128
HEIGHT                   = 128
SPI_FREQUENCY            = 30_000_000
SCREEN_DELAY             = 4
SCHEDULE_UPDATE_INTERVAL = 600

# ─── API endpoints ────────────────────────────────────────────────────────────
ONE_CALL_URL      = "https://api.openweathermap.org/data/3.0/onecall"
OPEN_METEO_URL    = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PARAMS = {
    "latitude":        LATITUDE,
    "longitude":       LONGITUDE,
    "current_weather": True,
    "timezone":        "America/Chicago",
    "temperature_unit":"fahrenheit",
    "windspeed_unit":  "mph",
    "daily":           "temperature_2m_max,temperature_2m_min,sunrise,sunset"
}

NHL_API_URL        = "https://api-web.nhle.com/v1/club-schedule-season/CHI/20252026"
MLB_API_URL        = "https://statsapi.mlb.com/api/v1/schedule"
MLB_CUBS_TEAM_ID   = "112"
MLB_SOX_TEAM_ID    = "145"

CENTRAL_TIME = pytz.timezone("America/Chicago")

# ─── Fonts ────────────────────────────────────────────────────────────────────
# Drop your TimesSquare-m105.ttf, DejaVuSans.ttf and DejaVuSans-Bold.ttf
# into a new folder named `fonts` alongside this file.
FONTS_DIR = os.path.join(SCRIPT_DIR, "fonts")

def _load_font(name, size):
    path = os.path.join(FONTS_DIR, name)
    return ImageFont.truetype(path, size)

FONT_DAY_DATE           = _load_font("DejaVuSans-Bold.ttf", 21)
FONT_DATE               = _load_font("DejaVuSans.ttf",      12)
FONT_TIME               = _load_font("DejaVuSans-Bold.ttf", 32)
FONT_AM_PM              = _load_font("DejaVuSans.ttf",      11)

FONT_TEMP               = _load_font("DejaVuSans-Bold.ttf", 24)
FONT_CONDITION          = _load_font("DejaVuSans-Bold.ttf", 11)
FONT_WEATHER_DETAILS    = _load_font("DejaVuSans.ttf",      12)
FONT_WEATHER_DETAILS_BOLD = _load_font("DejaVuSans-Bold.ttf", 10)
FONT_WEATHER_LABEL      = _load_font("DejaVuSans.ttf",      10)

FONT_TITLE_SPORTS       = _load_font("TimesSquare-m105.ttf", 16)
FONT_TEAM_SPORTS        = _load_font("TimesSquare-m105.ttf", 20)
FONT_DATE_SPORTS        = _load_font("TimesSquare-m105.ttf", 16)
FONT_TEAM_SPORTS_SMALL  = _load_font("TimesSquare-m105.ttf", 18)
FONT_SCORE              = _load_font("TimesSquare-m105.ttf", 22)
FONT_STATUS             = _load_font("TimesSquare-m105.ttf", 16)

FONT_INSIDE_LABEL       = _load_font("DejaVuSans-Bold.ttf", 10)
FONT_INSIDE_VALUE       = _load_font("DejaVuSans.ttf", 9)
FONT_TITLE_INSIDE       = _load_font("DejaVuSans-Bold.ttf", 9)

FONT_TRAVEL_TITLE       = _load_font("TimesSquare-m105.ttf", 9)
FONT_TRAVEL_HEADER      = _load_font("TimesSquare-m105.ttf", 9)
FONT_TRAVEL_VALUE       = _load_font("TimesSquare-m105.ttf",10)

FONT_IP_LABEL           = FONT_INSIDE_LABEL
FONT_IP_VALUE           = FONT_INSIDE_VALUE

FONT_STOCK_TITLE        = _load_font("DejaVuSans-Bold.ttf", 10)
FONT_STOCK_PRICE        = _load_font("DejaVuSans-Bold.ttf", 24)
FONT_STOCK_CHANGE       = _load_font("DejaVuSans.ttf",      12)
FONT_STOCK_TEXT         = _load_font("DejaVuSans.ttf",      9)

# Standings fonts...
FONT_STAND1_WL          = _load_font("DejaVuSans-Bold.ttf", 14)
FONT_STAND1_RANK        = _load_font("DejaVuSans.ttf",      12)
FONT_STAND1_GB_LABEL    = _load_font("DejaVuSans.ttf",      9)
FONT_STAND1_WCGB_LABEL  = _load_font("DejaVuSans.ttf",      9)
FONT_STAND1_GB_VALUE    = _load_font("DejaVuSans.ttf",      9)
FONT_STAND1_WCGB_VALUE  = _load_font("DejaVuSans.ttf",      9)

FONT_STAND2_RECORD      = _load_font("DejaVuSans.ttf",      14)
FONT_STAND2_LABEL       = _load_font("DejaVuSans.ttf",      12)
FONT_STAND2_VALUE       = _load_font("DejaVuSans.ttf",      12)

FONT_DIV_HEADER         = _load_font("DejaVuSans-Bold.ttf", 11)
FONT_DIV_RECORD         = _load_font("DejaVuSans.ttf",      12)
FONT_DIV_GB             = _load_font("DejaVuSans.ttf",      10)
FONT_GB_VALUE           = _load_font("DejaVuSans.ttf",      10)
FONT_GB_LABEL           = _load_font("DejaVuSans.ttf",      8)

# Symbola (packaged as `ttf-ancient-fonts` on Debian/Ubuntu) provides monochrome
# emoji glyphs that render reliably on the ePaper display. We fall back to the
# default PIL bitmap font if Symbola cannot be located so screens stay legible
# even without the optional package.
_symbola_paths = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
_symbola = next((p for p in _symbola_paths if "symbola" in p.lower()), None)
FONT_EMOJI = ImageFont.truetype(_symbola, 16) if _symbola else ImageFont.load_default()

# ─── Screen-specific configuration ─────────────────────────────────────────────

# Weather screen
WEATHER_ICON_SIZE = 64
WEATHER_DESC_GAP  = 8

# Date/time screen
DATE_TIME_GH_ICON_INVERT = True
DATE_TIME_GH_ICON_SIZE   = 18
DATE_TIME_GH_ICON_PATHS  = [
    os.path.join(IMAGES_DIR, "gh.png"),
    os.path.join(SCRIPT_DIR, "image", "gh.png"),
]

# Indoor sensor screen colors
INSIDE_COL_BG     = (0, 0, 0)
INSIDE_COL_TITLE  = (240, 240, 240)
INSIDE_CHIP_BLUE  = (34, 124, 236)
INSIDE_CHIP_AMBER = (233, 165, 36)
INSIDE_CHIP_PURPLE = (150, 70, 200)
INSIDE_COL_TEXT   = (255, 255, 255)
INSIDE_COL_STROKE = (230, 230, 230)

# Travel time screen
TRAVEL_PROFILES = {
    "to_home": {
        "origin": "224 W Hill St, Chicago, IL",
        "destination": "3912 Rutgers Ln, Northbrook, IL",
        "title": "Travel Time to Home…",
        "active_window": (datetime.time(14, 30), datetime.time(19, 0)),
    },
    "to_work": {
        "origin": "3912 Rutgers Ln, Northbrook, IL",
        "destination": "224 W Hill St, Chicago, IL",
        "title": "Travel Time to Work…",
        "active_window": (datetime.time(6, 0), datetime.time(11, 0)),
    },
    "default": {
        "origin": "224 W Hill St, Chicago, IL",
        "destination": "3912 Rutgers Ln, Northbrook, IL",
        "title": "Travel Time…",
        "active_window": (datetime.time(6, 0), datetime.time(19, 0)),
    },
}

_travel_profile = TRAVEL_PROFILES.get(TRAVEL_MODE, TRAVEL_PROFILES["default"])
TRAVEL_ORIGIN        = _travel_profile["origin"]
TRAVEL_DESTINATION   = _travel_profile["destination"]
TRAVEL_TITLE         = _travel_profile["title"]
TRAVEL_ACTIVE_WINDOW = _travel_profile["active_window"]
TRAVEL_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

# Bears schedule screen
BEARS_BOTTOM_MARGIN = 4
BEARS_SCHEDULE = [
    {"week":"0.1","date":"Sat, Aug 9",  "opponent":"Miami Dolphins",       "home_away":"Home","time":"Noon"},
    {"week":"0.2","date":"Sun, Aug 17", "opponent":"Buffalo Bills",        "home_away":"Home","time":"7PM"},
    {"week":"0.3","date":"Fri, Aug 22", "opponent":"Kansas City Chiefs",   "home_away":"Away","time":"7:20PM"},
    {"week":"Wk. 1",  "date":"Mon, Sep 8",  "opponent":"Minnesota Vikings",    "home_away":"Home","time":"7:15PM"},
    {"week":"Wk. 2",  "date":"Sun, Sep 14", "opponent":"Detroit Lions",        "home_away":"Away","time":"Noon"},
    {"week":"Wk. 3",  "date":"Sun, Sep 21", "opponent":"Dallas Cowboys",       "home_away":"Home","time":"3:25PM"},
    {"week":"Wk. 4",  "date":"Sun, Sep 28", "opponent":"Las Vegas Raiders",    "home_away":"Away","time":"3:25PM"},
    {"week":"Wk. 5",  "date":"BYE",         "opponent":"—",                    "home_away":"—",   "time":"—"},
    {"week":"Wk. 6",  "date":"Mon, Oct 13","opponent":"Washington Commanders", "home_away":"Away","time":"7:15PM"},
    {"week":"Wk. 7",  "date":"Sun, Oct 19","opponent":"New Orleans Saints",    "home_away":"Home","time":"Noon"},
    {"week":"Wk. 8",  "date":"Sun, Oct 26","opponent":"Baltimore Ravens",      "home_away":"Away","time":"Noon"},
    {"week":"Wk. 9",  "date":"Sun, Nov 2", "opponent":"Cincinnati Bengals",    "home_away":"Away","time":"Noon"},
    {"week":"Wk. 10", "date":"Sun, Nov 9", "opponent":"New York Giants",       "home_away":"Home","time":"Noon"},
    {"week":"Wk. 11", "date":"Sun, Nov 16","opponent":"Minnesota Vikings",     "home_away":"Away","time":"Noon"},
    {"week":"Wk. 12", "date":"Sun, Nov 23","opponent":"Pittsburgh Steelers",   "home_away":"Home","time":"Noon"},
    {"week":"Wk. 13", "date":"Fri, Nov 28","opponent":"Philadelphia Eagles",   "home_away":"Away","time":"2PM"},
    {"week":"Wk. 14", "date":"Sun, Dec 7", "opponent":"Green Bay Packers",     "home_away":"Away","time":"Noon"},
    {"week":"Wk. 15", "date":"Sun, Dec 14","opponent":"Cleveland Browns",      "home_away":"Home","time":"Noon"},
    {"week":"Wk. 16", "date":"Sat, Dec 20","opponent":"Green Bay Packers",     "home_away":"Home","time":"TBD"},
    {"week":"Wk. 17", "date":"Sun, Dec 28","opponent":"San Francisco 49ers",   "home_away":"Away","time":"7:20PM"},
    {"week":"Wk. 18", "date":"TBD",        "opponent":"Detroit Lions",         "home_away":"Home","time":"TBD"},
]

NFL_TEAM_ABBREVIATIONS = {
    "dolphins": "mia",   "bills": "buf",   "chiefs": "kc",
    "vikings": "min",    "lions": "det",   "cowboys": "dal",
    "raiders": "lv",     "commanders": "was","saints": "no",
    "ravens": "bal",     "bengals": "cin",  "giants": "nyg",
    "steelers": "pit",   "eagles": "phi",   "packers": "gb",
    "browns": "cle",     "49ers": "sf",
}

# VRNOF screen
VRNOF_FRESHNESS_LIMIT = 10 * 60
VRNOF_LOTS = [
    {"shares": 125, "cost": 3.39},
    {"shares": 230, "cost": 0.74},
    {"shares": 230, "cost": 1.34},
    {"shares": 555, "cost": 0.75},
    {"shares": 107, "cost": 0.64},
    {"shares": 157, "cost": 0.60},
]

# Hockey assets
NHL_IMAGES_DIR = os.path.join(IMAGES_DIR, "nhl")
TIMES_SQUARE_FONT_PATH = os.path.join(FONTS_DIR, "TimesSquare-m105.ttf")
os.makedirs(NHL_IMAGES_DIR, exist_ok=True)

NHL_API_ENDPOINTS = {
    "team_month_now": "https://api-web.nhle.com/v1/club-schedule/{tric}/month/now",
    "team_season_now": "https://api-web.nhle.com/v1/club-schedule-season/{tric}/now",
    "game_landing": "https://api-web.nhle.com/v1/gamecenter/{gid}/landing",
    "game_boxscore": "https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore",
    "stats_schedule": "https://statsapi.web.nhl.com/api/v1/schedule",
    "stats_feed": "https://statsapi.web.nhl.com/api/v1/game/{gamePk}/feed/live",
}

NHL_TEAM_ID      = 16
NHL_TEAM_TRICODE = "CHI"
NHL_FALLBACK_LOGO = os.path.join(NHL_IMAGES_DIR, "NHL.jpg")
