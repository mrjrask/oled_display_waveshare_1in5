#!/usr/bin/env python3
"""
nfl_scoreboard.py

Render a scrolling NFL scoreboard mirroring the layout of the MLB board.
Shows the previous day's games until 9:30 AM Central, then switches to the
current day.
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from typing import Iterable, Optional

import requests
from PIL import Image, ImageDraw

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

# ─── Constants ────────────────────────────────────────────────────────────────
TITLE               = "NFL Scoreboard"
TITLE_GAP           = 8
BLOCK_SPACING       = 6
SCORE_ROW_H         = 26
STATUS_ROW_H        = 14
SCROLL_STEP         = 1
SCROLL_DELAY        = 0.04
SCROLL_PAUSE_TOP    = 0.75
SCROLL_PAUSE_BOTTOM = 0.5
REQUEST_TIMEOUT     = 10

COL_WIDTHS = [28, 24, 24, 24, 28]
COL_X = [0]
for w in COL_WIDTHS:
    COL_X.append(COL_X[-1] + w)

SCORE_FONT  = clone_font(FONT_TEAM_SPORTS, 18)
STATUS_FONT = clone_font(FONT_STATUS, 15)
CENTER_FONT = clone_font(FONT_STATUS, 15)
TITLE_FONT  = FONT_TITLE_SPORTS
LOGO_HEIGHT = 22
LOGO_DIR    = os.path.join(IMAGES_DIR, "nfl")

_LOGO_CACHE: dict[str, Optional[Image.Image]] = {}


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

    candidates = [cache_key, cache_key.lower(), cache_key.title()]
    for candidate in candidates:
        path = os.path.join(LOGO_DIR, f"{candidate}.png")
        if os.path.exists(path):
            logo = load_team_logo(LOGO_DIR, candidate, height=LOGO_HEIGHT)
            _LOGO_CACHE[cache_key] = logo
            return logo

    _LOGO_CACHE[cache_key] = None
    return None


def _team_logo_abbr(team: dict) -> str:
    if not isinstance(team, dict):
        return ""
    for key in ("abbreviation", "abbrev", "shortDisplayName", "displayName"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            candidate = value.strip().upper()
            for suffix in (candidate, candidate.lower()):
                if os.path.exists(os.path.join(LOGO_DIR, f"{suffix}.png")):
                    return candidate
    nickname = (team.get("nickname") or team.get("name") or "").strip()
    return nickname[:3].upper() if nickname else ""


def _should_display_scores(game: dict) -> bool:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    state = (type_info.get("state") or "").lower()
    if state in {"in", "post"}:
        return True
    if (type_info.get("completed") or False) is True:
        return True
    return False


def _score_text(side: dict, *, show: bool) -> str:
    if not show:
        return "—"
    score = (side or {}).get("score")
    return "—" if score is None else str(score)


def _format_status(game: dict) -> str:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    short_detail = (type_info.get("shortDetail") or "").strip()
    detail = (type_info.get("detail") or "").strip()
    state = (type_info.get("state") or "").lower()

    if state == "post":
        return short_detail or detail or "Final"
    if state == "in":
        clock = status.get("displayClock") or ""
        period = status.get("period")
        if clock and period:
            return f"{clock} Q{period}"
        return short_detail or detail or "In Progress"

    if state == "pre":
        start_local = game.get("_start_local")
        if isinstance(start_local, datetime.datetime):
            return start_local.strftime("%I:%M %p").lstrip("0")
        return short_detail or detail or "TBD"

    return short_detail or detail or "TBD"


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
    competitors = (game or {}).get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})

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
        logo = _load_logo_cached(abbr)
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
    try:
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%MZ")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(CENTRAL_TIME)


def _hydrate_games(raw_games: Iterable[dict]) -> list[dict]:
    games: list[dict] = []
    for game in raw_games:
        game = game or {}
        start_local = _timestamp_to_local(game.get("_event_date"))
        if start_local:
            game["_start_local"] = start_local
            game["_start_sort"] = start_local.timestamp()
        else:
            game["_start_sort"] = float("inf")
        games.append(game)
    games.sort(key=lambda g: (g.get("_start_sort", float("inf")), g.get("id") or g.get("uid") or 0))
    return games


def _fetch_games_for_date(day: datetime.date) -> list[dict]:
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        f"?dates={day.strftime('%Y%m%d')}"
    )
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logging.error("Failed to fetch NFL scoreboard: %s", exc)
        return []

    raw_games: list[dict] = []
    for event in data.get("events", []) or []:
        event_date = event.get("date")
        local_start = _timestamp_to_local(event_date)
        if local_start and local_start.date() != day:
            continue
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0] or {}
        comp = dict(comp)
        comp["_event_date"] = event_date
        raw_games.append(comp)
    return _hydrate_games(raw_games)


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
def draw_nfl_scoreboard(display, transition: bool = False):
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
        _center_text(draw, "No games", STATUS_FONT, 0, WIDTH, HEIGHT // 2 - STATUS_ROW_H // 2, STATUS_ROW_H)
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
    else:
        _scroll_display(display, full_img)
    return None


if __name__ == "__main__":  # pragma: no cover
    from utils import Display

    disp = Display()
    try:
        draw_nfl_scoreboard(disp)
    finally:
        clear_display(disp)
