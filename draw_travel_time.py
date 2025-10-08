#!/usr/bin/env python3
"""
Travel time screen (redesigned):
- Three big lanes with road signs: I-94, I-90, and Non-Highway
- Uses Google **Directions API** with alternatives + traffic (best_guess)
- Falls back gracefully and never crashes the loop
- Colorful, fully centered layout for 128×128

Notes
-----
• Requires an API key with **Directions API** enabled. (Distance Matrix not required, but you can enable it.)
• We read the key from config.GOOGLE_MAPS_API_KEY, or env GOOGLE_MAPS_API_KEY if set.
"""
import os
import time
import datetime as dt
import logging
from typing import Optional, Tuple, Dict, Any, List

from PIL import Image, ImageDraw

from config import (
    WIDTH, HEIGHT,
    CENTRAL_TIME,
    FONT_TRAVEL_TITLE, FONT_TRAVEL_HEADER, FONT_TRAVEL_VALUE,
    FONT_TITLE_SPORTS, FONT_STOCK_PRICE, FONT_SCORE,
    GOOGLE_MAPS_API_KEY,
    TRAVEL_ORIGIN,
    TRAVEL_DESTINATION,
    TRAVEL_TITLE,
    TRAVEL_ACTIVE_WINDOW,
    TRAVEL_DIRECTIONS_URL,
)
from utils import (
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


def _pick_interstate(routes: list, i_label: str, synonyms: List[str]) -> Optional[dict]:
    tokens = [i_label, i_label.replace("-", " "), i_label.replace("-", "-"), i_label.replace("-", ""), *synonyms]
    match = choose_route_by_any(routes, tokens)
    return match or fastest_route(routes)

def get_travel_times() -> Dict[str, str]:
    """
    Returns dictionary:
      {
        "i94": "12 min",
        "i90": "14 min",
        "non_hw": "29 min"
      }
    Any value may be "N/A" if nothing usable was returned.
    """
    try:
        base = _fetch_routes(avoid_highways=False)
        nonh = _pick_non_highway()

        # Robust picks with Chicago synonyms
        r_i94 = _pick_interstate(base, "I-94", ["I94","Edens","Dan Ryan"])
        r_i90 = _pick_interstate(base, "I-90", ["I90","Kennedy"])

        return {
            "i94":   format_duration_text(r_i94),
            "i90":   format_duration_text(r_i90),
            "non_hw": format_duration_text(nonh),
        }
    except Exception as e:
        logging.warning("Travel time parse failed: %s", e)
        return {"i94":"N/A","i90":"N/A","non_hw":"N/A"}

# ──────────────────────────────────────────────────────────────────────────────
# Drawing: interstate shields and green road sign
# ──────────────────────────────────────────────────────────────────────────────

def _draw_interstate_shield(number: str, height: int = 36) -> Image.Image:
    """
    Interstate-style shield (approx):
      - White outer stroke, then blue field
      - Red top banner with 'INTERSTATE'
      - Large white route number centered
    """
    # Canvas & proportions
    w = int(height * 0.9)
    img = Image.new("RGBA", (w, height), (0,0,0,0))
    d = ImageDraw.Draw(img)

    # Outer white border via two rounded rects
    radius = max(6, height // 6)
    d.rounded_rectangle((0, 0, w-1, height-1), radius=radius, fill=(255,255,255), outline=(255,255,255), width=2)
    inset = 3
    d.rounded_rectangle((inset, inset, w-1-inset, height-1-inset), radius=radius-2, fill=(0, 65, 155))

    # Red banner
    band_h = max( int(height * 0.28), 12 )
    d.rectangle((inset, inset, w-1-inset, inset + band_h), fill=(200, 30, 35))

    # 'INTERSTATE' label (tiny)
    try:
        small = FONT_TRAVEL_HEADER
        tw, th = d.textsize("INTERSTATE", font=small)
        if tw < (w - 2*inset):
            d.text(((w - tw)//2, inset + (band_h - th)//2), "INTERSTATE", font=small, fill=(255,255,255))
    except Exception:
        pass

    # Big route number (white) centered in blue area
    num_font = FONT_SCORE  # big, bold route number
    label = str(number)
    tw, th = d.textsize(label, font=num_font)
    y_text = inset + band_h + ((height - inset - band_h) - th)//2
    d.text(((w - tw)//2, y_text), label, font=num_font, fill=(255,255,255))
    return img

def _draw_green_sign(text: str, height: int = 36) -> Image.Image:
    """
    Simple green highway-style sign for NON-HWY.
    """
    w = int(height * 1.5)
    img = Image.new("RGBA", (w, height), (0,0,0,0))
    d = ImageDraw.Draw(img)
    border = 3
    d.rounded_rectangle((0,0,w-1,height-1), radius=8, fill=(16,100,16), outline=(255,255,255), width=2)
    # centered label
    tw, th = d.textsize(text, font=FONT_TRAVEL_HEADER)
    d.text(((w - tw)//2, (height - th)//2), text, font=FONT_TRAVEL_HEADER, fill=(255,255,255))
    return img

# ──────────────────────────────────────────────────────────────────────────────
# Composition
# ──────────────────────────────────────────────────────────────────────────────

def _compose_travel_image(times: Dict[str,str]) -> Image.Image:
    """
    Build a full 128×128 image with title, three lanes, big times.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d   = ImageDraw.Draw(img)

    # Title (use global title style to match other pages)
    tw, th = d.textsize(TRAVEL_TITLE, font=FONT_TITLE_SPORTS)
    d.text(((WIDTH - tw)//2, 0), TRAVEL_TITLE, font=FONT_TITLE_SPORTS, fill=(255,255,255))

    # Layout constants
    top = th + 4
    sign_h = 46       # bigger signs
    time_font = FONT_STOCK_PRICE  # BIG
    gap_v  = 4
    gap_h  = 6

    # Three columns: I-94, I-90, NON-HWY
    shield_94 = _draw_interstate_shield("94", height=sign_h)
    shield_90 = _draw_interstate_shield("90", height=sign_h)
    sign_non  = _draw_green_sign("NON-HWY", height=sign_h)

    items = [
        ("I-94", shield_94, times.get("i94","N/A"), (90,160,255)),  # bluish
        ("I-90", shield_90, times.get("i90","N/A"), (200,170,255)), # violet
        ("NON",  sign_non,  times.get("non_hw","N/A"), (160,255,160)), # green
    ]

    # Column widths are max(sign_w, time_w)
    time_samples = []
    for _, _, t, _ in items:
        t_str = t if t else "N/A"
        tw_, th_ = d.textsize(t_str, font=time_font)
        time_samples.append((t_str, tw_, th_))

    sign_ws = [items[i][1].width for i in range(3)]
    col_ws  = [max(sign_ws[i], time_samples[i][1]) for i in range(3)]
    total_w = sum(col_ws) + gap_h * 2
    x0 = (WIDTH - total_w)//2

    # Draw columns
    y_sign = top
    y_time = y_sign + sign_h + gap_v

    for i in range(3):
        label, sign_img, t_str, color = items[i]
        col_w = col_ws[i]
        # paste sign centered in column
        sx = x0 + (col_w - sign_img.width)//2
        img.paste(sign_img, (sx, y_sign), sign_img)

        # Draw time large and centered
        # If value looks like "12 mins", normalize to "12 min"
        t_norm = (t_str or "N/A").replace("mins", "min")
        # Color gray if N/A
        col_use = color if (t_norm.upper() != "N/A") else (180, 180, 180)
        wt, ht = d.textsize(t_norm, font=time_font)
        tx = x0 + (col_w - wt)//2
        d.text((tx, y_time), t_norm, font=time_font, fill=col_use)

        x0 += col_w + gap_h

    # If all values are N/A, show a subtle hint at bottom
    t_i94 = items[0][2].upper()
    t_i90 = items[1][2].upper()
    t_non = items[2][2].upper()
    all_na = (t_i94 == "N/A" and t_i90 == "N/A" and t_non == "N/A")
    if all_na:
        warn = "Travel data unavailable · Check Google Directions API"
        ww, wh = d.textsize(warn, font=FONT_TRAVEL_HEADER)
        d.text(((WIDTH - ww)//2, HEIGHT - wh - 1), warn, font=FONT_TRAVEL_HEADER, fill=(200,200,200))

    return img

# ──────────────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────────────

@log_call
def draw_travel_time_screen(display, transition=False):
    # Time-of-day guard (retain original behavior)
    now = dt.datetime.now(CENTRAL_TIME).time()
    start, end = TRAVEL_ACTIVE_WINDOW

    if start <= end:
        active = start <= now < end
    else:
        active = now >= start or now < end

    if not active:
        logging.debug("Travel screen skipped—outside active window.")
        return None

    # Fetch travel times (robust, never raises)
    times = get_travel_times()

    img = _compose_travel_image(times)

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(4)
    return None
