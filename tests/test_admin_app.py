import json
from pathlib import Path

import pytest

import admin
from config_store import ConfigStore


def make_v2_config():
    return {
        "version": 2,
        "catalog": {"presets": {}},
        "metadata": {},
        "playlists": {
            "main": {
                "label": "Main",
                "steps": [
                    {"screen": "date"},
                    {"screen": "time"},
                ],
            }
        },
        "sequence": [{"playlist": "main"}],
    }


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "screens_config.json"
    config_path.write_text(json.dumps(make_v2_config()))

    monkeypatch.setattr(admin, "CONFIG_PATH", str(config_path))
    admin.store = ConfigStore(str(config_path))

    admin.app.config.update(TESTING=True)
    with admin.app.test_client() as client:
        yield client


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_api_catalog_returns_v2_schema(app_client, tmp_path):
    resp = app_client.get("/api/catalog")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert payload["config"]["version"] == 2
    assert "playlists" in payload["config"]
    assert payload["config"]["sequence"]


def test_save_config_accepts_playlists(app_client):
    payload = {
        "config": {
            "version": 2,
            "catalog": {"presets": {}},
            "metadata": {},
            "playlists": {
                "weather": {"steps": [{"screen": "date"}, {"screen": "time"}]},
                "main": {
                    "steps": [
                        {"playlist": "weather"},
                        {"rule": {"type": "variants", "options": ["inside", "travel"]}},
                    ]
                },
            },
            "sequence": [{"playlist": "main"}],
        }
    }

    resp = app_client.post("/save_config", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["config"]["playlists"]["weather"]["steps"][0] == {"screen": "date"}


def test_save_config_rejects_invalid_playlist_reference(app_client):
    payload = {
        "config": {
            "version": 2,
            "catalog": {"presets": {}},
            "metadata": {},
            "playlists": {
                "main": {"steps": [{"playlist": "missing"}]}
            },
            "sequence": [{"playlist": "main"}],
        }
    }

    resp = app_client.post("/save_config", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"


def test_preview_endpoint_uses_scheduler(app_client):
    payload = {
        "config": make_v2_config(),
        "count": 5,
    }
    resp = app_client.post("/preview", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert len(data["preview"]) <= 5


def test_rollback_endpoint_restores_previous_version(app_client, tmp_path):
    first_payload = {
        "config": {
            "version": 2,
            "catalog": {"presets": {}},
            "metadata": {},
            "playlists": {
                "main": {"steps": [{"screen": "date"}]}
            },
            "sequence": [{"playlist": "main"}],
        }
    }
    second_payload = {
        "config": {
            "version": 2,
            "catalog": {"presets": {}},
            "metadata": {},
            "playlists": {
                "main": {"steps": [{"screen": "time"}]}
            },
            "sequence": [{"playlist": "main"}],
        }
    }

    resp1 = app_client.post("/save_config", json=first_payload)
    assert resp1.status_code == 200
    version1 = resp1.get_json()["version_id"]

    resp2 = app_client.post("/save_config", json=second_payload)
    assert resp2.status_code == 200

    rollback_resp = app_client.post("/config/rollback", json={"version_id": version1})
    assert rollback_resp.status_code == 200
    data = rollback_resp.get_json()
    assert data["status"] == "success"
    assert data["config"]["playlists"]["main"]["steps"][0] == {"screen": "date"}


def test_migration_of_legacy_sequence(app_client, tmp_path):
    legacy = {"sequence": ["date", "time"]}
    Path(admin.CONFIG_PATH).write_text(json.dumps(legacy))

    resp = app_client.get("/api/catalog")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["config"]["version"] == 2
    assert payload["migrated"] is True
    persisted = read_json(Path(admin.CONFIG_PATH))
    assert persisted["version"] == 2
    assert persisted["playlists"]["main"]["steps"]
