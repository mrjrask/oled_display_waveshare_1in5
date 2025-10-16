import json
import os
from pathlib import Path

import pytest

import admin


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "screens_config.json"
    config_path.write_text(json.dumps({"screens": {"date": 0, "travel": 2}}))

    screenshot_dir = tmp_path / "screenshots"
    screenshot_dir.mkdir()

    monkeypatch.setattr(admin, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(admin, "SCREENSHOT_DIR", str(screenshot_dir))
    admin.app.static_folder = str(screenshot_dir)

    admin.app.config.update(TESTING=True)
    with admin.app.test_client() as client:
        yield client, screenshot_dir, config_path


def test_index_lists_screens(app_client):
    client, screenshot_dir, _ = app_client

    folder = screenshot_dir / admin._sanitize_directory_name("date")
    folder.mkdir()
    (folder / "date_1.png").write_bytes(b"fake")

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "date" in body
    assert "travel" in body
    assert "Frequency" in body


def test_api_screens_reports_latest_file(app_client):
    client, screenshot_dir, _ = app_client

    folder = screenshot_dir / admin._sanitize_directory_name("date")
    folder.mkdir(exist_ok=True)
    first = folder / "date_1.png"
    second = folder / "date_2.png"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    os.utime(first, (1, 1))
    os.utime(second, (2, 2))

    resp = client.get("/api/screens")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"

    screens = {entry["id"]: entry for entry in payload["screens"]}
    assert screens["date"]["last_screenshot"].endswith("date_2.png")
    assert screens["travel"]["last_screenshot"] is None


def test_api_config_returns_current_config(app_client):
    client, _, config_path = app_client
    resp = client.get("/api/config")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"
    assert payload["config"]["screens"]["travel"] == 2
    assert json.loads(Path(config_path).read_text())["screens"]["date"] == 0
