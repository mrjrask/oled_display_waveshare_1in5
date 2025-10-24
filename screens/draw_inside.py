#!/usr/bin/env python3
"""
draw_inside.py (RGB, 128x128)

Universal environmental sensor screen with a compact, modern layout:
  • Title (detects and names: Adafruit/Pimoroni BME680, BME688, BME280, SHT41)
  • Temperature (auto-fit)
  • Three rounded "chips": Humidity / Pressure (inHg) / VOC (or N/A if missing)
Everything is dynamically sized to fit 128×128 without clipping.
"""

from __future__ import annotations
import time
import logging
from typing import Optional, Tuple

from PIL import Image, ImageDraw
import config
from utils import (
    clear_display,
    fit_font,
    format_voc_ohms,
    measure_text,
    temperature_color,
)

# Optional HW libs (import lazily in _probe_sensor)
try:
    import board, busio  # type: ignore
except Exception:  # allows non-Pi dev boxes
    board = None
    busio = None

W, H = config.WIDTH, config.HEIGHT

# ── Universal sensor probe ───────────────────────────────────────────────────
def _probe_sensor():
    """
    Try drivers in a safe order. Returns (provider_name, read_fn) or (None, None)
    read_fn() -> dict with: temp_f, humidity, pressure_inhg, voc_ohms (or None)
    """
    if board is None or busio is None:
        logging.warning("BME* libs not available on this host; skipping sensor probe")
        return None, None

    i2c = busio.I2C(getattr(board, "SCL"), getattr(board, "SDA"))

    # 1) Adafruit BME680
    try:
        import adafruit_bme680  # type: ignore
        dev = adafruit_bme680.Adafruit_BME680_I2C(i2c)
        def read():
            temp_f = dev.temperature * 9/5 + 32
            hum    = float(dev.humidity)
            pres   = float(dev.pressure) * 0.02953
            voc    = float(getattr(dev, "gas", None)) if getattr(dev, "gas", None) is not None else None
            return dict(temp_f=temp_f, humidity=hum, pressure_inhg=pres, voc_ohms=voc)
        return "Adafruit BME680", read
    except Exception:
        pass

    # 2) Pimoroni BME688/BME680 via bme68x
    try:
        from bme68x import BME68X, I2C_ADDR_PRIMARY  # type: ignore
        dev = BME68X(i2c_addr=I2C_ADDR_PRIMARY)
        def read():
            data = dev.get_data()
            temp_f = float(data.temperature) * 9/5 + 32
            hum    = float(data.humidity)
            pres   = float(data.pressure) * 0.02953
            voc    = float(getattr(data, "gas_resistance", 0.0)) if getattr(data, "gas_resistance", None) else None
            return dict(temp_f=temp_f, humidity=hum, pressure_inhg=pres, voc_ohms=voc)
        return "Pimoroni BME688", read
    except Exception:
        pass

    # 3) Pimoroni BME280
    try:
        import pimoroni_bme280 as pim_bme280  # type: ignore
        dev = pim_bme280.BME280(i2c_dev=i2c)
        def read():
            temp_f = float(dev.get_temperature()) * 9/5 + 32
            hum    = float(dev.get_humidity())
            pres   = float(dev.get_pressure()) * 0.02953
            return dict(temp_f=temp_f, humidity=hum, pressure_inhg=pres, voc_ohms=None)
        return "Pimoroni BME280", read
    except Exception:
        pass

    # 4) Adafruit BME280
    try:
        import adafruit_bme280  # type: ignore
        dev = adafruit_bme280.Adafruit_BME280_I2C(i2c)
        def read():
            temp_f = float(dev.temperature) * 9/5 + 32
            hum    = float(dev.humidity)
            pres   = float(dev.pressure) * 0.02953
            return dict(temp_f=temp_f, humidity=hum, pressure_inhg=pres, voc_ohms=None)
        return "Adafruit BME280", read
    except Exception:
        pass

    # 5) Adafruit SHT41 / SHT4x family
    try:
        import adafruit_sht4x  # type: ignore
        dev = adafruit_sht4x.SHT4x(i2c)
        try:
            mode = getattr(adafruit_sht4x, "Mode", None)
            if mode is not None and hasattr(mode, "NOHEAT_HIGHPRECISION"):
                dev.mode = mode.NOHEAT_HIGHPRECISION
        except Exception:
            pass

        def read():
            temp_c, hum = dev.measurements
            temp_f = float(temp_c) * 9/5 + 32
            hum = float(hum)
            return dict(temp_f=temp_f, humidity=hum, pressure_inhg=None, voc_ohms=None)

        return "Adafruit SHT41", read
    except Exception:
        pass

    logging.warning("No supported indoor environmental sensor detected.")
    return None, None

# ── Chip drawing (LABEL left | VALUE right) ──────────────────────────────────
def _chip_lr(draw: ImageDraw.ImageDraw, rect: Tuple[int,int,int,int],
             bg: Tuple[int,int,int], label: str, value: str,
             label_base, value_base, center_gap_min=10,
             pad_x=8, pad_y=4):
    x0,y0,x1,y1 = rect
    # Slightly smaller radius to suit the shorter chips
    radius = max(7, min(12, (y1 - y0)//2))
    draw.rounded_rectangle(rect, radius=radius, fill=bg, outline=config.INSIDE_COL_STROKE)

    ix0, iy0 = x0 + pad_x, y0 + pad_y
    ix1, iy1 = x1 - pad_x, y1 - pad_y
    iw, ih   = max(0, ix1 - ix0), max(0, iy1 - iy0)

    # Split into left/right areas with a guaranteed center gap
    left_w  = int(iw * 0.46)
    right_w = int(iw * 0.46)
    gap = iw - (left_w + right_w)
    if gap < center_gap_min:
        shrink = (center_gap_min - gap + 1) // 2
        left_w  = max(16, left_w  - shrink)
        right_w = max(16, right_w - shrink)

    lx0, lx1 = ix0, ix0 + left_w
    rx1, rx0 = ix1, ix1 - right_w  # (rx0 < rx1)

    lw_max, lh_max = max(8, lx1 - lx0), max(10, ih)
    vw_max, vh_max = max(8, rx1 - rx0), max(10, ih)

    # Fit fonts tighter to shorter chips
    lf = fit_font(draw, label, label_base, lw_max, lh_max, min_pt=8,  max_pt=int(ih*0.62))
    vf = fit_font(draw, value, value_base, vw_max, vh_max, min_pt=9,  max_pt=int(ih*0.68))

    lw, lh = measure_text(draw, label, lf)
    vw, vh = measure_text(draw, value, vf)

    ly = iy0 + (ih - lh)//2
    vy = iy0 + (ih - vh)//2
    draw.text((lx0,      ly), label, font=lf, fill=config.INSIDE_COL_TEXT)
    draw.text((rx1 - vw, vy), value, font=vf, fill=config.INSIDE_COL_TEXT)

# ── Main render ──────────────────────────────────────────────────────────────
def draw_inside(display, transition: bool=False):
    provider, read_fn = _probe_sensor()
    if not read_fn:
        logging.warning("draw_inside: sensor not available")
        return None

    try:
        data = read_fn()
        temp_f = float(data["temp_f"])
        hum_raw = data.get("humidity")
        hum = float(hum_raw) if hum_raw is not None else None
        pres_raw = data.get("pressure_inhg")
        pres = float(pres_raw) if pres_raw is not None else None
        voc_raw = data.get("voc_ohms", None)
        voc = float(voc_raw) if voc_raw is not None else None
    except Exception as e:
        logging.warning(f"draw_inside: sensor read failed: {e}")
        return None

    # Title text
    title = f"Inside • {provider}"

    # Compose canvas
    img  = Image.new("RGB", (W, H), config.INSIDE_COL_BG)
    draw = ImageDraw.Draw(img)

    # Fonts (with fallbacks)
    title_base = getattr(config, "FONT_TITLE_INSIDE", config.FONT_TITLE_SPORTS)
    temp_base  = getattr(config, "FONT_TIME",        config.FONT_TITLE_SPORTS)
    label_base = getattr(config, "FONT_INSIDE_LABEL", getattr(config, "FONT_DATE_SPORTS", config.FONT_TITLE_SPORTS))
    value_base = getattr(config, "FONT_INSIDE_VALUE", getattr(config, "FONT_DATE_SPORTS", config.FONT_TITLE_SPORTS))

    # --- Title (auto-fit to width, compact height)
    title_max_h = 12
    t_font = fit_font(
        draw,
        title,
        title_base,
        max_width=W - 8,
        max_height=title_max_h,
        min_pt=9,
        max_pt=title_max_h + 2,
    )
    tw, th = measure_text(draw, title, t_font)
    draw.text(((W - tw)//2, 0), title, font=t_font, fill=config.INSIDE_COL_TITLE)

    # --- Temperature (auto-fit into a bounded block; slightly smaller)
    temp_txt     = f"{temp_f:.1f}°F"
    temp_area_h  = 22  # ↓ was 24; frees more space for shorter chips
    T_font = fit_font(
        draw,
        temp_txt,
        temp_base,
        max_width=W - 10,
        max_height=temp_area_h,
        min_pt=12,
        max_pt=temp_area_h + 2,
    )
    ttw, tth = measure_text(draw, temp_txt, T_font)
    t_y = th + 2 + max(0, (temp_area_h - tth)//2)
    draw.text(((W - ttw)//2, t_y), temp_txt, font=T_font, fill=temperature_color(temp_f))

    # --- Chips region (shorter chips, tighter gaps, smaller bottom margin)
    top_after_temp = th + 2 + temp_area_h
    bottom_margin  = 2      # ↓ was 3
    gap            = 2      # ↓ was 3
    chips_h_avail  = max(18, H - bottom_margin - top_after_temp)
    chip_h         = (chips_h_avail - 2*gap) // 3
    chip_h         = max(18, min(22, chip_h))  # ↓ clamp to 18–22px
    chips_total    = 3*chip_h + 2*gap
    chips_top      = H - bottom_margin - chips_total

    # Values
    hum_val = f"{hum:.1f}%" if hum is not None else "N/A"
    prs_val = f"{pres:.2f} inHg" if pres is not None else "N/A"
    voc_val = format_voc_ohms(voc)

    chips = [
        ("Humidity", hum_val, config.INSIDE_CHIP_BLUE),
        ("Pressure", prs_val, config.INSIDE_CHIP_AMBER),
        ("VOC",      voc_val, config.INSIDE_CHIP_PURPLE),
    ]

    side_pad = 6
    inner_w  = W - 2*side_pad
    y = chips_top
    for label, value, bg in chips:
        rect = (side_pad, y, side_pad + inner_w, y + chip_h)
        _chip_lr(draw, rect, bg, label, value, label_base, value_base,
                 center_gap_min=10, pad_x=8, pad_y=4)
        y += chip_h + gap

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(5)
    return None


if __name__ == "__main__":
    try:
        preview = draw_inside(None, transition=True)
        if preview:
            preview.show()
    except Exception:
        pass
