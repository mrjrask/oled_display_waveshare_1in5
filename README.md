# OLED Scoreboard & Info Display (Waveshare 1.5" RGB SSD1351)

A tiny, always‑on scoreboard and info display that runs on a Raspberry Pi and a Waveshare 1.5" RGB OLED (SSD1351). It cycles through date/time, weather, travel time, indoor sensors, stocks, Blackhawks & Bears screens, MLB standings, and Cubs/White Sox game views (last/live/next).

> **Highlights**
> - Smooth animations: scroll and fade‑in
> - Rich MLB views: last/live/next game, standings (divisions, overview, wild card)
> - **Cubs W/L result** full‑screen flag (animated WebP supported; PNG fallback)
> - **Smart screenshots** auto‑archived in batches when the live folder reaches 500 images
> - **GitHub update dot** on date/time screens when new commits are available
> - Screen sequencing via `screens_config.json`

---

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Images & Fonts](#images--fonts)
- [Screens](#screens)
- [Running](#running)
- [Systemd unit](#systemd-unit)
- [Screenshots & archiving](#screenshots--archiving)
- [GitHub update indicator](#github-update-indicator)
- [Troubleshooting](#troubleshooting)

---

## Requirements

- Raspberry Pi (tested on Pi Zero/Zero 2 W)
- Waveshare **OLED 1.5\" RGB (SSD1351)** wired to SPI0
- Python 3.9+
- Packages (install via apt / pip):
  ```bash
  sudo apt-get update
  sudo apt-get install -y python3-pip python3-pil libopenjp2-7 libtiff5
  pip3 install pillow requests colorama spidev gpiozero
  ```
  Pillow on current Raspberry Pi OS builds usually includes **WebP** support. If animated WebP is not rendering, upgrade Pillow:
  ```bash
  pip3 install --upgrade pillow
  ```

---

## Install

Clone your repo into (for example) `~/oled_display_waveshare_1in5` and copy your `*.py` files plus the `images/` and `fonts/` folders into place.

```bash
cd ~/oled_display_waveshare_1in5
```

---

## Project layout

```
oled_display_waveshare_1in5/
├─ main.py
├─ config.py
├─ utils.py
├─ data_fetch.py
├─ wifi_utils.py
├─ draw_date_time.py
├─ draw_weather.py
├─ draw_travel_time.py
├─ draw_vrnof.py
├─ draw_inside.py
├─ draw_bears_schedule.py
├─ draw_hawks_schedule.py
├─ mlb_schedule.py
├─ mlb_standings.py
├─ mlb_team_standings.py
├─ images/
│  ├─ mlb/<ABBR>.png              # MLB team logos (e.g., CUBS.png)
│  ├─ nfl/<ABBR>.png              # NFL logos used by Bears screen
│  ├─ W_flag.webp / L_flag.webp   # animated WebP flags (preferred)
│  ├─ W.png / L.png               # fallback PNG flags
│  ├─ cubs.jpg, sox.jpg, hawks.jpg, mlb.jpg, weather.jpg, verano.jpg, bears.png
└─ fonts/
   ├─ TimesSquare-m105.ttf
   ├─ DejaVuSans.ttf
   └─ DejaVuSans-Bold.ttf
```

---

## Configuration

Most runtime behavior is controlled in `config.py`:

- **Display:** `WIDTH=128`, `HEIGHT=128`, `SPI_FREQUENCY=30_000_000`
- **Intervals:** `SCREEN_DELAY`, `SCHEDULE_UPDATE_INTERVAL`
- **Feature flags:** `ENABLE_SCREENSHOTS`, `ENABLE_VIDEO`, `ENABLE_WIFI_MONITOR`
- **Weather:** `ENABLE_WEATHER`, `OWM_API_KEY`, `LATITUDE/LONGITUDE`
- **Travel:** `GOOGLE_MAPS_API_KEY`, `TRAVEL_MODE` (`to_home` or `to_work`)
- **MLB:** constants and timezone `CENTRAL_TIME`
- **Fonts:** make sure `fonts/` contains the TTFs above

### Screen sequencing

`screens_config.json` lets you enable/disable screens and place them into numbered sequences. Example:

```json
{
  "screens": {
    "date": 1,
    "time": 1,
    "weather1": 1,
    "cubs last": 2,
    "cubs live": 2,
    "cubs next": 2,
    "NL Overview": 1,
    "AL Overview": 1
  }
}
```

- A value of **`false`** hides the screen.
- A value of **`1`** shows the screen on **every** sequence.
- Any value **`>1`** shows the screen only when the main loop is on that sequence number. The length of the cycle is the highest such number in the file.

---

## Images & Fonts

- **MLB logos:** put team PNGs into `images/mlb/` named with your abbreviations (e.g., `CUBS.png`, `MIL.png`).
- **NFL logos:** for the Bears screen, `images/nfl/<abbr>.png` (e.g., `gb.png`, `min.png`).
- **Cubs W/L flag:** use `images/W_flag.webp` and `images/L_flag.webp` (animated). If missing, the code falls back to `images/W.png` / `images/L.png`.
- **Fonts:** copy `TimesSquare-m105.ttf`, `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf` into `fonts/`.

---

## Screens

- **Date/Time:** both screens display date & time in bright/legible colors with a red dot when updates are available.
- **Weather (1/2):** Open‑Meteo + OWM configuration.
- **Inside:** BME sensor summary (labels/values) if wired.
- **VRNOF:** stock mini‑panel.
- **Travel:** Maps ETA using your configured mode.
- **Bears Next:** opponent and logos row, formatted bottom line.
- **Blackhawks:** last/live/next based on schedule feed, logos included.
- **MLB (Cubs/Sox):**
  - **Last Game:** box score with **bold W/L** in the title.
  - **Live Game:** box score with inning/state as the bottom label.
  - **Next Game:** AWAY @ HOME logos row with day/date/time label using **Today / Tonight / Tomorrow / Yesterday** logic.
  - **Cubs Result:** full‑screen **W/L flag** (animated WebP 100×100 centered; PNG fallback).

- **MLB Standings:**
  - **Overview (AL/NL):** 3 columns of division logos (East/Central/West) with **drop‑in** animation (last place drops first).
  - **Divisions (AL/NL East/Central/West):** scrolling list with W‑L, GB.
  - **Wild Card (AL/NL):** bottom→top scroll with WCGB formatting and separator line.

---

## Running

Run directly:

```bash
python3 main.py
```

Or install the included systemd service (see below).

---

## Systemd unit

Create `/etc/systemd/system/oled_display-main.service`:

```ini
[Unit]
Description=OLED Display Service -main
After=network-online.target

[Service]
WorkingDirectory=/home/pi/oled_display_waveshare_1in5
ExecStart=/usr/bin/python3 /home/pi/oled_display_waveshare_1in5/main.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Enable & start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oled_display-main.service
sudo systemctl start oled_display-main.service
journalctl -u oled_display-main.service -f
```

---

## Screenshots & archiving

- Screenshots land in `./screenshots/` when `ENABLE_SCREENSHOTS=True`.
- **Batch archiving:** once the live folder reaches **500** images, the program moves the **entire batch** into `./screenshot_archive/YYYYMMDD/HHMMSS/` (images only).
- You will **not** see per‑image pruning logs; instead you’ll see a single archive log like: `🗃️ Archived 500 screenshot(s) → …`

> Tip: videos (if enabled) are written to `screenshots/oled_output.mp4` and aren’t moved by the archiver.

---

## GitHub update indicator

`utils.check_github_updates()` compares local HEAD with `origin/HEAD`. If they differ, a **red dot** appears at the lower‑left of date/time screens.

The checker now logs **which files have diverged** when updates exist, for easier review (uses `git diff --name-only HEAD..origin/HEAD`).

---

## Troubleshooting

- **Too‑dark colors on date/time:** this project forces high‑brightness random RGB values to ensure legibility on OLED.
- **Missing logos:** you’ll see a warning like `Logo file missing: CUBS.png`. Add the correct file into `images/mlb/`.
- **No WebP animation:** ensure your Pillow build supports WebP (`pip3 show pillow`). PNG fallback will still work.
- **Network/API errors:** MLB/OWM requests are time‑bounded; transient timeouts are logged and screens are skipped gracefully.
- **Font not found:** the code falls back to `ImageFont.load_default()` so the app keeps running; install the missing TTFs to restore look.

---

## License

Personal / hobby project. Use at your own risk. Team names and logos belong to their respective owners.
