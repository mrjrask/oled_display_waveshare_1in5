#!/usr/bin/env python3
"""
draw_weather.py

Two weather screens (basic + detailed) in RGB.

Screen 1:
  • Temp & description at top
  • 64×64 weather icon
  • Two-line Feels/Hi/Lo: labels on the line above values, each centered.

Screen 2:
  • Detailed info: Sunrise/Sunset, Wind, Gust, Humidity, Pressure, UV Index
  • Each label/value pair vertically centered within its row.
"""

import datetime
from PIL import Image, ImageDraw

from config import (
    WIDTH,
    HEIGHT,
    CENTRAL_TIME,
    FONT_TEMP,
    FONT_CONDITION,
    FONT_WEATHER_LABEL,
    FONT_WEATHER_DETAILS,
    FONT_WEATHER_DETAILS_BOLD,
    WEATHER_ICON_SIZE,
    WEATHER_DESC_GAP,
)
from utils import clear_display, fetch_weather_icon, log_call, timestamp_to_datetime, uv_index_color

# ─── Screen 1: Basic weather + two-line Feels/Hi/Lo ────────────────────────────
@log_call
def draw_weather_screen_1(display, weather, transition=False):
    if not weather:
        return None

    current = weather.get("current", {})
    daily   = weather.get("daily", [{}])[0]

    temp  = round(current.get("temp", 0))
    desc  = current.get("weather", [{}])[0].get("description", "").title()

    feels = round(current.get("feels_like", 0))
    hi    = round(daily.get("temp", {}).get("max", 0))
    lo    = round(daily.get("temp", {}).get("min", 0))

    clear_display(display)
    img  = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    # Temperature
    temp_str = f"{temp}°F"
    w_temp, h_temp = draw.textsize(temp_str, font=FONT_TEMP)
    draw.text(((WIDTH - w_temp)//2, 0), temp_str, font=FONT_TEMP, fill=(255,255,255))

    font_desc = FONT_CONDITION
    w_desc, h_desc = draw.textsize(desc, font=font_desc)
    if w_desc > WIDTH:
        font_desc = FONT_WEATHER_DETAILS_BOLD
        w_desc, h_desc = draw.textsize(desc, font=font_desc)
    draw.text(
        ((WIDTH - w_desc)//2, h_temp + WEATHER_DESC_GAP),
        desc,
        font=font_desc,
        fill=(255,255,255)
    )

    icon_code = current.get("weather", [{}])[0].get("icon")
    icon_img = fetch_weather_icon(icon_code, WEATHER_ICON_SIZE)

    # Feels/Hi/Lo groups
    labels    = ["Feels", "Hi", "Lo"]
    values    = [f"{feels}°", f"{hi}°", f"{lo}°"]
    # dynamic colors
    if feels > hi:
        feels_col = (255,165,0)
    elif feels < lo:
        feels_col = (128,0,128)
    else:
        feels_col = (255,255,255)
    val_colors = [feels_col, (255,0,0), (0,0,255)]

    groups = []
    for lbl, val in zip(labels, values):
        lw, lh = draw.textsize(lbl, font=FONT_WEATHER_LABEL)
        vw, vh = draw.textsize(val, font=FONT_WEATHER_DETAILS)
        gw = max(lw, vw)
        groups.append((lbl, lw, lh, val, vw, vh, gw))

    # horizontal layout
    SPACING_X = 12
    total_w   = sum(g[6] for g in groups) + SPACING_X * (len(groups)-1)
    x0        = (WIDTH - total_w)//2

    # vertical positions
    max_val_h = max(g[5] for g in groups)
    max_lbl_h = max(g[2] for g in groups)
    y_val     = HEIGHT - max_val_h - 4
    LABEL_GAP = 2
    y_lbl     = y_val - max_lbl_h - LABEL_GAP

    # paste icon between desc and labels
    if icon_img:
        top_of_icons = h_temp + h_desc + WEATHER_DESC_GAP * 2
        y_icon = top_of_icons + ((y_lbl - top_of_icons - WEATHER_ICON_SIZE)//2)
        img.paste(icon_img, ((WIDTH - WEATHER_ICON_SIZE)//2, y_icon), icon_img)

    # draw groups
    x = x0
    for idx, (lbl, lw, lh, val, vw, vh, gw) in enumerate(groups):
        cx = x + gw//2
        draw.text((cx - lw//2, y_lbl), lbl, font=FONT_WEATHER_LABEL,      fill=(255,255,255))
        draw.text((cx - vw//2, y_val), val, font=FONT_WEATHER_DETAILS,     fill=val_colors[idx])
        x += gw + SPACING_X

    if transition:
        return img

    display.image(img)
    display.show()
    return None


# ─── Screen 2: Detailed (with UV index) ───────────────────────────────────────
def draw_weather_screen_2(display, weather, transition=False):
    if not weather:
        return None

    current = weather.get("current", {})
    daily   = weather.get("daily", [{}])[0]

    now = datetime.datetime.now(CENTRAL_TIME)
    s_r = timestamp_to_datetime(daily.get("sunrise"), CENTRAL_TIME)
    s_s = timestamp_to_datetime(daily.get("sunset"), CENTRAL_TIME)

    # Sunrise or Sunset first
    if s_r and now < s_r:
        items = [("Sunrise:", s_r.strftime("%-I:%M %p"))]
    elif s_s:
        items = [("Sunset:",  s_s.strftime("%-I:%M %p"))]
    else:
        items = []

    # Other details
    items += [
        ("Wind:",     f"{round(current.get('wind_speed',0))} mph"),
        ("Gust:",     f"{round(current.get('wind_gust',0))} mph"),
        ("Humidity:", f"{current.get('humidity',0)}%"),
        ("Pressure:", f"{round(current.get('pressure',0)*0.0338639,2)} inHg"),
    ]

    uvi = round(current.get("uvi", 0))
    uv_col = uv_index_color(uvi)
    items.append(("UV Index:", str(uvi), uv_col))

    clear_display(display)
    img  = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    # compute per-row heights
    row_metrics = []
    total_h = 0
    for it in items:
        lbl, val = it[0], it[1]
        h1 = draw.textsize(lbl, font=FONT_WEATHER_DETAILS_BOLD)[1]
        h2 = draw.textsize(val, font=FONT_WEATHER_DETAILS)[1]
        row_h = max(h1, h2)
        row_metrics.append((lbl, val, row_h, h1, h2, it[2] if len(it)==3 else (255,255,255)))
        total_h += row_h

    # vertical spacing
    space = (HEIGHT - total_h) // (len(items) + 1)
    y = space

    # render each row, vertically centering label & value
    for lbl, val, row_h, h_lbl, h_val, color in row_metrics:
        lw, _ = draw.textsize(lbl, font=FONT_WEATHER_DETAILS_BOLD)
        vw, _ = draw.textsize(val, font=FONT_WEATHER_DETAILS)
        row_w = lw + 4 + vw
        x0    = (WIDTH - row_w)//2

        y_lbl = y + (row_h - h_lbl)//2
        y_val = y + (row_h - h_val)//2

        draw.text((x0,          y_lbl), lbl, font=FONT_WEATHER_DETAILS_BOLD, fill=(255,255,255))
        draw.text((x0 + lw + 4, y_val), val, font=FONT_WEATHER_DETAILS,      fill=color)
        y += row_h + space

    if transition:
        return img

    display.image(img)
    display.show()
    return None
