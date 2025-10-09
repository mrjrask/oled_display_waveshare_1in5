#!/usr/bin/env python3
"""Render NFL standings screens for the NFC and AFC conferences."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from config import (
    WIDTH,
    HEIGHT,
    FONT_TITLE_SPORTS,
    FONT_STATUS,
    IMAGES_DIR,
)
from http_client import get_session
from utils import ScreenImage, clear_display, clone_font, load_team_logo, log_call

# ─── Constants ────────────────────────────────────────────────────────────────
TITLE_NFC = "NFL Standings – NFC"
TITLE_AFC = "NFL Standings – AFC"
STANDINGS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings"
REQUEST_TIMEOUT = 10
CACHE_TTL = 15 * 60  # seconds

CONFERENCE_NFC_KEY = "NFC"
CONFERENCE_AFC_KEY = "AFC"

LOGO_DIR = os.path.join(IMAGES_DIR, "nfl")
LOGO_HEIGHT = 22
LEFT_MARGIN = 4
ROW_PADDING = 3
ROW_SPACING = 2
TITLE_MARGIN_TOP = 4
TITLE_MARGIN_BOTTOM = 6
DIVISION_MARGIN_TOP = 2
DIVISION_MARGIN_BOTTOM = 4
COLUMN_GAP_BELOW = 3
SCROLL_STEP = 1
SCROLL_DELAY = 0.04
SCROLL_PAUSE_TOP = 0.75
SCROLL_PAUSE_BOTTOM = 0.5

TITLE_FONT = FONT_TITLE_SPORTS
DIVISION_FONT = clone_font(FONT_TITLE_SPORTS, 14)
COLUMN_FONT = clone_font(FONT_STATUS, 13)
ROW_FONT = clone_font(FONT_STATUS, 15)

WHITE = (255, 255, 255)

_SESSION = get_session()

_MEASURE_IMG = Image.new("RGB", (1, 1))
_MEASURE_DRAW = ImageDraw.Draw(_MEASURE_IMG)

_STANDINGS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}
_LOGO_CACHE: Dict[str, Optional[Image.Image]] = {}

DIVISION_ORDER_NFC = ["NFC North", "NFC East", "NFC South", "NFC West"]
DIVISION_ORDER_AFC = ["AFC North", "AFC East", "AFC South", "AFC West"]

COLUMN_LAYOUT = {
    "team": LEFT_MARGIN + LOGO_HEIGHT + 6,
    "wins": 86,
    "losses": 104,
    "ties": 120,
}
COLUMN_HEADERS: List[tuple[str, str, str]] = [
    ("Team", "team", "left"),
    ("W", "wins", "right"),
    ("L", "losses", "right"),
    ("T", "ties", "right"),
]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _text_size(text: str, font) -> tuple[int, int]:
    try:
        l, t, r, b = _MEASURE_DRAW.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:  # pragma: no cover - PIL fallback
        return _MEASURE_DRAW.textsize(text, font)


ROW_TEXT_HEIGHT = _text_size("CHI", ROW_FONT)[1]
ROW_HEIGHT = max(LOGO_HEIGHT, ROW_TEXT_HEIGHT) + ROW_PADDING * 2
COLUMN_TEXT_HEIGHT = max(_text_size(label, COLUMN_FONT)[1] for label, _, _ in COLUMN_HEADERS)
COLUMN_ROW_HEIGHT = COLUMN_TEXT_HEIGHT + 2
DIVISION_TEXT_HEIGHT = _text_size("NFC North", DIVISION_FONT)[1]
TITLE_TEXT_HEIGHT = _text_size(TITLE_NFC, TITLE_FONT)[1]


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
            try:
                logo = load_team_logo(LOGO_DIR, candidate, height=LOGO_HEIGHT)
            except Exception as exc:  # pragma: no cover - defensive guard
                logging.debug("NFL logo load failed for %s: %s", candidate, exc)
                logo = None
            _LOGO_CACHE[cache_key] = logo
            return logo

    _LOGO_CACHE[cache_key] = None
    return None


def _normalize_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, str) and not value.strip():
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _normalize_conference(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    text = name.strip()
    if not text:
        return ""
    upper = text.upper()
    if "AFC" in upper:
        return CONFERENCE_AFC_KEY
    if "NFC" in upper:
        return CONFERENCE_NFC_KEY
    return text.title()


def _normalize_division(name: Any, conference: str = "") -> str:
    if not isinstance(name, str):
        name = ""
    text = (name or "").strip()
    if text.lower().endswith("division"):
        text = text[: -len("division")].strip()
    parts = text.split()
    normalized: List[str] = []
    seen_conference = False
    for part in parts:
        upper = part.upper()
        if upper in {CONFERENCE_AFC_KEY, CONFERENCE_NFC_KEY}:
            normalized.append(upper)
            seen_conference = True
        else:
            normalized.append(part.title())
    if not normalized and conference:
        normalized = [conference]
    if conference and not seen_conference:
        normalized.insert(0, conference)
    return " ".join(normalized).strip()


def _stat_map(stats: Iterable[dict]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for stat in stats or []:
        if not isinstance(stat, dict):
            continue
        name = stat.get("name") or stat.get("abbreviation")
        if not isinstance(name, str):
            continue
        value = stat.get("value")
        if value is None:
            value = stat.get("displayValue")
        mapping[name.lower()] = value
    return mapping


def _extract_entries(payload: Any) -> List[dict]:
    """Return the first set of overall standings entries found in *payload*."""

    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"]  # type: ignore[return-value]

    stack: List[Any] = [payload]
    candidates: List[tuple[str, List[dict]]] = []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            entries = node.get("entries")
            if isinstance(entries, list):
                label = str(node.get("name") or node.get("type") or node.get("displayName") or "").lower()
                candidates.append((label, entries))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)

    if not candidates:
        return []

    for label, entries in candidates:
        if "overall" in label or "league" in label:
            return entries
    return candidates[0][1]


def _parse_standings(data: Any) -> dict[str, dict[str, List[dict]]]:
    standings: dict[str, dict[str, List[dict]]] = {
        CONFERENCE_NFC_KEY: {},
        CONFERENCE_AFC_KEY: {},
    }

    entries = _extract_entries(data)
    if not entries:
        logging.warning("NFL standings response missing entries")
        return standings

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        team = entry.get("team") if isinstance(entry.get("team"), dict) else {}
        if not isinstance(team, dict):
            team = {}

        abbr = team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName")
        if isinstance(abbr, str):
            abbr = abbr.strip().upper()
        else:
            abbr = ""
        if not abbr:
            name = team.get("nickname") or team.get("name") or team.get("displayName") or ""
            abbr = name[:3].upper() if isinstance(name, str) else ""
        if not abbr:
            continue

        stats = _stat_map(entry.get("stats") or [])
        wins = _normalize_int(stats.get("wins") or stats.get("overallwins"))
        losses = _normalize_int(stats.get("losses") or stats.get("overalllosses"))
        ties = _normalize_int(stats.get("ties") or stats.get("overallties") or stats.get("draws"))
        rank = _normalize_int(stats.get("rank") or stats.get("overallrank") or stats.get("playoffseed"))

        conference_name = _normalize_conference(entry.get("conference"))
        if not conference_name and isinstance(entry.get("conference"), dict):
            conference_name = _normalize_conference(entry["conference"].get("name") or entry["conference"].get("displayName"))
        if not conference_name and isinstance(team.get("conference"), dict):
            conference_name = _normalize_conference(team["conference"].get("name") or team["conference"].get("displayName"))

        division_name = None
        for key in ("division", "group"):
            value = entry.get(key)
            if isinstance(value, dict):
                division_name = value.get("displayName") or value.get("name") or value.get("abbreviation")
                break
        if not division_name and isinstance(team.get("division"), dict):
            div = team["division"]
            division_name = div.get("displayName") or div.get("name") or div.get("abbreviation")

        if not conference_name and division_name:
            upper = str(division_name).upper()
            if upper.startswith(CONFERENCE_AFC_KEY):
                conference_name = CONFERENCE_AFC_KEY
            elif upper.startswith(CONFERENCE_NFC_KEY):
                conference_name = CONFERENCE_NFC_KEY

        if not conference_name:
            logging.debug("NFL standings skipping team %s without conference", abbr)
            continue

        division = _normalize_division(division_name or "", conference_name)
        if not division:
            logging.debug("NFL standings skipping team %s without division", abbr)
            continue

        conference_bucket = standings.setdefault(conference_name, {})
        division_bucket = conference_bucket.setdefault(division, [])
        division_bucket.append(
            {
                "abbr": abbr,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "order": rank if rank > 0 else len(division_bucket) + 1,
            }
        )

    # Sort each division by rank fallback to record
    for conference in standings.values():
        for division, teams in conference.items():
            teams.sort(
                key=lambda item: (
                    item.get("order", 999),
                    -item.get("wins", 0),
                    item.get("losses", 0),
                    -item.get("ties", 0),
                    item.get("abbr", ""),
                )
            )

    return standings


def _fetch_standings_data() -> dict[str, dict[str, List[dict]]]:
    now = time.time()
    cached = _STANDINGS_CACHE.get("data")
    timestamp = float(_STANDINGS_CACHE.get("timestamp", 0.0))
    if cached and now - timestamp < CACHE_TTL:
        return cached  # type: ignore[return-value]

    try:
        response = _SESSION.get(STANDINGS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network guard
        logging.error("Failed to fetch NFL standings: %s", exc)
        if isinstance(cached, dict):
            return cached  # type: ignore[return-value]
        return {
            CONFERENCE_NFC_KEY: {},
            CONFERENCE_AFC_KEY: {},
        }

    standings = _parse_standings(payload)
    _STANDINGS_CACHE["data"] = standings
    _STANDINGS_CACHE["timestamp"] = now
    return standings


def _division_section_height(team_count: int) -> int:
    height = DIVISION_MARGIN_TOP + DIVISION_TEXT_HEIGHT
    height += COLUMN_ROW_HEIGHT + COLUMN_GAP_BELOW
    if team_count > 0:
        height += team_count * ROW_HEIGHT + max(0, team_count - 1) * ROW_SPACING
    height += DIVISION_MARGIN_BOTTOM
    return height


def _render_conference(title: str, division_order: List[str], standings: Dict[str, List[dict]]) -> Image.Image:
    sections = [
        _division_section_height(len(standings.get(division, [])))
        for division in division_order
    ]
    content_height = sum(sections)
    total_height = max(
        HEIGHT,
        TITLE_MARGIN_TOP + TITLE_TEXT_HEIGHT + TITLE_MARGIN_BOTTOM + content_height,
    )
    img = Image.new("RGB", (WIDTH, total_height), "black")
    draw = ImageDraw.Draw(img)

    # Title
    try:
        l, t, r, b = draw.textbbox((0, 0), title, font=TITLE_FONT)
        tw, th = r - l, b - t
        tx = (WIDTH - tw) // 2 - l
        ty = TITLE_MARGIN_TOP - t
    except Exception:  # pragma: no cover - PIL fallback
        tw, th = draw.textsize(title, font=TITLE_FONT)
        tx = (WIDTH - tw) // 2
        ty = TITLE_MARGIN_TOP
    draw.text((tx, ty), title, font=TITLE_FONT, fill=WHITE)

    y = TITLE_MARGIN_TOP + TITLE_TEXT_HEIGHT + TITLE_MARGIN_BOTTOM

    for division, section_height in zip(division_order, sections):
        teams = standings.get(division, [])

        # Division header
        try:
            l, t, r, b = draw.textbbox((0, 0), division, font=DIVISION_FONT)
            tw, th = r - l, b - t
            tx = (WIDTH - tw) // 2 - l
            ty = y + DIVISION_MARGIN_TOP - t
        except Exception:  # pragma: no cover - PIL fallback
            tw, th = draw.textsize(division, font=DIVISION_FONT)
            tx = (WIDTH - tw) // 2
            ty = y + DIVISION_MARGIN_TOP
        draw.text((tx, ty), division, font=DIVISION_FONT, fill=WHITE)

        y_division_bottom = y + section_height
        row_y = y + DIVISION_MARGIN_TOP + DIVISION_TEXT_HEIGHT + COLUMN_GAP_BELOW

        # Column headers
        column_y = row_y
        for label, key, align in COLUMN_HEADERS:
            x = COLUMN_LAYOUT[key]
            if align == "right":
                try:
                    l, t, r, b = draw.textbbox((0, 0), label, font=COLUMN_FONT)
                    tw, th = r - l, b - t
                    tx = x - tw
                    ty = column_y - t
                except Exception:  # pragma: no cover - PIL fallback
                    tw, th = draw.textsize(label, font=COLUMN_FONT)
                    tx = x - tw
                    ty = column_y
            else:
                try:
                    l, t, r, b = draw.textbbox((0, 0), label, font=COLUMN_FONT)
                    tx = x - l
                    ty = column_y - t
                except Exception:  # pragma: no cover - PIL fallback
                    tx = x
                    ty = column_y
            draw.text((tx, ty), label, font=COLUMN_FONT, fill=WHITE)
        row_y += COLUMN_ROW_HEIGHT + ROW_SPACING

        # Team rows
        for team in teams:
            abbr = team.get("abbr", "")
            wins = str(team.get("wins", 0))
            losses = str(team.get("losses", 0))
            ties = str(team.get("ties", 0))

            # Logo
            logo = _load_logo_cached(abbr)
            if logo:
                logo_y = row_y + ROW_PADDING + (ROW_HEIGHT - ROW_PADDING * 2 - logo.height) // 2
                img.paste(logo, (LEFT_MARGIN, logo_y), logo)

            # Abbreviation
            try:
                l, t, r, b = draw.textbbox((0, 0), abbr, font=ROW_FONT)
                tw, th = r - l, b - t
                tx = COLUMN_LAYOUT["team"] - l
                ty = row_y + ROW_PADDING - t
            except Exception:  # pragma: no cover - PIL fallback
                tw, th = draw.textsize(abbr, font=ROW_FONT)
                tx = COLUMN_LAYOUT["team"]
                ty = row_y + ROW_PADDING
            draw.text((tx, ty), abbr, font=ROW_FONT, fill=WHITE)

            # Record columns
            for value, key in ((wins, "wins"), (losses, "losses"), (ties, "ties")):
                x = COLUMN_LAYOUT[key]
                try:
                    l, t, r, b = draw.textbbox((0, 0), value, font=ROW_FONT)
                    tw, th = r - l, b - t
                    tx = x - tw
                    ty = row_y + ROW_PADDING - t
                except Exception:  # pragma: no cover - PIL fallback
                    tw, th = draw.textsize(value, font=ROW_FONT)
                    tx = x - tw
                    ty = row_y + ROW_PADDING
                draw.text((tx, ty), value, font=ROW_FONT, fill=WHITE)

            row_y += ROW_HEIGHT + ROW_SPACING

        y = y_division_bottom

    return img


def _scroll_display(display, full_img: Image.Image):
    if full_img.height <= HEIGHT:
        display.image(full_img)
        display.show()
        time.sleep(SCROLL_PAUSE_BOTTOM)
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


def _render_and_display(display, title: str, division_order: List[str], standings: Dict[str, List[dict]], transition: bool) -> ScreenImage:
    if not any(standings.values()):
        clear_display(display)
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        draw = ImageDraw.Draw(img)
        message = "No standings"
        try:
            l, t, r, b = draw.textbbox((0, 0), title, font=TITLE_FONT)
            tw, th = r - l, b - t
            tx = (WIDTH - tw) // 2 - l
            ty = 0 - t
        except Exception:  # pragma: no cover - PIL fallback
            tw, th = draw.textsize(title, font=TITLE_FONT)
            tx = (WIDTH - tw) // 2
            ty = 0
        draw.text((tx, ty), title, font=TITLE_FONT, fill=WHITE)

        try:
            l, t, r, b = draw.textbbox((0, 0), message, font=ROW_FONT)
            tw, th = r - l, b - t
            tx = (WIDTH - tw) // 2 - l
            ty = (HEIGHT - th) // 2 - t
        except Exception:  # pragma: no cover - PIL fallback
            tw, th = draw.textsize(message, font=ROW_FONT)
            tx = (WIDTH - tw) // 2
            ty = (HEIGHT - th) // 2
        draw.text((tx, ty), message, font=ROW_FONT, fill=WHITE)

        if transition:
            return ScreenImage(img, displayed=False)
        display.image(img)
        display.show()
        time.sleep(SCROLL_PAUSE_BOTTOM)
        return ScreenImage(img, displayed=True)

    full_img = _render_conference(title, division_order, standings)
    if transition:
        _scroll_display(display, full_img)
        return ScreenImage(full_img, displayed=True)

    _scroll_display(display, full_img)
    return ScreenImage(full_img, displayed=True)


# ─── Public API ───────────────────────────────────────────────────────────────
@log_call
def draw_nfl_standings_nfc(display, transition: bool = False) -> ScreenImage:
    standings_by_conf = _fetch_standings_data()
    conference = standings_by_conf.get(CONFERENCE_NFC_KEY, {})
    return _render_and_display(display, TITLE_NFC, DIVISION_ORDER_NFC, conference, transition)


@log_call
def draw_nfl_standings_afc(display, transition: bool = False) -> ScreenImage:
    standings_by_conf = _fetch_standings_data()
    conference = standings_by_conf.get(CONFERENCE_AFC_KEY, {})
    return _render_and_display(display, TITLE_AFC, DIVISION_ORDER_AFC, conference, transition)


if __name__ == "__main__":  # pragma: no cover
    from waveshare_OLED import Display

    disp = Display()
    try:
        draw_nfl_standings_nfc(disp)
        draw_nfl_standings_afc(disp)
    finally:
        clear_display(disp)
