"""Simple frequency-based screen scheduler."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from screens_catalog import SCREEN_IDS
from screens.registry import ScreenDefinition


KNOWN_SCREENS: Set[str] = set(SCREEN_IDS)


@dataclass
class _ScheduleEntry:
    screen_id: str
    frequency: int
    cooldown: int = 0


class ScreenScheduler:
    """Iterator that yields the next available screen based on frequencies."""

    def __init__(self, entries: Sequence[_ScheduleEntry]):
        self._entries: List[_ScheduleEntry] = list(entries)
        self._cursor: int = 0
        self._requested: Set[str] = {entry.screen_id for entry in self._entries}

    @property
    def node_count(self) -> int:
        return len(self._entries)

    @property
    def requested_ids(self) -> Set[str]:
        return set(self._requested)

    def next_available(self, registry: Dict[str, ScreenDefinition]) -> Optional[ScreenDefinition]:
        if not self._entries:
            return None

        for _ in range(len(self._entries)):
            entry = self._entries[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._entries)

            if entry.cooldown > 0:
                entry.cooldown -= 1
                if entry.cooldown > 0:
                    continue

            # A frequency of ``n`` means the screen should appear once every
            # ``n`` iterations of the playlist.  The previous implementation
            # used the raw frequency value as the cooldown which effectively
            # produced a cycle of ``n + 1`` iterations, making the screens
            # appear less often than configured (e.g. a frequency of 3 would
            # yield one appearance every 4 loops).  By resetting the cooldown
            # to the raw frequency and letting the current iteration proceed
            # when it hits zero we align the output with the configured
            # interval while keeping ``0`` as an "always show" value.
            entry.cooldown = max(entry.frequency, 0)
            definition = registry.get(entry.screen_id)
            if definition and definition.available:
                return definition

        return None


def load_schedule_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Schedule configuration must be a JSON object")
    return data


def build_scheduler(config: Dict[str, Any]) -> ScreenScheduler:
    if not isinstance(config, dict):
        raise ValueError("Schedule configuration must be a JSON object")

    screens = config.get("screens")
    if not isinstance(screens, dict) or not screens:
        raise ValueError("Configuration must provide a non-empty 'screens' mapping")

    entries: List[_ScheduleEntry] = []
    for screen_id, freq in screens.items():
        if not isinstance(screen_id, str):
            raise ValueError("Screen identifiers must be strings")
        if screen_id not in KNOWN_SCREENS:
            raise ValueError(f"Unknown screen id '{screen_id}'")
        try:
            frequency = int(freq)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Frequency for '{screen_id}' must be an integer") from exc
        if frequency < 0:
            raise ValueError(f"Frequency for '{screen_id}' cannot be negative")
        entries.append(_ScheduleEntry(screen_id, frequency))

    return ScreenScheduler(entries)
