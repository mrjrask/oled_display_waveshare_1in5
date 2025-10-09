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
    FONT_TITLE_SPORTS,
    FONT_TRAVEL_HEADER,
    FONT_TRAVEL_TITLE,
    FONT_TRAVEL_VALUE,
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


SCROLL_STEP = 2
SCROLL_DELAY = 0.035
SCROLL_PAUSE_TOP = 1.0
SCROLL_PAUSE_BOTTOM = 1.0


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

    measurement_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def _measure(text: str, font) -> Tuple[int, int]:
        if hasattr(measurement_draw, "textbbox"):
            left, top, right, bottom = measurement_draw.textbbox((0, 0), text, font=font)
            return right - left, bottom - top
        return measurement_draw.textsize(text, font=font)

    lane_definitions: List[
        Tuple[str, str, Callable[[], Image.Image], Tuple[int, int, int]]
    ] = [
        (
            "i94",
            "I-94",
            lambda: _draw_interstate_shield("94", height=28),
            (90, 160, 255),
        ),
        (
            "i90",
            "I-90",
            lambda: _draw_interstate_shield("90", height=28),
            (200, 170, 255),
        ),
        (
            "non_hw",
            "NON-HWY",
            lambda: _draw_green_sign("NON-HWY", height=28),
            (160, 255, 160),
        ),
    ]

    rows: List[Dict[str, Any]] = []
    time_font = FONT_TRAVEL_VALUE
    label_font = FONT_TRAVEL_TITLE

    max_sign_height = 0
    max_time_height = 0
    max_label_height = 0

    for key, label, factory, color in lane_definitions:
        time_result = times.get(key, TravelTimeResult("N/A"))
        normalized = time_result.normalized()
        sign_image = factory()
        time_width, time_height = _measure(normalized, time_font)
        label_width, label_height = _measure(label, label_font)

        max_sign_height = max(max_sign_height, sign_image.height)
        max_time_height = max(max_time_height, time_height)
        max_label_height = max(max_label_height, label_height)

        rows.append(
            {
                "sign": sign_image,
                "normalized": normalized,
                "color": color,
                "label": label,
                "time_width": time_width,
                "time_height": time_height,
                "label_width": label_width,
                "label_height": label_height,
            }
        )

    title_width, title_height = _measure(TRAVEL_TITLE, FONT_TITLE_SPORTS)

    outer_margin = 6
    row_padding = 12
    row_gap = 10
    header_gap = 6
    row_height = max(max_sign_height, max_time_height, max_label_height) + 2 * row_padding

    all_na = all(row["normalized"].upper() == "N/A" for row in rows)
    warning_text = "Travel data unavailable · Check Google Directions API"
    warning_width, warning_height = _measure(warning_text, FONT_TRAVEL_HEADER)

    row_count = len(rows)
    content_height = (
        title_height
        + header_gap
        + row_count * row_height
        + max(0, row_count - 1) * row_gap
        + outer_margin
    )
    if all_na:
        content_height += warning_height + 6

    canvas_height = max(content_height, HEIGHT)
    img = Image.new("RGB", (WIDTH, canvas_height), "black")
    draw = ImageDraw.Draw(img)

    draw.text(
        ((WIDTH - title_width) // 2, 0),
        TRAVEL_TITLE,
        font=FONT_TITLE_SPORTS,
        fill=(255, 255, 255),
    )

    y = title_height + header_gap
    row_left = outer_margin
    row_right = WIDTH - outer_margin
    row_inner_gap = 10

    for row in rows:
        sign_image = row["sign"]
        normalized = row["normalized"]
        color = row["color"]
        label = row["label"]

        display_color = color if normalized.upper() != "N/A" else (230, 230, 230)

        row_top = y
        row_bottom = y + row_height

        draw.rounded_rectangle(
            (row_left, row_top, row_right, row_bottom),
            radius=12,
            fill=(28, 28, 28),
            outline=(80, 80, 80),
        )

        sign_x = row_left + row_padding
        sign_y = row_top + (row_height - sign_image.height) // 2
        img.paste(sign_image, (sign_x, sign_y), sign_image)

        text_left = sign_x + sign_image.width + row_inner_gap
        time_width = row["time_width"]
        time_height = row["time_height"]
        time_x = row_right - row_padding - time_width
        time_y = row_top + (row_height - time_height) // 2
        draw.text((time_x, time_y), normalized, font=time_font, fill=display_color)

        label_width = row["label_width"]
        label_height = row["label_height"]
        label_x = text_left
        label_y = row_top + (row_height - label_height) // 2
        draw.text((label_x, label_y), label, font=label_font, fill=(235, 235, 235))

        y = row_bottom + row_gap

    if all_na:
        warning_y = min(canvas_height - warning_height - 4, y)
        draw.text(
            ((WIDTH - warning_width) // 2, warning_y),
            warning_text,
            font=FONT_TRAVEL_HEADER,
            fill=(200, 200, 200),
        )

    return img


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────

def _scroll_travel_display(display, full_img: Image.Image) -> None:
    if display is None:
        return

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

    displayed = display is not None

    if transition:
        _scroll_travel_display(display, img)
        return ScreenImage(img, displayed=displayed)

    _scroll_travel_display(display, img)
    return ScreenImage(img, displayed=displayed)


__all__ = [
    "draw_travel_time_screen",
    "get_travel_times",
    "is_travel_screen_active",
]
