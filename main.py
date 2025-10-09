#!/usr/bin/env python3
"""
Main display loop driving Waveshare SSD1351 in RGB,
with optional screenshot, H.264 MP4 video capture, Wi-Fi triage,
screen-config sequencing, and batch screenshot archiving.

Changes:
- Stop pruning single files; instead, when screenshots/ has >= ARCHIVE_THRESHOLD
  images, archive the whole set into screenshot_archive/YYYYMMDD/HHMMSS/.
- Avoid creating empty archive folders.
- Guard logo screens when the image file is missing.
"""
import warnings
from gpiozero.exc import PinFactoryFallback, NativePinFactoryFallback

warnings.filterwarnings("ignore", category=PinFactoryFallback)
warnings.filterwarnings("ignore", category=NativePinFactoryFallback)

import os
import sys
import time
import json
import logging
import threading
import datetime
import signal
import shutil
from typing import Optional

gc = __import__('gc')

from PIL import Image, ImageDraw

from config import (
    WIDTH,
    HEIGHT,
    SCREEN_DELAY,
    SCHEDULE_UPDATE_INTERVAL,
    FONT_DATE_SPORTS,
    ENABLE_SCREENSHOTS,
    ENABLE_VIDEO,
    VIDEO_FPS,
    ENABLE_WIFI_MONITOR,
    CENTRAL_TIME,
    TRAVEL_ACTIVE_WINDOW,
)
from utils import (
    Display,
    ScreenImage,
    clear_display,
    draw_text_centered,
    animate_fade_in,
    animate_scroll,
)
import data_fetch
import wifi_utils  # for wifi_utils.wifi_status

from draw_date_time      import draw_date, draw_time
from draw_weather        import draw_weather_screen_1, draw_weather_screen_2
from draw_vrnof          import draw_vrnof_screen
from draw_travel_time    import (
    draw_travel_time_screen,
    get_travel_active_window,
    is_travel_screen_active,
)
from draw_bears_schedule import show_bears_next_game
from draw_hawks_schedule import (
    draw_last_hawks_game,
    draw_live_hawks_game,
    draw_sports_screen_hawks,
    draw_hawks_next_home_game,
)
from mlb_schedule        import (
    draw_last_game,
    draw_box_score,
    draw_sports_screen,
    draw_next_home_game,
    draw_cubs_result,
)
from mlb_team_standings  import (
    draw_standings_screen1,
    draw_standings_screen2,
)
from mlb_standings       import (
    draw_NL_Overview,
    draw_AL_Overview,
    draw_NL_East,
    draw_NL_Central,
    draw_NL_West,
    draw_NL_WildCard,
    draw_AL_East,
    draw_AL_Central,
    draw_AL_West,
    draw_AL_WildCard,
)
from mlb_scoreboard      import draw_mlb_scoreboard
from nba_scoreboard      import draw_nba_scoreboard
from nhl_scoreboard      import draw_nhl_scoreboard
from nhl_standings       import (
    draw_nhl_standings_east,
    draw_nhl_standings_west,
)
from nfl_scoreboard      import draw_nfl_scoreboard
from nfl_standings      import (
    draw_nfl_standings_afc,
    draw_nfl_standings_nfc,
)
from draw_inside import draw_inside

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.info("🖥️  Starting display service…")

# ─── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "screens_config.json")

# ─── Screenshot archiving (batch) ────────────────────────────────────────────
ARCHIVE_THRESHOLD        = 500                  # archive when we reach this many images
SCREENSHOT_ARCHIVE_BASE  = os.path.join(SCRIPT_DIR, "screenshot_archive")
ALLOWED_SCREEN_EXTS      = (".png", ".jpg", ".jpeg")  # images only

def _normalize_frequency(screen_id: str, raw_value) -> int:
    """Convert the raw JSON value into a positive integer frequency.

    A value of 0/False disables the screen. Any invalid value falls back to 1.
    """

    if raw_value in (False, None):
        return 0

    try:
        freq = int(raw_value)
    except (TypeError, ValueError):
        logging.warning(
            f"Invalid frequency '{raw_value}' for screen '{screen_id}'. Defaulting to 1."
        )
        return 1

    if freq <= 0:
        return 0

    return freq


def load_screen_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        logging.warning(f"Could not load screens_config.json: {e}")
        return {}

    screens = data.get("screens", {}) if isinstance(data, dict) else {}
    frequencies = {
        screen_id: _normalize_frequency(screen_id, raw)
        for screen_id, raw in screens.items()
    }
    return frequencies


screen_frequencies = load_screen_config()
try:
    _screen_config_mtime = os.path.getmtime(CONFIG_PATH)
except OSError:
    _screen_config_mtime = None


def _recalculate_max_frequency():
    global MAX_FREQUENCY
    freq_vals = [v for v in screen_frequencies.values() if v > 1]
    MAX_FREQUENCY = max(freq_vals) if freq_vals else 1


MAX_FREQUENCY = 1
_recalculate_max_frequency()


def _extract_team_id(blob):
    if not isinstance(blob, dict):
        return None
    team = blob.get("team") if isinstance(blob.get("team"), dict) else blob
    if isinstance(team, dict):
        for key in ("id", "teamId", "team_id"):
            if team.get(key) is not None:
                return team.get(key)
    return None


def _games_match(game_a, game_b):
    if not game_a or not game_b:
        return False

    for key in ("gamePk", "id", "gameId", "gameUUID"):
        a_val = game_a.get(key)
        b_val = game_b.get(key)
        if a_val and b_val and a_val == b_val:
            return True

    def _teams(game, prefix):
        teams = game.get("teams")
        if isinstance(teams, dict):
            return teams.get(prefix) or {}
        return game.get(f"{prefix}Team") or game.get(f"{prefix}_team") or {}

    date_a = (game_a.get("gameDate") or game_a.get("officialDate") or "")[:10]
    date_b = (game_b.get("gameDate") or game_b.get("officialDate") or "")[:10]
    if date_a and date_b and date_a == date_b:
        home_a = _extract_team_id(_teams(game_a, "home"))
        home_b = _extract_team_id(_teams(game_b, "home"))
        away_a = _extract_team_id(_teams(game_a, "away"))
        away_b = _extract_team_id(_teams(game_b, "away"))
        return home_a and home_a == home_b and away_a and away_a == away_b

    return False
logging.info(f"🔁 Max configured screen frequency: every {MAX_FREQUENCY} loop(s)")

# ─── Display & Wi-Fi monitor ─────────────────────────────────────────────────
display = Display()
if ENABLE_WIFI_MONITOR:
    logging.info("🔌 Starting Wi-Fi monitor…")
    wifi_utils.start_monitor()

# ─── Screenshot / video outputs ──────────────────────────────────────────────
SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "screenshots")
if ENABLE_SCREENSHOTS:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_ARCHIVE_BASE, exist_ok=True)

video_out = None
if ENABLE_VIDEO:
    import cv2, numpy as np
    FOURCC     = cv2.VideoWriter_fourcc(*"mp4v")
    video_path = os.path.join(SCREENSHOT_DIR, "oled_output.mp4")
    logging.info(f"🎥 Starting video capture → {video_path} @ {VIDEO_FPS} FPS using mp4v")
    video_out = cv2.VideoWriter(video_path, FOURCC, VIDEO_FPS, (WIDTH, HEIGHT))
    if not video_out.isOpened():
        logging.error("❌ Cannot open video writer; disabling video output")
        video_out = None

_archive_lock = threading.Lock()

def _list_screenshot_files():
    try:
        return sorted(
            f for f in os.listdir(SCREENSHOT_DIR)
            if f.lower().endswith(ALLOWED_SCREEN_EXTS)
        )
    except Exception:
        return []

def maybe_archive_screenshots():
    """
    When screenshots/ reaches ARCHIVE_THRESHOLD images,
    move the current images into screenshot_archive/YYYYMMDD/HHMMSS/.
    Avoid creating empty archive folders.
    """
    if not ENABLE_SCREENSHOTS:
        return
    files = _list_screenshot_files()
    if len(files) < ARCHIVE_THRESHOLD:
        return

    with _archive_lock:
        files = _list_screenshot_files()
        if len(files) < ARCHIVE_THRESHOLD:
            return

        moved = 0
        batch_dir = None  # create only on first successful move
        for fname in files:
            src = os.path.join(SCREENSHOT_DIR, fname)
            try:
                if batch_dir is None:
                    now = datetime.datetime.now()
                    day_dir   = os.path.join(SCREENSHOT_ARCHIVE_BASE, now.strftime("%Y%m%d"))
                    batch_dir = os.path.join(day_dir, now.strftime("%H%M%S"))
                    os.makedirs(batch_dir, exist_ok=True)
                shutil.move(src, os.path.join(batch_dir, fname))
                moved += 1
            except Exception as e:
                logging.warning(f"⚠️  Could not move '{fname}' to archive: {e}")

        # Remove an empty batch_dir if nothing was moved
        if moved == 0 and batch_dir and os.path.isdir(batch_dir):
            try:
                os.rmdir(batch_dir)
            except Exception:
                pass

        if moved:
            logging.info(f"🗃️  Archived {moved} screenshot(s).")

# ─── SIGTERM handler ─────────────────────────────────────────────────────────
def _handle_sigterm(signum, frame):
    logging.info("✋ SIGTERM caught—clearing display & finalizing video…")
    try:
        clear_display(display)
    except Exception:
        pass
    if video_out:
        video_out.release()
        logging.info("🎬 Video finalized cleanly.")
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)

# ─── Logos ───────────────────────────────────────────────────────────────────
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")
def load_logo(fn, height=80):
    path = os.path.join(IMAGES_DIR, fn)
    try:
        with Image.open(path) as img:
            has_transparency = (
                img.mode in ("RGBA", "LA")
                or (img.mode == "P" and "transparency" in img.info)
            )
            target_mode = "RGBA" if has_transparency else "RGB"
            img = img.convert(target_mode)
            ratio = height / img.height if img.height else 1
            resized = img.resize((int(img.width * ratio), height), Image.ANTIALIAS)
        return resized
    except Exception as e:
        logging.warning(f"Logo load failed '{fn}': {e}")
        return None

cubs_logo   = load_logo("cubs.jpg")
hawks_logo  = load_logo("hawks.jpg")
sox_logo    = load_logo("sox.jpg")
weather_img = load_logo("weather.jpg")
mlb_logo    = load_logo("mlb.jpg")
nba_logo    = load_logo("nba/NBA.png")
nhl_logo    = load_logo("nhl/nhl.png") or load_logo("nhl/NHL.png")
nfl_logo    = load_logo("nfl/nfl.png")
verano_img  = load_logo("verano.jpg")
bears_logo  = load_logo("bears.png")

# ─── Data cache & refresh ────────────────────────────────────────────────────
cache = {
    "weather": None,
    "hawks":   {"last":None, "live":None, "next":None, "next_home":None},
    "cubs":    {"stand":None, "last":None, "live":None, "next":None, "next_home":None},
    "sox":     {"stand":None, "last":None, "live":None, "next":None, "next_home":None},
}

def refresh_all():
    logging.info("🔄 Refreshing all data…")
    cache["weather"] = data_fetch.fetch_weather()
    cache["hawks"].update({
        "last": data_fetch.fetch_blackhawks_last_game(),
        "live": data_fetch.fetch_blackhawks_live_game(),
        "next": data_fetch.fetch_blackhawks_next_game(),
        "next_home": data_fetch.fetch_blackhawks_next_home_game(),
    })
    cubg = data_fetch.fetch_cubs_games() or {}
    cache["cubs"].update({
        "stand": data_fetch.fetch_cubs_standings(),
        "last":  cubg.get("last_game"),
        "live":  cubg.get("live_game"),
        "next":  cubg.get("next_game"),
        "next_home": cubg.get("next_home_game"),
    })
    soxg = data_fetch.fetch_sox_games() or {}
    cache["sox"].update({
        "stand": data_fetch.fetch_sox_standings(),
        "last":  soxg.get("last_game"),
        "live":  soxg.get("live_game"),
        "next":  soxg.get("next_game"),
        "next_home": soxg.get("next_home_game"),
    })

threading.Thread(
    target=lambda: (time.sleep(30),
                    [refresh_all() or time.sleep(SCHEDULE_UPDATE_INTERVAL) for _ in iter(int, None)]),
    daemon=True
).start()
refresh_all()

# ─── Present helpers ─────────────────────────────────────────────────────────
def show_logo(img: Image.Image) -> Image.Image:
    animate_scroll(display, img)
    return img


def show_nba_logo_screen() -> Optional[Image.Image]:
    if not nba_logo:
        return None
    return show_logo(nba_logo)


# ─── Build screen sequence ───────────────────────────────────────────────────
def build_screens():
    global _travel_schedule_state

    screens = [
        ("date",         lambda: draw_date(display,   transition=False)),
        ("time",         lambda: draw_time(display,   transition=True)),
        ("weather logo", (lambda: show_logo(weather_img)) if weather_img else None),
        ("weather1",     lambda: draw_weather_screen_1(display, cache["weather"], transition=True)),
        ("weather2",     lambda: draw_weather_screen_2(display, cache["weather"], transition=True)),
        ("inside",       lambda: draw_inside(display, transition=True)),
        ("verano logo",  (lambda: show_logo(verano_img)) if verano_img else None),
        ("vrnof",        lambda: draw_vrnof_screen(display, "VRNOF", transition=True)),
    ]

    travel_freq = screen_frequencies.get("travel", 1)
    travel_enabled = travel_freq > 0
    travel_active = is_travel_screen_active()

    window = get_travel_active_window()
    now_time = datetime.datetime.now(CENTRAL_TIME).time()

    def fmt_time(value: Optional[datetime.time]) -> str:
        if isinstance(value, datetime.time):
            return value.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
        return "all day"

    window_desc = (
        f"{fmt_time(window[0])} – {fmt_time(window[1])}" if window else "all day"
    )

    if travel_enabled and travel_active:
        state = "scheduled"
        if _travel_schedule_state != state:
            logging.info(
                "🧭 Travel screen enabled (window %s).",
                window_desc,
            )
        screens.append(("travel", lambda: draw_travel_time_screen(display, transition=True)))
    elif travel_enabled:
        state = "outside_window"
        if _travel_schedule_state != state:
            if window:
                logging.info(
                    "🧭 Travel screen skipped—outside active window (%s, now %s).",
                    window_desc,
                    fmt_time(now_time),
                )
            else:
                logging.info("🧭 Travel screen enabled (no active window configured).")
    elif travel_active:
        state = "disabled"
        if _travel_schedule_state != state:
            logging.info("🧭 Travel screen disabled via configuration.")
    else:
        state = "inactive"

    _travel_schedule_state = state

    screens += [
        ("bears logo",   (lambda: show_logo(bears_logo)) if bears_logo else None),
        ("bears next",   lambda: show_bears_next_game(display, transition=True)),
        ("nfl logo",     (lambda: show_logo(nfl_logo)) if nfl_logo else None),
        ("NFL Scoreboard", lambda: draw_nfl_scoreboard(display, transition=True)),
        ("NFL Standings NFC", lambda: draw_nfl_standings_nfc(display, transition=True)),
        ("NFL Standings AFC", lambda: draw_nfl_standings_afc(display, transition=True)),
    ]

    screens = [s for s in screens if s]

    if any(cache["hawks"].values()):
        hawks_next = cache["hawks"].get("next")
        hawks_next_home = cache["hawks"].get("next_home")
        if _games_match(hawks_next_home, hawks_next):
            hawks_next_home = None

        screens += [
            ("hawks logo", (lambda: show_logo(hawks_logo)) if hawks_logo else None),
            ("hawks last", lambda: draw_last_hawks_game(display, cache["hawks"]["last"], transition=True)),
            ("hawks live", lambda: draw_live_hawks_game(display, cache["hawks"]["live"], transition=True)),
            ("hawks next", lambda: draw_sports_screen_hawks(display, hawks_next, transition=True)),
            (
                "hawks next home",
                (
                    lambda: draw_hawks_next_home_game(
                        display,
                        hawks_next_home,
                        transition=True,
                    )
                ) if hawks_next_home else None,
            ),
            ("nhl logo",   (lambda: show_logo(nhl_logo)) if nhl_logo else None),
            ("NHL Scoreboard", lambda: draw_nhl_scoreboard(display, transition=True)),
            (
                "NHL Standings West",
                lambda: draw_nhl_standings_west(display, transition=True),
            ),
            (
                "NHL Standings East",
                lambda: draw_nhl_standings_east(display, transition=True),
            ),
        ]
        screens = [s for s in screens if s]

    if any(cache["cubs"].values()):
        cubs_next = cache["cubs"].get("next")
        cubs_next_home = cache["cubs"].get("next_home")
        if _games_match(cubs_next_home, cubs_next):
            cubs_next_home = None

        screens += [
            ("cubs logo",   (lambda: show_logo(cubs_logo)) if cubs_logo else None),
            ("cubs stand1", lambda: draw_standings_screen1(display, cache["cubs"]["stand"], os.path.join(IMAGES_DIR,"cubs.jpg"), "NL Central", transition=True)),
            ("cubs stand2", lambda: draw_standings_screen2(display, cache["cubs"]["stand"], os.path.join(IMAGES_DIR,"cubs.jpg"), transition=True)),
            ("cubs last",   lambda: draw_last_game(display, cache["cubs"]["last"],  "Last Cubs game...", transition=True)),
            ("cubs result", lambda: draw_cubs_result(display, cache["cubs"]["last"], transition=True)),
            ("cubs live",   lambda: draw_box_score(display,  cache["cubs"]["live"], "Cubs Live...", transition=True)),
            ("cubs next",   lambda: draw_sports_screen(display, cubs_next, "Next Cubs game...", transition=True)),
            (
                "cubs next home",
                (
                    lambda: draw_next_home_game(
                        display,
                        cubs_next_home,
                        transition=True,
                    )
                ) if cubs_next_home else None,
            ),
        ]
        screens = [s for s in screens if s]

    if any(cache["sox"].values()):
        sox_next = cache["sox"].get("next")
        sox_next_home = cache["sox"].get("next_home")
        if _games_match(sox_next_home, sox_next):
            sox_next_home = None

        screens += [
            ("sox logo",   (lambda: show_logo(sox_logo)) if sox_logo else None),
            ("sox stand1", lambda: draw_standings_screen1(display, cache["sox"]["stand"], os.path.join(IMAGES_DIR,"sox.jpg"), "AL Central", transition=True)),
            ("sox stand2", lambda: draw_standings_screen2(display, cache["sox"]["stand"], os.path.join(IMAGES_DIR,"sox.jpg"), transition=True)),
            ("sox last",   lambda: draw_last_game(display, cache["sox"]["last"], "Last Sox game...", transition=True)),
            ("sox live",   lambda: draw_box_score(display, cache["sox"]["live"], "Sox Live...", transition=True)),
            ("sox next",   lambda: draw_sports_screen(display, sox_next, "Next Sox game...", transition=True)),
            (
                "sox next home",
                (
                    lambda: draw_next_home_game(
                        display,
                        sox_next_home,
                        transition=True,
                    )
                ) if sox_next_home else None,
            ),
        ]
        screens = [s for s in screens if s]

    screens += [
        ("mlb logo",     (lambda: show_logo(mlb_logo)) if mlb_logo else None),
        ("MLB Scoreboard", lambda: draw_mlb_scoreboard(display, transition=True)),
        ("nba logo",     show_nba_logo_screen if nba_logo else None),
        ("NBA Scoreboard", lambda: draw_nba_scoreboard(display, transition=True)),
        ("NL Overview",  lambda: draw_NL_Overview(display, transition=True)),
        ("NL East",      lambda: draw_NL_East(display, transition=True)),
        ("NL Central",   lambda: draw_NL_Central(display, transition=True)),
        ("NL West",      lambda: draw_NL_West(display, transition=True)),
        ("NL Wild Card", lambda: draw_NL_WildCard(display, transition=True)),
        ("AL Overview",  lambda: draw_AL_Overview(display, transition=True)),
        ("AL East",      lambda: draw_AL_East(display, transition=True)),
        ("AL Central",   lambda: draw_AL_Central(display, transition=True)),
        ("AL West",      lambda: draw_AL_West(display, transition=True)),
        ("AL Wild Card", lambda: draw_AL_WildCard(display, transition=True)),
    ]
    return [s for s in screens if s]

# ─── Main loop ───────────────────────────────────────────────────────────────
loop_count = 0
_travel_schedule_state: Optional[str] = None

def refresh_screen_config_if_needed():
    """Reload the screen configuration when the JSON file changes."""

    global screen_frequencies, _screen_config_mtime

    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mtime = None

    if mtime == _screen_config_mtime:
        return

    screen_frequencies = load_screen_config()
    _screen_config_mtime = mtime
    _recalculate_max_frequency()
    logging.info(
        f"🔁 Reloaded screen configuration (max every {MAX_FREQUENCY} loop(s))"
    )


def main_loop():
    global loop_count

    try:
        while True:
            refresh_screen_config_if_needed()
            loop_count += 1

            # Wi-Fi outage handling
            if ENABLE_WIFI_MONITOR and wifi_utils.wifi_status != "ok":
                img = Image.new("RGB", (WIDTH, HEIGHT), "black")
                d   = ImageDraw.Draw(img)
                if wifi_utils.wifi_status == "no_wifi":
                    draw_text_centered(d, "No Wi-Fi.", FONT_DATE_SPORTS, fill=(255,0,0))
                else:
                    draw_text_centered(d, "Wi-Fi ok.",     FONT_DATE_SPORTS, y_offset=-12, fill=(255,255,0))
                    draw_text_centered(d, wifi_utils.current_ssid or "", FONT_DATE_SPORTS, fill=(255,255,0))
                    draw_text_centered(d, "No internet.",  FONT_DATE_SPORTS, y_offset=12,  fill=(255,0,0))
                display.image(img); display.show(); time.sleep(SCREEN_DELAY)
                for fn in (draw_date, draw_time):
                    img2 = fn(display, transition=True)
                    animate_fade_in(display, img2, steps=8, delay=0.015)
                    time.sleep(SCREEN_DELAY)
                gc.collect()
                continue

            # Build & filter by sequence position
            all_screens = build_screens()
            filtered = []
            for sid, fn in all_screens:
                freq = screen_frequencies.get(sid, 1)
                if freq <= 0:
                    continue
                if loop_count % freq == 0:
                    filtered.append((sid, fn, freq))

            # Present
            for sid, fn, freq in filtered:
                logging.info(
                    f"🎬 Presenting '{sid}' (loop {loop_count}, every {freq} loop(s))"
                )
                try:
                    result = fn()
                except Exception as e:
                    logging.error(f"Error in screen '{sid}': {e}")
                    continue

                already_displayed = False
                img = None
                if isinstance(result, ScreenImage):
                    img = result.image
                    already_displayed = result.displayed
                elif isinstance(result, Image.Image):
                    img = result

                # Logos return an image directly
                if "logo" in sid and isinstance(img, Image.Image):
                    if ENABLE_SCREENSHOTS:
                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        path = os.path.join(SCREENSHOT_DIR, f"{sid.replace(' ', '_')}_{ts}.png")
                        try:
                            img.save(path)
                        except Exception:
                            logging.warning(f"⚠️ Screenshot save failed for '{sid}'")
                        maybe_archive_screenshots()
                    if ENABLE_VIDEO and video_out:
                        import cv2, numpy as np
                        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                        video_out.write(frame)
                    gc.collect()
                    continue

                # Content screens
                if isinstance(img, Image.Image):
                    if not already_displayed:
                        animate_fade_in(display, img, steps=8, delay=0.015)
                    if ENABLE_SCREENSHOTS:
                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe = sid.replace(" ", "_").replace(".", "")
                        path = os.path.join(SCREENSHOT_DIR, f"{safe}_{ts}.png")
                        try:
                            img.save(path)
                        except Exception:
                            logging.warning(f"⚠️ Screenshot save failed for '{sid}'")
                        maybe_archive_screenshots()
                    if ENABLE_VIDEO and video_out:
                        import cv2, numpy as np
                        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                        video_out.write(frame)

                time.sleep(SCREEN_DELAY)
                gc.collect()

    finally:
        if video_out:
            logging.info("🎬 Finalizing video…")
            video_out.release()

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        logging.info("✋ CTRL-C caught—clearing display…")
        clear_display(display)
        if video_out:
            video_out.release()
        sys.exit(0)
