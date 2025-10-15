import json

import pytest

from config_store import ConfigStore


def make_config(value: str) -> dict:
    return {
        "version": 2,
        "catalog": {"presets": {}},
        "metadata": {"value": value},
        "playlists": {"main": {"steps": [{"screen": "date"}]}},
        "sequence": [{"playlist": "main"}],
    }


def test_config_store_versioning_and_pruning(tmp_path):
    config_path = tmp_path / "screens_config.json"
    store = ConfigStore(str(config_path), retention=2)

    v1 = store.save(make_config("one"), actor="tester1")
    v2 = store.save(make_config("two"), actor="tester2")
    v3 = store.save(make_config("three"), actor="tester3")

    versions = store.list_versions()
    assert versions[0]["id"] == v3
    assert len(versions) == 2
    assert store.latest_version_id() == v3

    archive_dir = config_path.parent / "config_versions"
    archived_files = sorted(archive_dir.glob("*.json"))
    assert len(archived_files) == 2

    with pytest.raises(KeyError):
        store.load_version(v1)


def test_config_store_rollback(tmp_path):
    config_path = tmp_path / "config.json"
    store = ConfigStore(str(config_path))

    first = make_config("initial")
    store.save(first, actor="tester")
    second = make_config("second")
    version_id = store.save(second, actor="tester")

    rolled = store.rollback(version_id, actor="tester")
    assert rolled["metadata"]["value"] == "second"
    persisted = json.loads(config_path.read_text())
    assert persisted["metadata"]["value"] == "second"
