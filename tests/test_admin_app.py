import json
from pathlib import Path

import pytest

import admin


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "screens_config.json"
    # Seed with a minimal valid config to avoid bootstrap warnings.
    config_path.write_text(json.dumps({"sequence": ["date", "time"]}))

    monkeypatch.setattr(admin, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(admin, "SCREENSHOT_DIR", str(tmp_path / "shots"))

    admin.app.config.update(TESTING=True)
    with admin.app.test_client() as client:
        yield client


def read_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def test_api_config_migrates_legacy_format(app_client):
    legacy = {"screens": {"date": 1, "time": 2, "unknown": 3, "travel": 0}}
    Path(admin.CONFIG_PATH).write_text(json.dumps(legacy))

    resp = app_client.get("/api/config")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    sequence = payload["config"]["sequence"]

    assert sequence[0] == "date"
    assert sequence[1] == {"every": 2, "screen": "time"}
    # Unknown screen ids should be dropped silently.
    assert all(item != "unknown" for item in sequence)

    # File should have been rewritten to canonical structure.
    persisted = read_config(admin.CONFIG_PATH)
    assert persisted == payload["config"]


def test_save_config_persists_cycles_and_every_rules(app_client):
    payload = {
        "sequence": [
            "date",
            {"cycle": ["time", "inside"]},
            {"every": 3, "screen": "time"},
        ]
    }

    resp = app_client.post("/save_config", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["config"]["sequence"][1] == {"cycle": ["time", "inside"]}

    stored = read_config(admin.CONFIG_PATH)
    assert stored == data["config"]


def test_save_config_rejects_unknown_screen(app_client):
    resp = app_client.post("/save_config", json={"sequence": ["not-a-screen"]})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Unknown screen" in data["message"]


def test_reorder_and_edit_cycle_triggers_scheduler(app_client, monkeypatch):
    initial = {"sequence": ["date", {"cycle": ["time", "inside"]}, "time"]}
    Path(admin.CONFIG_PATH).write_text(json.dumps(initial))

    calls = []

    def fake_build_scheduler(config):
        calls.append(config)
        class Dummy:
            requested_ids = set()
            node_count = len(config["sequence"])
        return Dummy()

    monkeypatch.setattr(admin, "build_scheduler", fake_build_scheduler)

    new_order = {
        "sequence": [
            {"cycle": ["inside", "date"]},
            {"every": 2, "screen": "time"},
        ]
    }

    resp = app_client.post("/save_config", json=new_order)
    assert resp.status_code == 200
    assert calls, "Scheduler was not invoked"
    assert calls[-1]["sequence"][0] == {"cycle": ["inside", "date"]}
    assert calls[-1]["sequence"][1] == {"every": 2, "screen": "time"}

    persisted = read_config(admin.CONFIG_PATH)
    assert persisted == calls[-1]

    refreshed = app_client.get("/api/config").get_json()["config"]["sequence"]
    assert refreshed[0] == {"cycle": ["inside", "date"]}
