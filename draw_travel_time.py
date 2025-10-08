#!/usr/bin/env python3
"""Travel time screen helpers."""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw

from config import (
    CENTRAL_TIME,
    FONT_SCORE,
    FONT_STOCK_PRICE,
    FONT_TITLE_SPORTS,
    FONT_TRAVEL_HEADER,
    FONT_TRAVEL_TITLE,
    GOOGLE_MAPS_API_KEY,
    HEIGHT,
    TRAVEL_ACTIVE_WINDOW,
    TRAVEL_DESTINATION,
    TRAVEL_DIRECTIONS_URL,
    TRAVEL_ORIGIN,
    TRAVEL_TITLE,
    WIDTH,
)
from utils import (
    ScreenImage,
    choose_route_by_any,
    clear_display,
    fastest_route,
    fetch_directions_routes,
    format_duration_text,
    log_call,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: Google Directions fetching/parsing
# ──────────────────────────────────────────────────────────────────────────────

def _api_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY") or GOOGLE_MAPS_API_KEY

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: Google Directions fetching/parsing
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_routes(avoid_highways: bool = False) -> List[Dict[str, Any]]:
    return fetch_directions_routes(
        TRAVEL_ORIGIN,
        TRAVEL_DESTINATION,
        _api_key(),
        avoid_highways=avoid_highways,
        url=TRAVEL_DIRECTIONS_URL,
    )


def _pick_non_highway() -> Optional[dict]:
    routes = _fetch_routes(avoid_highways=True)
    return fastest_route(routes)


def _pick_interstate(routes: Iterable[dict], i_label: str, synonyms: Iterable[str]) -> Optional[dict]:
    tokens = [
        i_label,
        i_label.replace("-", " "),
        i_label.replace("-", ""),
        *synonyms,
    ]
    routes_list = list(routes)
    match = choose_route_by_any(routes_list, tokens)
    return match or fastest_route(routes_list)

@dataclass
class TravelTimeResult:
    """Container for travel time results."""

    value: str

    @classmethod
    def from_route(cls, route: Optional[dict]) -> "TravelTimeResult":
        return cls(format_duration_text(route))

    def normalized(self) -> str:
        return (self.value or "N/A").replace("mins", "min")


def get_travel_times() -> Dict[str, TravelTimeResult]:
    """Return formatted travel times keyed by route identifier."""

    try:
        base = _fetch_routes(avoid_highways=False)
        non_highway = _pick_non_highway()

        r_i94 = _pick_interstate(base, "I-94", ["I94", "Edens", "Dan Ryan"])
        r_i90 = _pick_interstate(base, "I-90", ["I90", "Kennedy"])

        return {
            "i94": TravelTimeResult.from_route(r_i94),
            "i90": TravelTimeResult.from_route(r_i90),
            "non_hw": TravelTimeResult.from_route(non_highway),
        }
    except Exception as exc:  # pragma: no cover - defensive guard for runtime issues
        logging.warning("Travel time parse failed: %s", exc)
        return {
            "i94": TravelTimeResult("N/A"),
            "i90": TravelTimeResult("N/A"),
            "non_hw": TravelTimeResult("N/A"),
        }

# ──────────────────────────────────────────────────────────────────────────────
# Drawing: interstate shields and green road sign
# ──────────────────────────────────────────────────────────────────────────────

def _draw_interstate_shield(number: str, height: int = 36) -> Image.Image:
    """Return an approximation of an interstate shield for the given number."""

    width = int(height * 0.9)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = max(6, height // 6)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=radius,
        fill=(255, 255, 255),
        outline=(255, 255, 255),
        width=2,
    )
    inset = 3
    draw.rounded_rectangle(
        (inset, inset, width - 1 - inset, height - 1 - inset),
        radius=radius - 2,
        fill=(0, 65, 155),
    )

    banner_height = max(int(height * 0.28), 12)
    draw.rectangle(
        (inset, inset, width - 1 - inset, inset + banner_height),
        fill=(200, 30, 35),
    )

    try:
        text_width, text_height = draw.textsize("INTERSTATE", font=FONT_TRAVEL_HEADER)
        if text_width < (width - 2 * inset):
            draw.text(
                ((width - text_width) // 2, inset + (banner_height - text_height) // 2),
                "INTERSTATE",
                font=FONT_TRAVEL_HEADER,
                fill=(255, 255, 255),
            )
    except Exception:  # pragma: no cover - defensive
        pass

    number_text = str(number)
    num_width, num_height = draw.textsize(number_text, font=FONT_SCORE)
    y_text = inset + banner_height + ((height - inset - banner_height) - num_height) // 2
    draw.text(
        ((width - num_width) // 2, y_text),
        number_text,
        font=FONT_SCORE,
        fill=(255, 255, 255),
    )
    return img

def _draw_green_sign(text: str, height: int = 36) -> Image.Image:
    width = int(height * 1.5)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=8,
        fill=(16, 100, 16),
        outline=(255, 255, 255),
        width=2,
    )
    text_width, text_height = draw.textsize(text, font=FONT_TRAVEL_HEADER)
    draw.text(
        ((width - text_width) // 2, (height - text_height) // 2),
        text,
        font=FONT_TRAVEL_HEADER,
        fill=(255, 255, 255),
    )
    return img

# ──────────────────────────────────────────────────────────────────────────────
# Composition
# ──────────────────────────────────────────────────────────────────────────────

def _compose_travel_image(times: Dict[str, TravelTimeResult]) -> Image.Image:
    """Return a rendered travel time image for the provided timings."""

    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    title_width, title_height = draw.textsize(TRAVEL_TITLE, font=FONT_TITLE_SPORTS)
    draw.text(
        ((WIDTH - title_width) // 2, 0),
        TRAVEL_TITLE,
        font=FONT_TITLE_SPORTS,
        fill=(255, 255, 255),
    )

    top = title_height + 4
    sign_height = 46
    gap_vertical = 4
    gap_horizontal = 6

    lane_definitions: List[Tuple[str, Callable[[], Image.Image], Tuple[int, int, int]]] = [
        ("i94", lambda: _draw_interstate_shield("94", height=sign_height), (90, 160, 255)),
        ("i90", lambda: _draw_interstate_shield("90", height=sign_height), (200, 170, 255)),
        ("non_hw", lambda: _draw_green_sign("NON-HWY", height=sign_height), (160, 255, 160)),
    ]

    lane_images: List[Tuple[Image.Image, TravelTimeResult, Tuple[int, int, int]]] = []
    for key, factory, color in lane_definitions:
        lane_images.append((factory(), times.get(key, TravelTimeResult("N/A")), color))

    time_font = FONT_STOCK_PRICE
    column_widths = []
    for sign_image, time_result, _ in lane_images:
        time_text = time_result.value or "N/A"
        width, _ = draw.textsize(time_text, font=time_font)
        column_widths.append(max(sign_image.width, width))

    total_width = sum(column_widths) + gap_horizontal * (len(column_widths) - 1)
    x_offset = (WIDTH - total_width) // 2
    y_sign = top
    y_time = y_sign + sign_height + gap_vertical

    for index, (sign_image, time_result, color) in enumerate(lane_images):
        column_width = column_widths[index]
        paste_x = x_offset + (column_width - sign_image.width) // 2
        img.paste(sign_image, (paste_x, y_sign), sign_image)

        normalized = time_result.normalized()
        fill_color = color if normalized.upper() != "N/A" else (180, 180, 180)
        text_width, text_height = draw.textsize(normalized, font=time_font)
        time_x = x_offset + (column_width - text_width) // 2
        draw.text((time_x, y_time), normalized, font=time_font, fill=fill_color)

        x_offset += column_width + gap_horizontal

    if all(result.normalized().upper() == "N/A" for _, result, _ in lane_images):
        warning = "Travel data unavailable · Check Google Directions API"
        warning_width, warning_height = draw.textsize(warning, font=FONT_TRAVEL_HEADER)
        draw.text(
            ((WIDTH - warning_width) // 2, HEIGHT - warning_height - 1),
            warning,
            font=FONT_TRAVEL_HEADER,
            fill=(200, 200, 200),
        )

    return img

# ──────────────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────────────

def is_travel_screen_active(now: Optional[dt.time] = None) -> bool:
    start, end = TRAVEL_ACTIVE_WINDOW
    now = now or dt.datetime.now(CENTRAL_TIME).time()

    if start <= end:
        active = start <= now < end
    else:
        active = now >= start or now < end

    if not active:
        logging.debug("Travel screen skipped—outside active window.")

    return active


@log_call
def draw_travel_time_screen(
    display,
    transition: bool = False,
) -> Optional[Image.Image | ScreenImage]:
    if not is_travel_screen_active():
        return None

    times = get_travel_times()
    img = _compose_travel_image(times)

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(4)
    return ScreenImage(img, displayed=True)


__all__ = [
    "draw_travel_time_screen",
    "get_travel_times",
    "is_travel_screen_active",
]
