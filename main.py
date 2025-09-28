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
)
from utils import (
    Display,
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
from draw_travel_time    import draw_travel_time_screen
from draw_bears_schedule import show_bears_next_game
from draw_hawks_schedule import (
    draw_last_hawks_game,
    draw_live_hawks_game,
    draw_sports_screen_hawks,
)
from mlb_schedule        import (
    draw_last_game,
    draw_box_score,
    draw_sports_screen,
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

def load_screen_config():
    try:
        return json.load(open(CONFIG_PATH)).get("screens", {})
    except Exception as e:
        logging.warning(f"Could not load screens_config.json: {e}")
        return {}

user_cfg = load_screen_config()
seq_vals = [v for v in user_cfg.values() if isinstance(v, int) and v > 1]
MAX_SEQUENCE = max(seq_vals) if seq_vals else 1
logging.info(f"🔢 Sequence length determined: {MAX_SEQUENCE}")

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
        img = Image.open(path).convert("RGB")
        ratio = height / img.height
        return img.resize((int(img.width * ratio), height))
    except Exception as e:
        logging.warning(f"Logo load failed '{fn}': {e}")
        return None

cubs_logo   = load_logo("cubs.jpg")
hawks_logo  = load_logo("hawks.jpg")
sox_logo    = load_logo("sox.jpg")
weather_img = load_logo("weather.jpg")
mlb_logo    = load_logo("mlb.jpg")
verano_img  = load_logo("verano.jpg")
bears_logo  = load_logo("bears.png")

# ─── Data cache & refresh ────────────────────────────────────────────────────
cache = {
    "weather": None,
    "hawks":   {"last":None, "live":None, "next":None},
    "cubs":    {"stand":None, "last":None, "live":None, "next":None},
    "sox":     {"stand":None, "last":None, "live":None, "next":None},
}

def refresh_all():
    logging.info("🔄 Refreshing all data…")
    cache["weather"] = data_fetch.fetch_weather()
    cache["hawks"].update({
        "last": data_fetch.fetch_blackhawks_last_game(),
        "live": data_fetch.fetch_blackhawks_live_game(),
        "next": data_fetch.fetch_blackhawks_next_game(),
    })
    cubg = data_fetch.fetch_cubs_games() or {}
    cache["cubs"].update({
        "stand": data_fetch.fetch_cubs_standings(),
        "last":  cubg.get("last_game"),
        "live":  cubg.get("live_game"),
        "next":  cubg.get("next_game"),
    })
    soxg = data_fetch.fetch_sox_games() or {}
    cache["sox"].update({
        "stand": data_fetch.fetch_sox_standings(),
        "last":  soxg.get("last_game"),
        "live":  soxg.get("live_game"),
        "next":  soxg.get("next_game"),
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

# ─── Build screen sequence ───────────────────────────────────────────────────
def build_screens():
    screens = [
        ("date",         lambda: draw_date(display,   transition=False)),
        ("time",         lambda: draw_time(display,   transition=True)),
        ("weather logo", (lambda: show_logo(weather_img)) if weather_img else None),
        ("weather1",     lambda: draw_weather_screen_1(display, cache["weather"], transition=True)),
        ("weather2",     lambda: draw_weather_screen_2(display, cache["weather"], transition=True)),
        ("inside",       lambda: draw_inside(display, transition=True)),
        ("verano logo",  (lambda: show_logo(verano_img)) if verano_img else None),
        ("vrnof",        lambda: draw_vrnof_screen(display, "VRNOF", transition=True)),
        ("travel",       lambda: draw_travel_time_screen(display, transition=True)),
        ("bears logo",   (lambda: show_logo(bears_logo)) if bears_logo else None),
        ("bears next",   lambda: show_bears_next_game(display, transition=True)),
    ]
    screens = [s for s in screens if s]

    if any(cache["hawks"].values()):
        screens += [
            ("hawks logo", (lambda: show_logo(hawks_logo)) if hawks_logo else None),
            ("hawks last", lambda: draw_last_hawks_game(display, cache["hawks"]["last"], transition=True)),
            ("hawks live", lambda: draw_live_hawks_game(display, cache["hawks"]["live"], transition=True)),
            ("hawks next", lambda: draw_sports_screen_hawks(display, cache["hawks"]["next"], transition=True)),
        ]
        screens = [s for s in screens if s]

    if any(cache["cubs"].values()):
        screens += [
            ("cubs logo",   (lambda: show_logo(cubs_logo)) if cubs_logo else None),
            ("cubs stand1", lambda: draw_standings_screen1(display, cache["cubs"]["stand"], os.path.join(IMAGES_DIR,"cubs.jpg"), "NL Central", transition=True)),
            ("cubs stand2", lambda: draw_standings_screen2(display, cache["cubs"]["stand"], os.path.join(IMAGES_DIR,"cubs.jpg"), transition=True)),
            ("cubs last",   lambda: draw_last_game(display, cache["cubs"]["last"],  "Last Cubs game...", transition=True)),
            ("cubs result", lambda: draw_cubs_result(display, cache["cubs"]["last"], transition=True)),
            ("cubs live",   lambda: draw_box_score(display,  cache["cubs"]["live"], "Cubs Live...", transition=True)),
            ("cubs next",   lambda: draw_sports_screen(display, cache["cubs"]["next"], "Next Cubs game...", transition=True)),
        ]
        screens = [s for s in screens if s]

    if any(cache["sox"].values()):
        screens += [
            ("sox logo",   (lambda: show_logo(sox_logo)) if sox_logo else None),
            ("sox stand1", lambda: draw_standings_screen1(display, cache["sox"]["stand"], os.path.join(IMAGES_DIR,"sox.jpg"), "AL Central", transition=True)),
            ("sox stand2", lambda: draw_standings_screen2(display, cache["sox"]["stand"], os.path.join(IMAGES_DIR,"sox.jpg"), transition=True)),
            ("sox last",   lambda: draw_last_game(display, cache["sox"]["last"], "Last Sox game...", transition=True)),
            ("sox live",   lambda: draw_box_score(display, cache["sox"]["live"], "Sox Live...", transition=True)),
            ("sox next",   lambda: draw_sports_screen(display, cache["sox"]["next"], "Next Sox game...", transition=True)),
        ]
        screens = [s for s in screens if s]

    screens += [
        ("mlb logo",     (lambda: show_logo(mlb_logo)) if mlb_logo else None),
        ("MLB Scoreboard", lambda: draw_mlb_scoreboard(display, transition=True)),
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

def main_loop():
    global loop_count

    try:
        while True:
            loop_count += 1
            seq_pos = ((loop_count - 1) % MAX_SEQUENCE) + 1

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
                cfg = user_cfg.get(sid, 1)
                if cfg is False or cfg == 0:
                    continue
                try:
                    pos = int(cfg)
                except Exception:
                    pos = 1
                if pos == 1 or pos == seq_pos:
                    filtered.append((sid, fn))

            # Present
            for sid, fn in filtered:
                logging.info(f"🎬 Presenting '{sid}' (seq {seq_pos})")
                try:
                    img = fn()
                except Exception as e:
                    logging.error(f"Error in screen '{sid}': {e}")
                    continue

                # Logos return an image directly
                if "logo" in sid and img:
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
                if img:
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
