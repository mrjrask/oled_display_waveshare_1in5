#!/usr/bin/env python3
"""
nba_scoreboard.py

Render a scrolling NBA scoreboard using the same layout as the NHL version.
Maintains the previous day's games until 9:30 AM Central before switching to
the current day's slate.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import time
from typing import Any, Dict, Iterable, Optional

from PIL import Image, ImageDraw

try:
    RESAMPLE = Image.ANTIALIAS
except AttributeError:  # Pillow ≥11
    RESAMPLE = Image.Resampling.LANCZOS

from config import (
    WIDTH,
    HEIGHT,
    FONT_TITLE_SPORTS,
    FONT_TEAM_SPORTS,
    FONT_STATUS,
    CENTRAL_TIME,
    IMAGES_DIR,
)
from utils import (
    clear_display,
    clone_font,
    load_team_logo,
    log_call,
)
from http_client import get_session

# ─── Constants ────────────────────────────────────────────────────────────────
TITLE               = "NBA Scoreboard"
TITLE_GAP           = 8
BLOCK_SPACING       = 6
SCORE_ROW_H         = 26
STATUS_ROW_H        = 14
SCROLL_STEP         = 1
SCROLL_DELAY        = 0.04
SCROLL_PAUSE_TOP    = 0.75
SCROLL_PAUSE_BOTTOM = 0.5
REQUEST_TIMEOUT     = 10

COL_WIDTHS = [28, 24, 24, 24, 28]  # total = 128 (WIDTH)
COL_X = [0]
for w in COL_WIDTHS:
    COL_X.append(COL_X[-1] + w)

SCORE_FONT  = clone_font(FONT_TEAM_SPORTS, 18)
STATUS_FONT = clone_font(FONT_STATUS, 15)
CENTER_FONT = clone_font(FONT_STATUS, 15)
TITLE_FONT  = FONT_TITLE_SPORTS
LOGO_HEIGHT = 22
LOGO_DIR    = os.path.join(IMAGES_DIR, "nba")
INTRO_LOGO        = "NBA.png"
INTRO_MAX_HEIGHT  = 100
INTRO_ANIM_SCALES = (0.45, 0.6, 0.75, 0.9, 1.04, 0.98, 1.0)
INTRO_ANIM_DELAY  = 0.06
INTRO_ANIM_HOLD   = 0.4

_LOGO_CACHE: dict[str, Optional[Image.Image]] = {}
_SESSION = get_session()
_NBA_HEADERS = {
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}

_INTRO_LOGO_CACHE: Optional[Image.Image] = None
_INTRO_LOGO_LOADED = False

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _scoreboard_date(now: Optional[datetime.datetime] = None) -> datetime.date:
    now = now or datetime.datetime.now(CENTRAL_TIME)
    cutoff = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now < cutoff:
        return (now - datetime.timedelta(days=1)).date()
    return now.date()


def _load_logo_cached(abbr: str) -> Optional[Image.Image]:
    key = (abbr or "").strip()
    if not key:
        return None
    cache_key = key.upper()
    if cache_key in _LOGO_CACHE:
        return _LOGO_CACHE[cache_key]
    logo = load_team_logo(LOGO_DIR, cache_key, height=LOGO_HEIGHT)
    _LOGO_CACHE[cache_key] = logo
    return logo


def _load_intro_logo() -> Optional[Image.Image]:
    global _INTRO_LOGO_CACHE, _INTRO_LOGO_LOADED
    if not _INTRO_LOGO_LOADED:
        path = os.path.join(LOGO_DIR, INTRO_LOGO)
        try:
            with Image.open(path) as img:
                _INTRO_LOGO_CACHE = img.convert("RGBA")
        except FileNotFoundError:
            logging.warning("NBA intro logo missing at %s", path)
            _INTRO_LOGO_CACHE = None
        except Exception as exc:
            logging.warning("Failed to load NBA intro logo: %s", exc)
            _INTRO_LOGO_CACHE = None
        finally:
            _INTRO_LOGO_LOADED = True
    return _INTRO_LOGO_CACHE.copy() if _INTRO_LOGO_CACHE is not None else None


def _render_intro_frame(logo: Image.Image, scale: float) -> Image.Image:
    if logo.width > 0 and logo.height > 0:
        base_scale = min(WIDTH / logo.width, HEIGHT / logo.height)
    else:
        base_scale = 1.0

    effective_scale = max(0.0, base_scale * scale)
    if effective_scale <= 0:
        effective_scale = base_scale
    max_height_scale = (
        INTRO_MAX_HEIGHT / logo.height if logo.height else base_scale
    )
    effective_scale = min(effective_scale, base_scale, max_height_scale)

    w = max(1, int(round(logo.width * effective_scale)))
    h = max(1, int(round(logo.height * effective_scale)))
    resized = logo.resize((w, h), RESAMPLE)
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    x = (WIDTH - resized.width) // 2
    y = (HEIGHT - resized.height) // 2
    frame.paste(resized, (x, y), resized)
    return frame.convert("RGB")


def _play_intro_animation(display, *, hold: float = INTRO_ANIM_HOLD) -> Optional[Image.Image]:
    logo = _load_intro_logo()
    if logo is None:
        return None

    final_frame: Optional[Image.Image] = None
    for idx, scale in enumerate(INTRO_ANIM_SCALES):
        frame = _render_intro_frame(logo, scale)
        display.image(frame)
        display.show()
        final_frame = frame
        if idx < len(INTRO_ANIM_SCALES) - 1:
            time.sleep(INTRO_ANIM_DELAY)
        else:
            time.sleep(hold)
    return final_frame


@log_call
def play_nba_logo_animation(display, *, hold: float = INTRO_ANIM_HOLD) -> Optional[Image.Image]:
    """Play the NBA intro logo animation and return the final frame."""
    return _play_intro_animation(display, hold=hold)


def _team_logo_abbr(team: Dict[str, Any]) -> str:
    if not isinstance(team, dict):
        return ""
    for key in ("teamTricode", "triCode", "tricode", "abbreviation", "abbr"):
        val = team.get(key)
        if isinstance(val, str) and val.strip():
            candidate = val.strip().upper()
            if os.path.exists(os.path.join(LOGO_DIR, f"{candidate}.png")):
                return candidate
    city = (team.get("teamCity") or team.get("city") or "").strip()
    name = (team.get("teamName") or team.get("name") or "").strip()
    nickname = " ".join(part for part in (city, name) if part)
    if nickname:
        candidate = nickname[:3].upper()
        if os.path.exists(os.path.join(LOGO_DIR, f"{candidate}.png")):
            return candidate
    return ""


def _should_display_scores(game: dict) -> bool:
    status = (game or {}).get("status", {}) or {}
    abstract = (status.get("abstractGameState") or "").lower()
    code = (status.get("statusCode") or "").strip()
    if abstract in {"final", "completed", "live"}:
        return True
    if code in {"2", "3"}:  # 2 = live, 3 = final from NBA feed
        return True
    detailed = (status.get("detailedState") or "").lower()
    if "final" in detailed or "progress" in detailed:
        return True
    return False


def _score_text(side: dict, *, show: bool) -> str:
    if not show:
        return "—"
    score = (side or {}).get("score")
    return "—" if score is None else str(score)


def _ordinal_from_number(num: Any, *, is_overtime: bool = False) -> str:
    try:
        value = int(num)
    except Exception:
        if isinstance(num, str) and num.strip():
            return num.strip().upper()
        return ""
    if value <= 0:
        return ""
    if is_overtime:
        if value <= 1:
            return "OT"
        return f"{value}OT"
    if value == 1:
        return "1ST"
    if value == 2:
        return "2ND"
    if value == 3:
        return "3RD"
    if value == 4:
        return "4TH"
    return f"{value}TH"


def _normalize_clock(clock: Any) -> str:
    if not clock:
        return ""
    if isinstance(clock, (int, float)):
        minutes = int(clock) // 60
        seconds = int(clock) % 60
        return f"{minutes}:{seconds:02d}"
    text = str(clock).strip()
    if not text:
        return ""
    if text.startswith("PT"):
        # Format like PT07M32.00S
        minutes = 0
        seconds = 0
        rem = text[2:]
        try:
            if "M" in rem:
                min_part, rem = rem.split("M", 1)
                minutes = int(float(min_part))
            if "S" in rem:
                sec_part = rem.split("S", 1)[0]
                seconds = int(float(sec_part))
        except Exception:
            return text
        return f"{minutes}:{seconds:02d}"
    return text.upper()


def _format_status(game: dict) -> str:
    status = (game or {}).get("status", {}) or {}
    linescore = (game or {}).get("linescore", {}) or {}
    detailed = (status.get("detailedState") or "").strip()
    detailed_lower = detailed.lower()
    abstract = (status.get("abstractGameState") or "").lower()
    status_code = (status.get("statusCode") or "").strip()

    period_ord = (linescore.get("currentPeriodOrdinal") or "").upper()
    time_remaining = (linescore.get("currentPeriodTimeRemaining") or "").upper()
    final_period = linescore.get("finalPeriod")

    if "postponed" in detailed_lower:
        return "Postponed"
    if "suspended" in detailed_lower:
        return detailed or "Suspended"

    if abstract in {"final", "completed"} or status_code == "3" or "final" in detailed_lower:
        if detailed and detailed_lower not in {"final", "final "}:
            return detailed
        if isinstance(final_period, int) and final_period > 4:
            ot_number = final_period - 4
            if ot_number <= 1:
                return "Final/OT"
            return f"Final/{ot_number}OT"
        return "Final"

    if abstract == "live" or status_code == "2" or "progress" in detailed_lower:
        if "halftime" in detailed_lower:
            return "Halftime"
        if time_remaining and period_ord:
            return f"{time_remaining} {period_ord}".strip()
        if period_ord:
            return period_ord
        return detailed or "In Progress"

    start_local = game.get("_start_local")
    if isinstance(start_local, datetime.datetime):
        return start_local.strftime("%I:%M %p").lstrip("0")

    if detailed:
        return detailed
    return "TBD"


def _center_text(draw: ImageDraw.ImageDraw, text: str, font, x: int, width: int,
                 y: int, height: int, *, fill=(255, 255, 255)):
    if not text:
        return
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        tx = x + (width - tw) // 2 - l
        ty = y + (height - th) // 2 - t
    except Exception:
        tw, th = draw.textsize(text, font=font)
        tx = x + (width - tw) // 2
        ty = y + (height - th) // 2
    draw.text((tx, ty), text, font=font, fill=fill)


def _draw_game_block(canvas: Image.Image, draw: ImageDraw.ImageDraw, game: dict, top: int):
    teams = (game or {}).get("teams", {})
    away = teams.get("away", {})
    home = teams.get("home", {})

    show_scores = _should_display_scores(game)
    away_text = _score_text(away, show=show_scores)
    home_text = _score_text(home, show=show_scores)

    score_top = top
    for idx, text in ((0, away_text), (2, "@"), (4, home_text)):
        font = SCORE_FONT if idx != 2 else CENTER_FONT
        _center_text(draw, text, font, COL_X[idx], COL_WIDTHS[idx], score_top, SCORE_ROW_H)

    for idx, team_side in ((1, away), (3, home)):
        team_obj = (team_side or {}).get("team", {})
        abbr = _team_logo_abbr(team_obj)
        logo = _load_logo_cached(abbr) if abbr else None
        if not logo:
            continue
        x0 = COL_X[idx] + (COL_WIDTHS[idx] - logo.width) // 2
        y0 = score_top + (SCORE_ROW_H - logo.height) // 2
        canvas.paste(logo, (x0, y0), logo)

    status_top = score_top + SCORE_ROW_H
    status_text = _format_status(game)
    _center_text(draw, status_text, STATUS_FONT, COL_X[2], COL_WIDTHS[2], status_top, STATUS_ROW_H)


def _compose_canvas(games: list[dict]) -> Image.Image:
    if not games:
        return Image.new("RGB", (WIDTH, HEIGHT), "black")
    block_height = SCORE_ROW_H + STATUS_ROW_H
    total_height = block_height * len(games)
    if len(games) > 1:
        total_height += BLOCK_SPACING * (len(games) - 1)
    canvas = Image.new("RGB", (WIDTH, total_height), "black")
    draw = ImageDraw.Draw(canvas)

    y = 0
    for idx, game in enumerate(games):
        _draw_game_block(canvas, draw, game, y)
        y += SCORE_ROW_H + STATUS_ROW_H
        if idx < len(games) - 1:
            sep_y = y + BLOCK_SPACING // 2
            draw.line((10, sep_y, WIDTH - 10, sep_y), fill=(45, 45, 45))
            y += BLOCK_SPACING
    return canvas


def _timestamp_to_local(ts: str) -> Optional[datetime.datetime]:
    if not ts:
        return None
    text = str(ts).strip()
    if not text:
        return None
    fmt_candidates = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]
    for fmt in fmt_candidates:
        try:
            dt = datetime.datetime.strptime(text, fmt)
        except Exception:
            continue
        else:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(CENTRAL_TIME)
    try:
        dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(CENTRAL_TIME)


def _hydrate_games(raw_games: Iterable[dict]) -> list[dict]:
    games: list[dict] = []
    for game in raw_games:
        game = game or {}
        start_local = game.get("_start_local")
        if not isinstance(start_local, datetime.datetime):
            start_local = _timestamp_to_local(game.get("gameDate"))
            if not start_local:
                start_local = _timestamp_to_local(game.get("startTimeUTC"))
            if not start_local:
                start_local = _timestamp_to_local(game.get("gameTimeUTC"))
            if start_local:
                game["_start_local"] = start_local
        if isinstance(start_local, datetime.datetime):
            game["_start_sort"] = start_local.timestamp()
        else:
            game["_start_sort"] = float("inf")
        games.append(game)
    games.sort(key=lambda g: (g.get("_start_sort", float("inf")), g.get("gamePk", g.get("gameId", 0))))
    return games


def _parse_period_info(game: Dict[str, Any]) -> tuple[Optional[int], str, Optional[int]]:
    period_info = game.get("period")
    period_type = ""
    final_period = None
    number: Optional[int] = None

    if isinstance(period_info, dict):
        for key in ("current", "number", "period", "sequence"):
            value = period_info.get(key)
            if value not in (None, ""):
                try:
                    number = int(value)
                    break
                except Exception:
                    pass
        period_type = str(period_info.get("type") or period_info.get("periodType") or "").upper()
    elif period_info not in (None, ""):
        try:
            number = int(period_info)
        except Exception:
            pass

    descriptor = game.get("periodDescriptor") or {}
    if isinstance(descriptor, dict):
        if number is None:
            for key in ("period", "number"):
                value = descriptor.get(key)
                if value not in (None, ""):
                    try:
                        number = int(value)
                        break
                    except Exception:
                        pass
        if not period_type:
            period_type = str(descriptor.get("type") or descriptor.get("periodType") or "").upper()
        final_period_val = descriptor.get("maxRegular") or descriptor.get("max") or descriptor.get("total")
        if final_period_val not in (None, ""):
            try:
                final_period = int(final_period_val)
            except Exception:
                pass

    if final_period is None:
        final_period = number

    return number, period_type, final_period


def _map_team(team: Dict[str, Any]) -> Dict[str, Any]:
    team = team or {}
    abbr = ""
    for key in ("teamTricode", "triCode", "tricode", "abbreviation", "abbr"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            abbr = value.strip().upper()
            break
    name_parts = []
    for key in ("teamCity", "city"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            name_parts.append(value.strip())
            break
    for key in ("teamName", "nickname", "name"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            if name_parts:
                name_parts.append(value.strip())
            else:
                name_parts.append(value.strip())
            break
    full_name = " ".join(name_parts).strip()

    mapped: Dict[str, Any] = {"team": {}}
    if abbr:
        mapped["team"]["abbreviation"] = abbr
        mapped["team"]["triCode"] = abbr
    if full_name:
        mapped["team"]["name"] = full_name
    team_id = team.get("teamId") or team.get("id")
    if team_id not in (None, ""):
        mapped["team"]["id"] = team_id

    score = team.get("score")
    if score not in (None, ""):
        mapped["score"] = score

    return mapped


def _map_game(game: Dict[str, Any]) -> Dict[str, Any]:
    game = game or {}
    status_code_raw = game.get("gameStatus") or game.get("statusNum")
    status_code = ""
    if status_code_raw not in (None, ""):
        try:
            status_code = str(int(status_code_raw))
        except Exception:
            status_code = str(status_code_raw)

    status_text = (game.get("gameStatusText") or game.get("statusText") or "").strip()
    if not status_text:
        status_text = {"1": "Scheduled", "2": "In Progress", "3": "Final"}.get(status_code, "")

    abstract = ""
    if status_code == "3":
        abstract = "final"
    elif status_code == "2":
        abstract = "live"
    elif status_code == "1":
        abstract = "preview"

    game_date = game.get("gameTimeUTC") or game.get("gameTime") or game.get("startTimeUTC") or game.get("gameDate")
    mapped: Dict[str, Any] = {
        "gamePk": game.get("gameId") or game.get("id") or game.get("gameCode"),
        "gameDate": game_date,
        "status": {
            "statusCode": status_code,
            "detailedState": status_text,
        },
        "teams": {
            "away": _map_team(game.get("awayTeam") or game.get("away")),
            "home": _map_team(game.get("homeTeam") or game.get("home")),
        },
    }
    if abstract:
        mapped["status"]["abstractGameState"] = abstract

    period_number, period_type, final_period = _parse_period_info(game)
    clock = _normalize_clock(game.get("gameClock") or game.get("clock"))

    linescore: Dict[str, Any] = {}
    if period_number is not None:
        is_ot = False
        if period_number > 4 or period_type in {"OT", "OVERTIME"}:
            is_ot = True
            ot_number = period_number - 4 if period_number > 4 else period_number
            linescore["currentPeriodOrdinal"] = _ordinal_from_number(ot_number, is_overtime=True)
        else:
            linescore["currentPeriodOrdinal"] = _ordinal_from_number(period_number)
        linescore["finalPeriod"] = period_number if status_code == "3" else final_period or period_number
    elif final_period is not None:
        linescore["finalPeriod"] = final_period

    if clock:
        linescore["currentPeriodTimeRemaining"] = clock

    if linescore:
        mapped["linescore"] = linescore

    start_local = _timestamp_to_local(mapped.get("gameDate"))
    if start_local:
        mapped["_start_local"] = start_local
        mapped["_start_sort"] = start_local.timestamp()

    return mapped


def _fetch_games_for_date(day: datetime.date) -> list[dict]:
    def _load_json(url: str) -> Optional[Dict[str, Any]]:
        try:
            response = _SESSION.get(url, timeout=REQUEST_TIMEOUT, headers=_NBA_HEADERS)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logging.error("Failed to fetch NBA scoreboard from %s: %s", url, exc)
            return None

    base = "https://cdn.nba.com/static/json/liveData/scoreboard"
    date_url = f"{base}/scoreboard_{day.strftime('%Y%m%d')}.json"
    data = _load_json(date_url)

    if data is None and day == datetime.date.today():
        today_url = f"{base}/todaysScoreboard.json"
        data = _load_json(today_url)

    if not isinstance(data, dict):
        return []

    games_raw: Iterable[dict] = []
    if isinstance(data.get("scoreboard"), dict):
        games_raw = data["scoreboard"].get("games") or []
    elif isinstance(data.get("games"), list):
        games_raw = data.get("games") or []

    mapped_games = [_map_game(game) for game in games_raw]
    return _hydrate_games(mapped_games)


def _render_scoreboard(games: list[dict]) -> Image.Image:
    canvas = _compose_canvas(games)

    dummy = Image.new("RGB", (WIDTH, 10), "black")
    dd = ImageDraw.Draw(dummy)
    try:
        l, t, r, b = dd.textbbox((0, 0), TITLE, font=TITLE_FONT)
        title_h = b - t
    except Exception:
        _, title_h = dd.textsize(TITLE, font=TITLE_FONT)

    content_top = title_h + TITLE_GAP
    img_height = max(HEIGHT, content_top + canvas.height)
    img = Image.new("RGB", (WIDTH, img_height), "black")
    draw = ImageDraw.Draw(img)

    try:
        l, t, r, b = draw.textbbox((0, 0), TITLE, font=TITLE_FONT)
        tw, th = r - l, b - t
        tx = (WIDTH - tw) // 2 - l
        ty = 0 - t
    except Exception:
        tw, th = draw.textsize(TITLE, font=TITLE_FONT)
        tx = (WIDTH - tw) // 2
        ty = 0
    draw.text((tx, ty), TITLE, font=TITLE_FONT, fill=(255, 255, 255))

    img.paste(canvas, (0, content_top))
    return img


def _scroll_display(display, full_img: Image.Image):
    if full_img.height <= HEIGHT:
        display.image(full_img)
        display.show()
        return

    max_offset = full_img.height - HEIGHT
    frame = full_img.crop((0, 0, WIDTH, HEIGHT))
    display.image(frame)
    display.show()
    time.sleep(SCROLL_PAUSE_TOP)

    for offset in range(SCROLL_STEP, max_offset + 1, SCROLL_STEP):
        frame = full_img.crop((0, offset, WIDTH, offset + HEIGHT))
        display.image(frame)
        display.show()
        time.sleep(SCROLL_DELAY)

    time.sleep(SCROLL_PAUSE_BOTTOM)


# ─── Public API ───────────────────────────────────────────────────────────────
@log_call
def draw_nba_scoreboard(display, transition: bool = False):
    games = _fetch_games_for_date(_scoreboard_date())

    if not games:
        clear_display(display)
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        draw = ImageDraw.Draw(img)
        try:
            l, t, r, b = draw.textbbox((0, 0), TITLE, font=TITLE_FONT)
            tw, th = r - l, b - t
            tx = (WIDTH - tw) // 2 - l
            ty = 0 - t
        except Exception:
            tw, th = draw.textsize(TITLE, font=TITLE_FONT)
            tx = (WIDTH - tw) // 2
            ty = 0
        draw.text((tx, ty), TITLE, font=TITLE_FONT, fill=(255, 255, 255))
        _center_text(draw, "No games today", STATUS_FONT, 0, WIDTH, HEIGHT // 2 - STATUS_ROW_H // 2, STATUS_ROW_H)
        if transition:
            return img
        display.image(img)
        display.show()
        time.sleep(SCROLL_PAUSE_BOTTOM)
        return None

    full_img = _render_scoreboard(games)
    if transition:
        _scroll_display(display, full_img)
        return None

    if full_img.height <= HEIGHT:
        display.image(full_img)
        display.show()
        time.sleep(SCROLL_PAUSE_BOTTOM)
        return None

    _scroll_display(display, full_img)
    return None


@log_call
def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render the NBA scoreboard to the OLED display")
    parser.add_argument("--transition", action="store_true", help="Animate the scoreboard as a transition")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        from waveshare_OLED import OLED_1in5_rgb
    except Exception as exc:  # pragma: no cover - hardware import
        logging.error("Failed to import OLED driver: %s", exc)
        return 1

    display = OLED_1in5_rgb.OLED_1in5_rgb()
    display.Init()

    try:
        draw_nba_scoreboard(display, transition=args.transition)
    finally:
        display.Dev_exit()

    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution path
    raise SystemExit(main())
