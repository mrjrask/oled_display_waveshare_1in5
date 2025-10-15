#!/usr/bin/env python3
"""Admin service providing playlist-aware configuration tooling."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from flask import Flask, jsonify, render_template, request

from config_store import ConfigStore
from schedule import build_scheduler
from schedule_migrations import MigrationError, migrate_config
from screens_catalog import SCREEN_IDS


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "screens_config.json")

app = Flask(__name__, static_folder="screenshots", static_url_path="/screenshots")

store = ConfigStore(CONFIG_PATH)


class ConfigValidationError(ValueError):
    """Raised when a configuration payload fails validation."""


def _default_config() -> Dict[str, Any]:
    return {
        "version": 2,
        "catalog": {"presets": {}},
        "metadata": {"created": "auto"},
        "playlists": {
            "main": {
                "label": "Default rotation",
                "steps": [
                    {"screen": "date"},
                    {"screen": "time"},
                ],
            }
        },
        "sequence": [{"playlist": "main"}],
    }


def _load_active_config() -> Tuple[Dict[str, Any], List[str], bool]:
    raw = store.load()
    migrated = False
    if not raw:
        config = _default_config()
        store.save(config, actor="system", summary="Seed default configuration")
        raw = config
        migrated = True

    try:
        result = migrate_config(raw, source=CONFIG_PATH)
    except MigrationError as exc:  # pragma: no cover - indicates corrupt file
        raise ConfigValidationError(str(exc)) from exc

    config = result.config
    if result.migrated:
        store.save(
            config,
            actor="system",
            summary="Automated migration to schema v2",
            metadata={"reason": "auto_migration"},
        )
        migrated = True

    errors = _validate_config(config)
    return config, errors, migrated


def _validate_config(config: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    try:
        build_scheduler(config)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def _normalise_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigValidationError("Configuration payload must be a JSON object")

    config: Dict[str, Any] = {}
    config["version"] = payload.get("version", 2)
    if config["version"] != 2:
        raise ConfigValidationError("Configuration must declare version 2")

    catalog = payload.get("catalog")
    config["catalog"] = catalog if isinstance(catalog, dict) else {"presets": {}}

    metadata = payload.get("metadata")
    config["metadata"] = metadata if isinstance(metadata, dict) else {}

    playlists = payload.get("playlists") or {}
    if not isinstance(playlists, dict):
        raise ConfigValidationError("playlists must be an object")
    config["playlists"] = playlists

    sequence = payload.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        raise ConfigValidationError("sequence must be a non-empty list")
    config["sequence"] = sequence

    return config


def _playlist_ui_enabled(config: Dict[str, Any]) -> bool:
    metadata = config.get("metadata")
    if isinstance(metadata, dict):
        ui_meta = metadata.get("ui")
        if isinstance(ui_meta, dict) and ui_meta.get("playlist_admin_enabled") is False:
            return False
    return True


def _catalog_payload() -> Dict[str, Any]:
    config, errors, migrated = _load_active_config()
    versions = store.list_versions(limit=20)
    return {
        "config": config,
        "screens": sorted(SCREEN_IDS),
        "validation": errors,
        "migrated": migrated,
        "versions": versions,
        "latest_version_id": store.latest_version_id(),
    }


@app.route("/")
def index() -> str:
    payload = _catalog_payload()
    use_playlist_ui = _playlist_ui_enabled(payload["config"]) and request.args.get("legacy") != "1"
    template = "admin.html" if use_playlist_ui else "admin_legacy.html"
    return render_template(
        template,
        bootstrap=json.dumps(payload),
        config_json=json.dumps(payload["config"], indent=2),
    )


@app.route("/api/catalog")
def api_catalog():
    try:
        payload = _catalog_payload()
    except ConfigValidationError as exc:
        return jsonify(status="error", message=str(exc)), 500
    return jsonify(status="ok", **payload)


@app.route("/api/config")
def api_config():
    return api_catalog()


@app.route("/save_config", methods=["POST"])
def save_config():
    incoming = request.get_json() or {}
    actor = incoming.get("actor") or request.headers.get("X-User", "admin")
    summary = incoming.get("summary")
    payload = incoming.get("config") if "config" in incoming else incoming

    try:
        config = _normalise_payload(payload)
        build_scheduler(config)
    except (ConfigValidationError, ValueError) as exc:
        return jsonify(status="error", message=str(exc)), 400

    version_id = store.save(config, actor=actor, summary=summary or None)
    response = _catalog_payload()
    response.update({"status": "success", "version_id": version_id})
    return jsonify(response)


@app.route("/preview", methods=["POST"])
def preview():
    data = request.get_json(silent=True) or {}
    count = data.get("count", 20)
    try:
        count = max(1, min(int(count), 200))
    except (TypeError, ValueError):
        return jsonify(status="error", message="count must be an integer"), 400

    payload = data.get("config")
    if payload is None:
        payload = _load_active_config()[0]

    try:
        config = _normalise_payload(payload)
        scheduler = build_scheduler(config)
    except (ConfigValidationError, ValueError) as exc:
        return jsonify(status="error", message=str(exc)), 400

    from screens.registry import ScreenDefinition

    registry = {
        sid: ScreenDefinition(id=sid, render=lambda sid=sid: sid, available=True)
        for sid in SCREEN_IDS
    }

    seen: List[str] = []
    for _ in range(count * 2):
        entry = scheduler.next_available(registry)
        if entry is None:
            continue
        seen.append(entry.id)
        if len(seen) >= count:
            break

    return jsonify(status="ok", preview=seen)


@app.route("/config/rollback", methods=["POST"])
def rollback_config():
    data = request.get_json() or {}
    version_id = data.get("version_id")
    actor = data.get("actor") or request.headers.get("X-User", "admin")
    if version_id is None:
        return jsonify(status="error", message="version_id is required"), 400
    try:
        version_id = int(version_id)
    except (TypeError, ValueError):
        return jsonify(status="error", message="version_id must be an integer"), 400

    try:
        store.rollback(version_id, actor=actor)
    except KeyError:
        return jsonify(status="error", message="Unknown version"), 404
    except Exception as exc:  # pragma: no cover - unexpected failure
        return jsonify(status="error", message=str(exc)), 500

    payload = _catalog_payload()
    payload.update({"status": "success", "rolled_back_to": version_id})
    return jsonify(payload)


if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=5001, debug=True)
