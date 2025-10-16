import pytest

from schedule import build_scheduler
from screens.registry import ScreenDefinition


def make_registry(availability):
    return {
        sid: ScreenDefinition(id=sid, render=lambda sid=sid: sid, available=available)
        for sid, available in availability.items()
    }


def test_build_scheduler_from_config():
    config = {
        "screens": {
            "date": 0,
            "travel": 2,
            "inside": 1,
        }
    }
    scheduler = build_scheduler(config)
    assert scheduler.node_count == 3
    assert scheduler.requested_ids == {"date", "travel", "inside"}


def test_build_scheduler_rejects_unknown_screen():
    config = {"screens": {"missing": 1}}
    with pytest.raises(ValueError):
        build_scheduler(config)


def test_scheduler_respects_frequency():
    config = {"screens": {"date": 0, "travel": 1}}
    scheduler = build_scheduler(config)
    registry = make_registry({"date": True, "travel": True})

    sequence = [scheduler.next_available(registry).id for _ in range(6)]
    assert sequence == ["date", "travel", "date", "date", "travel", "date"]


def test_scheduler_skips_unavailable_screen():
    config = {"screens": {"travel": 0}}
    scheduler = build_scheduler(config)
    registry = make_registry({"travel": False})
    assert scheduler.next_available(registry) is None


def test_invalid_configuration_shapes():
    with pytest.raises(ValueError):
        build_scheduler({})
    with pytest.raises(ValueError):
        build_scheduler({"screens": []})
    with pytest.raises(ValueError):
        build_scheduler({"screens": {"date": -1}})
    with pytest.raises(ValueError):
        build_scheduler({"screens": {"date": "oops"}})
