#!/usr/bin/env python3
import os
import json
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory, request

app = Flask(__name__, static_folder='screenshots', static_url_path='/screenshots')

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR  = os.path.join(SCRIPT_DIR, "screenshots")
CONFIG_PATH     = os.path.join(SCRIPT_DIR, "screens_config.json")
ADMIN_SERVICE   = "oled_admin.service"
DISPLAY_SERVICE = "oled_display.service"


def load_screen_config():
    """Return a mapping of screen id → frequency as integers.

    The display runtime treats a value of 0/False as disabled, ``1`` as every
    loop and any other positive integer as "once every N loops".  Older
    configuration files may store booleans or strings, so we normalise the
    values here before handing them to the template.
    """

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}

    raw_screens = data.get("screens", {}) if isinstance(data, dict) else {}

    normalised = {}
    for screen_id, raw_value in raw_screens.items():
        if raw_value in (False, None):
            normalised[screen_id] = 0
            continue

        try:
            freq = int(raw_value)
        except (TypeError, ValueError):
            freq = 1 if raw_value else 0

        normalised[screen_id] = max(freq, 0)

    return normalised


@app.route("/")
def index():
    # screens: list of (key, enabled)
    cfg = load_screen_config()
    screens = sorted(cfg.items(), key=lambda kv: kv[0])
    return render_template("admin.html", screens=screens)


@app.route("/save_config", methods=["POST"])
def save_config():
    data = request.get_json() or {}
    raw_screens = data.get("screens", {}) if isinstance(data, dict) else {}

    screens = {}
    for screen_id, raw_value in raw_screens.items():
        if raw_value in (False, None, ""):
            screens[screen_id] = 0
            continue

        try:
            freq = int(raw_value)
        except (TypeError, ValueError):
            freq = 1 if raw_value else 0

        screens[screen_id] = max(freq, 0)

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"screens": screens}, f, indent=2, sort_keys=True)
        return jsonify(status="success")
    except Exception as e:
        return jsonify(status="error", message=str(e)), 500


@app.route("/api/screenshots/<screen_id>")
def screenshots_for_screen(screen_id):
    safe = screen_id.replace(" ", "_")
    try:
        files = sorted(os.listdir(SCREENSHOT_DIR))
        matches = [f for f in files if f.startswith(safe + "_")]
    except Exception:
        matches = []
    return jsonify(matches)


@app.route("/logs")
def logs():
    out = {}
    for name, svc in (("Display", DISPLAY_SERVICE), ("Admin", ADMIN_SERVICE)):
        try:
            txt = subprocess.check_output(
                ["journalctl", "-u", svc, "-n", "100", "--no-pager"],
                stderr=subprocess.STDOUT
            ).decode()
        except Exception as e:
            txt = f"Error loading {name} logs: {e}"
        out[name] = txt
    return jsonify(out)


@app.route('/screenshots/<filename>')
def serve_screenshot(filename):
    return send_from_directory(SCREENSHOT_DIR, filename)


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
