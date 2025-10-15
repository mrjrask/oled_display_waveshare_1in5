import pytest

from schedule import build_scheduler
from screens.registry import ScreenDefinition


def make_registry(available_map):
    return {
        sid: ScreenDefinition(id=sid, render=lambda sid=sid: sid, available=available)
        for sid, available in available_map.items()
    }


def test_build_scheduler_valid_sequence():
    config = {
        "sequence": [
            "date",
            {"cycle": ["time", "inside"]},
            {"variants": ["travel", "inside"]},
        ]
    }
    scheduler = build_scheduler(config)
    assert scheduler.node_count == 3
    assert scheduler.requested_ids == {"date", "time", "inside", "travel"}


def test_build_scheduler_unknown_screen():
    config = {"sequence": ["not-a-real-screen"]}
    with pytest.raises(ValueError):
        build_scheduler(config)


def test_cycle_two_overview_one_standings():
    config = {
        "sequence": [
            {"cycle": ["NFL Overview AFC", "NFL Overview AFC", "NFL Standings AFC"]}
        ]
    }
    scheduler = build_scheduler(config)
    registry = make_registry(
        {
            "NFL Overview AFC": True,
            "NFL Standings AFC": True,
        }
    )

    outputs = [scheduler.next_available(registry).id for _ in range(6)]
    assert outputs == [
        "NFL Overview AFC",
        "NFL Overview AFC",
        "NFL Standings AFC",
        "NFL Overview AFC",
        "NFL Overview AFC",
        "NFL Standings AFC",
    ]


def test_variants_skip_missing():
    config = {"sequence": [{"variants": ["travel", "inside"]}]}
    scheduler = build_scheduler(config)
    registry = make_registry({"travel": False, "inside": True})

    entry = scheduler.next_available(registry)
    assert entry.id == "inside"


def test_returns_none_when_all_screens_unavailable():
    config = {"sequence": ["travel"]}
    scheduler = build_scheduler(config)
    registry = make_registry({"travel": False})

    assert scheduler.next_available(registry) is None
