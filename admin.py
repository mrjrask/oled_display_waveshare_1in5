#!/usr/bin/env python3
import os
import json
import subprocess
from typing import Any, Dict, List, Tuple, Union

from flask import Flask, render_template, jsonify, send_from_directory, request

from schedule import KNOWN_SCREENS, build_scheduler
from screens_catalog import SCREEN_IDS

app = Flask(__name__, static_folder='screenshots', static_url_path='/screenshots')

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR  = os.path.join(SCRIPT_DIR, "screenshots")
CONFIG_PATH     = os.path.join(SCRIPT_DIR, "screens_config.json")
ADMIN_SERVICE   = "oled_admin.service"
DISPLAY_SERVICE = "oled_display.service"


ScheduleEntry = Union[str, Dict[str, Any]]

DEFAULT_SEQUENCE: List[ScheduleEntry] = ["date", "time"]


class ConfigValidationError(ValueError):
    """Raised when a provided configuration cannot be normalised."""


def _validate_screen_id(screen_id: str) -> str:
    if screen_id not in KNOWN_SCREENS:
        raise ConfigValidationError(f"Unknown screen id '{screen_id}'")
    return screen_id


def _normalise_entry(entry: Any) -> ScheduleEntry:
    """Return a canonical representation of a sequence entry."""

    if isinstance(entry, str):
        return _validate_screen_id(entry)

    if isinstance(entry, dict):
        # Allow wrapper objects such as {"screen": "foo"}
        if set(entry.keys()) == {"screen"}:
            return _normalise_entry(entry["screen"])

        if "cycle" in entry:
            children = entry["cycle"]
            if not isinstance(children, list) or not children:
                raise ConfigValidationError("cycle must be a non-empty list")
            normalised_children = [_normalise_entry(child) for child in children]
            return {"cycle": normalised_children}

        if "variants" in entry:
            options = entry["variants"]
            if not isinstance(options, list) or not options:
                raise ConfigValidationError("variants must be a non-empty list")
            normalised_options = []
            for option in options:
                if not isinstance(option, str):
                    raise ConfigValidationError("variants entries must be screen ids")
                normalised_options.append(_validate_screen_id(option))
            return {"variants": normalised_options}

        if "every" in entry:
            freq_raw = entry.get("every")
            try:
                freq = int(freq_raw)
            except (TypeError, ValueError) as exc:
                raise ConfigValidationError("every rule requires an integer frequency") from exc
            if freq <= 0:
                raise ConfigValidationError("every frequency must be greater than zero")
            child_raw = entry.get("screen") or entry.get("item")
            if child_raw is None:
                raise ConfigValidationError("every rule requires a child screen")
            child = _normalise_entry(child_raw)
            return {"every": freq, "screen": child}

    raise ConfigValidationError(f"Unsupported schedule entry: {entry!r}")


def _normalise_sequence(sequence: Any) -> List[ScheduleEntry]:
    if not isinstance(sequence, list) or not sequence:
        raise ConfigValidationError("sequence must be a non-empty list")
    return [_normalise_entry(item) for item in sequence]


def _normalise_config(data: Any) -> Tuple[Dict[str, Any], bool]:
    """Return a validated configuration and whether a migration occurred."""

    migrated = False

    if isinstance(data, dict) and "sequence" in data:
        sequence_raw = data["sequence"]
    elif isinstance(data, dict) and "screens" in data:
        migrated = True
        sequence_raw: List[ScheduleEntry] = []
        screens = data.get("screens") or {}
        if isinstance(screens, dict):
            for screen_id, raw_value in screens.items():
                try:
                    _validate_screen_id(screen_id)
                except ConfigValidationError:
                    continue
                try:
                    freq = int(raw_value)
                except (TypeError, ValueError):
                    freq = 1 if raw_value else 0
                if freq <= 0:
                    continue
                if freq == 1:
                    sequence_raw.append(screen_id)
                else:
                    sequence_raw.append({"every": freq, "screen": screen_id})
        if not sequence_raw:
            sequence_raw = list(DEFAULT_SEQUENCE)
    else:
        migrated = True
        sequence_raw = list(DEFAULT_SEQUENCE)

    sequence = _normalise_sequence(sequence_raw)

    config = {"sequence": sequence}

    # Validate via scheduler parser to ensure parity with the display service.
    build_scheduler(config)

    return config, migrated or config != data


def load_screen_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            raw_data = json.load(fh)
    except Exception:
        raw_data = {}

    try:
        config, migrated = _normalise_config(raw_data)
    except ConfigValidationError as exc:
        raise
    except ValueError as exc:  # build_scheduler errors propagate as ValueError
        raise ConfigValidationError(str(exc)) from exc

    # Persist migrations so the file always matches the canonical schema.
    if migrated:
        save_screen_config(config)

    return config


def save_screen_config(config: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, sort_keys=True)
        fh.write("\n")


@app.route("/")
def index():
    try:
        config = load_screen_config()
    except ConfigValidationError as exc:
        app.logger.warning("Falling back to default config: %s", exc)
        config = {"sequence": list(DEFAULT_SEQUENCE)}
    return render_template(
        "admin.html",
        config_json=json.dumps(config),
        known_screens=json.dumps(sorted(SCREEN_IDS)),
    )


@app.route("/api/config")
def api_config():
    try:
        config = load_screen_config()
    except ConfigValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    return jsonify({"status": "ok", "config": config})


@app.route("/save_config", methods=["POST"])
def save_config():
    data = request.get_json() or {}

    try:
        config, _ = _normalise_config(data)
    except ConfigValidationError as exc:
        return jsonify(status="error", message=str(exc)), 400
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 400

    try:
        save_screen_config(config)
    except Exception as exc:
        return jsonify(status="error", message=str(exc)), 500

    return jsonify(status="success", config=config)


@app.route("/api/screenshots/<screen_id>")
def screenshots_for_screen(screen_id):
    safe = screen_id.replace(" ", "_")
    try:
        files = sorted(os.listdir(SCREENSHOT_DIR))
        matches = [f for f in files if f.startswith(safe + "_")]
    except Exception:
        matches = []
    return jsonify(matches)


def _catalog_thumbnails() -> Dict[str, str]:
    """Return a mapping of screen id → thumbnail path if available."""

    thumbnails: Dict[str, str] = {}
    try:
        files = sorted(os.listdir(SCREENSHOT_DIR))
    except Exception:
        files = []

    for screen_id in SCREEN_IDS:
        safe = screen_id.replace(" ", "_")
        prefix = safe + "_"
        match = next((f for f in files if f.startswith(prefix)), None)
        if match:
            thumbnails[screen_id] = f"/screenshots/{match}"
    return thumbnails


@app.route("/api/catalog")
def api_catalog():
    thumbs = _catalog_thumbnails()
    payload = [
        {
            "id": screen_id,
            "thumbnail": thumbs.get(screen_id),
        }
        for screen_id in SCREEN_IDS
    ]
    return jsonify({"status": "ok", "screens": payload})


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
