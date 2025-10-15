"""Schedule parsing and iteration helpers.

This module now supports both the historical v1 "sequence" array as well as the
new playlist-centric configuration schema (v2).  The v2 schema allows
named playlists, nested playlists, reusable rule descriptors, and
time/day-based conditions that can wrap any node.  The parser is designed to be
agnostic to the source of the configuration (whether loaded directly from
``screens_config.json`` or produced via the migration CLI).
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from screens_catalog import SCREEN_IDS
from screens.registry import ScreenDefinition


KNOWN_SCREENS: Set[str] = set(SCREEN_IDS)


class ScheduleNode:
    """Abstract base class for schedule nodes."""

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        raise NotImplementedError


class ScreenNode(ScheduleNode):
    def __init__(self, screen_id: str) -> None:
        self.screen_id = screen_id

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        return self.screen_id


class EveryNode(ScheduleNode):
    def __init__(self, child: ScheduleNode, frequency: int) -> None:
        self.child = child
        self.frequency = max(1, frequency)
        self._tick = 0

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        result: Optional[str] = None
        if self._tick == 0:
            result = self.child.next(registry)
        self._tick = (self._tick + 1) % self.frequency
        return result


class CycleNode(ScheduleNode):
    def __init__(self, children: Sequence[ScheduleNode]) -> None:
        self.children = list(children)
        self._index = 0

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        if not self.children:
            return None
        node = self.children[self._index]
        self._index = (self._index + 1) % len(self.children)
        return node.next(registry)


class VariantsNode(ScheduleNode):
    def __init__(self, options: Sequence[str]) -> None:
        self.options = list(options)

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        for option in self.options:
            entry = registry.get(option)
            if entry and entry.available:
                return option
        return None


@dataclass(frozen=True)
class ConditionSpec:
    """Represents optional time/day constraints for a playlist node."""

    days_of_week: Optional[Set[int]] = None
    time_ranges: Optional[Tuple[Tuple[int, int], ...]] = None

    @staticmethod
    def from_dict(data: Any) -> "ConditionSpec":
        if not data or not isinstance(data, dict):
            return ConditionSpec()

        days_raw = data.get("day_of_week") or data.get("days_of_week")
        days: Optional[Set[int]] = None
        if days_raw is not None:
            if isinstance(days_raw, str):
                days_raw = [days_raw]
            if not isinstance(days_raw, (list, tuple)):
                raise ValueError("days_of_week must be a list of weekday names")
            days = set()
            for entry in days_raw:
                if not isinstance(entry, str):
                    raise ValueError("days_of_week entries must be strings")
                normalised = entry.strip().lower()
                if not normalised:
                    continue
                mapping = {
                    "mon": 0,
                    "monday": 0,
                    "tue": 1,
                    "tues": 1,
                    "tuesday": 1,
                    "wed": 2,
                    "wednesday": 2,
                    "thu": 3,
                    "thurs": 3,
                    "thursday": 3,
                    "fri": 4,
                    "friday": 4,
                    "sat": 5,
                    "saturday": 5,
                    "sun": 6,
                    "sunday": 6,
                }
                if normalised not in mapping:
                    raise ValueError(f"Unknown day-of-week '{entry}'")
                days.add(mapping[normalised])
            if not days:
                days = None

        ranges_raw = data.get("time_of_day") or data.get("time_ranges")
        ranges: Optional[List[Tuple[int, int]]] = None
        if ranges_raw is not None:
            if isinstance(ranges_raw, dict):
                ranges_raw = [ranges_raw]
            if not isinstance(ranges_raw, (list, tuple)):
                raise ValueError("time_of_day must be a list of ranges")
            ranges = []
            for rng in ranges_raw:
                if not isinstance(rng, dict):
                    raise ValueError("time_of_day entries must be objects")
                start_raw = rng.get("start")
                end_raw = rng.get("end")
                if not isinstance(start_raw, str) or not isinstance(end_raw, str):
                    raise ValueError("time_of_day ranges require start and end times")
                start_minutes = _parse_hhmm(start_raw)
                end_minutes = _parse_hhmm(end_raw)
                ranges.append((start_minutes, end_minutes))
            if not ranges:
                ranges = None

        if days is None and ranges is None:
            return ConditionSpec()
        return ConditionSpec(days, tuple(ranges) if ranges else None)

    def allows_datetime(self, dt: Optional[_dt.datetime] = None) -> bool:
        if dt is None:
            dt = _dt.datetime.now()
        if self.days_of_week is not None and dt.weekday() not in self.days_of_week:
            return False
        if self.time_ranges is None:
            return True
        minutes = dt.hour * 60 + dt.minute
        for start, end in self.time_ranges:
            if start == end:
                continue
            if start < end:
                if start <= minutes < end:
                    return True
            else:
                # Overnight range such as 22:00-02:00.
                if minutes >= start or minutes < end:
                    return True
        return False


class ConditionNode(ScheduleNode):
    """Decorates a node with time/day restrictions."""

    def __init__(self, child: ScheduleNode, spec: ConditionSpec) -> None:
        self.child = child
        self.spec = spec

    def next(self, registry: Dict[str, ScreenDefinition]) -> Optional[str]:
        if not self.spec.allows_datetime():
            return None
        return self.child.next(registry)


class ScreenScheduler:
    """Iterator that yields the next available screen from the schedule."""

    def __init__(self, nodes: Sequence[ScheduleNode], requested_ids: Iterable[str]):
        self._nodes = list(nodes)
        self._requested = set(requested_ids)
        self._index = 0

    @property
    def requested_ids(self) -> Set[str]:
        return set(self._requested)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def _step(self, registry: Dict[str, ScreenDefinition]) -> Optional[ScreenDefinition]:
        if not self._nodes:
            return None
        node = self._nodes[self._index]
        self._index = (self._index + 1) % len(self._nodes)
        screen_id = node.next(registry)
        if not screen_id:
            return None
        entry = registry.get(screen_id)
        if entry and entry.available:
            return entry
        return None

    def next_available(self, registry: Dict[str, ScreenDefinition]) -> Optional[ScreenDefinition]:
        if not self._nodes:
            return None
        for _ in range(len(self._nodes)):
            entry = self._step(registry)
            if entry is not None:
                return entry
        return None


def load_schedule_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Schedule configuration must be a JSON object")
    return data


def build_scheduler(config: Dict[str, Any]) -> ScreenScheduler:
    parser = _ScheduleParser(config)
    nodes, requested = parser.parse()
    return ScreenScheduler(nodes, requested)


class _ScheduleParser:
    """Parse either the legacy sequence list or the playlist schema."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        playlists = self.config.get("playlists")
        self.playlists: Dict[str, Any] = playlists if isinstance(playlists, dict) else {}

    # ------------------------------------------------------------------
    # Public API
    def parse(self) -> Tuple[List[ScheduleNode], Set[str]]:
        if self._is_playlist_schema():
            return self._parse_playlist_schema()
        return self._parse_legacy_sequence()

    # ------------------------------------------------------------------
    # Legacy parsing (v1 schema)
    def _parse_legacy_sequence(self) -> Tuple[List[ScheduleNode], Set[str]]:
        sequence = self.config.get("sequence")
        if not isinstance(sequence, list) or not sequence:
            raise ValueError("Schedule sequence must be a non-empty list")
        nodes: List[ScheduleNode] = []
        requested: Set[str] = set()
        for item in sequence:
            child_nodes, ids = self._parse_step(item, ancestry=())
            nodes.extend(child_nodes)
            requested.update(ids)
        return nodes, requested

    # ------------------------------------------------------------------
    # Playlist schema parsing
    def _is_playlist_schema(self) -> bool:
        if self.config.get("version") == 2:
            return True
        if self.playlists:
            return True
        sequence = self.config.get("sequence")
        if isinstance(sequence, list):
            for item in sequence:
                if isinstance(item, dict) and ("playlist" in item or "steps" in item):
                    return True
        return False

    def _parse_playlist_schema(self) -> Tuple[List[ScheduleNode], Set[str]]:
        sequence = self.config.get("sequence")
        if not isinstance(sequence, list) or not sequence:
            raise ValueError("Playlist sequence must be a non-empty list")

        nodes: List[ScheduleNode] = []
        requested: Set[str] = set()
        for item in sequence:
            child_nodes, ids = self._parse_step(item, ancestry=())
            nodes.extend(child_nodes)
            requested.update(ids)
        return nodes, requested

    # ------------------------------------------------------------------
    # Step parsing
    def _parse_step(self, step: Any, ancestry: Sequence[str]) -> Tuple[List[ScheduleNode], Set[str]]:
        conditions_raw = None
        if isinstance(step, dict) and "conditions" in step:
            conditions_raw = step.get("conditions")

        base_nodes: List[ScheduleNode]
        requested: Set[str]

        if isinstance(step, str):
            base_nodes, requested = self._parse_screen(step)
        elif isinstance(step, dict):
            base_nodes, requested = self._parse_step_dict(step, ancestry)
        else:
            raise ValueError(f"Unsupported schedule entry: {step!r}")

        if conditions_raw:
            spec = ConditionSpec.from_dict(conditions_raw)
            base_nodes = [ConditionNode(node, spec) for node in base_nodes]
        return base_nodes, requested

    def _parse_step_dict(self, data: Dict[str, Any], ancestry: Sequence[str]) -> Tuple[List[ScheduleNode], Set[str]]:
        if "screen" in data and len(data) == 1:
            return self._parse_step(data["screen"], ancestry)

        if "playlist" in data:
            playlist_id = data["playlist"]
            if not isinstance(playlist_id, str):
                raise ValueError("playlist reference must be a string id")
            return self._parse_playlist_ref(playlist_id, ancestry)

        if "rule" in data:
            return self._parse_rule(data["rule"], ancestry)

        if "steps" in data:
            steps = data["steps"]
            if not isinstance(steps, list) or not steps:
                raise ValueError("Inline playlist steps must be a non-empty list")
            combined_nodes: List[ScheduleNode] = []
            requested: Set[str] = set()
            for step in steps:
                child_nodes, ids = self._parse_step(step, ancestry)
                combined_nodes.extend(child_nodes)
                requested.update(ids)
            return combined_nodes, requested

        if "variants" in data or "cycle" in data or "every" in data:
            return self._parse_rule(data, ancestry)

        raise ValueError(f"Unsupported schedule entry: {data!r}")

    def _parse_screen(self, screen_id: str) -> Tuple[List[ScheduleNode], Set[str]]:
        if not isinstance(screen_id, str):
            raise ValueError("screen id must be a string")
        _validate_screen_id(screen_id)
        return [ScreenNode(screen_id)], {screen_id}

    def _parse_playlist_ref(self, playlist_id: str, ancestry: Sequence[str]) -> Tuple[List[ScheduleNode], Set[str]]:
        if playlist_id in ancestry:
            raise ValueError(f"Circular playlist reference detected: {' -> '.join(ancestry + (playlist_id,))}")
        playlist_def = self.playlists.get(playlist_id)
        if not isinstance(playlist_def, dict):
            raise ValueError(f"Unknown playlist '{playlist_id}'")
        steps = playlist_def.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"Playlist '{playlist_id}' must define a non-empty steps list")
        combined_nodes: List[ScheduleNode] = []
        requested: Set[str] = set()
        for step in steps:
            child_nodes, ids = self._parse_step(step, ancestry + (playlist_id,))
            combined_nodes.extend(child_nodes)
            requested.update(ids)

        conditions_spec = ConditionSpec.from_dict(playlist_def.get("conditions"))
        if conditions_spec.days_of_week or conditions_spec.time_ranges:
            combined_nodes = [ConditionNode(node, conditions_spec) for node in combined_nodes]
        return combined_nodes, requested

    def _parse_rule(self, rule_data: Any, ancestry: Sequence[str]) -> Tuple[List[ScheduleNode], Set[str]]:
        if not isinstance(rule_data, dict):
            raise ValueError("rule descriptor must be an object")
        rule_type = rule_data.get("type")

        if rule_type is None:
            # Support legacy inline descriptors such as {"cycle": [...]}
            if "cycle" in rule_data:
                rule_type = "cycle"
            elif "variants" in rule_data:
                rule_type = "variants"
            elif "every" in rule_data:
                rule_type = "every"

        if rule_type == "variants":
            options = rule_data.get("options") or rule_data.get("variants")
            if not isinstance(options, (list, tuple)) or not options:
                raise ValueError("variants rule requires a non-empty list of options")
            parsed: List[str] = []
            for option in options:
                if not isinstance(option, str):
                    raise ValueError("variants options must be screen ids")
                _validate_screen_id(option)
                parsed.append(option)
            return [VariantsNode(parsed)], set(parsed)

        if rule_type == "cycle":
            items = rule_data.get("items") or rule_data.get("cycle")
            if not isinstance(items, (list, tuple)) or not items:
                raise ValueError("cycle rule requires a non-empty list of items")
            children: List[ScheduleNode] = []
            requested: Set[str] = set()
            for item in items:
                child_nodes, child_ids = self._parse_step(item, ancestry)
                if len(child_nodes) != 1:
                    raise ValueError("cycle rule items must resolve to a single schedule node")
                children.append(child_nodes[0])
                requested.update(child_ids)
            return [CycleNode(children)], requested

        if rule_type == "every":
            frequency_raw = rule_data.get("frequency") or rule_data.get("every")
            try:
                frequency = int(frequency_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("every rule requires an integer frequency") from exc
            if frequency <= 0:
                raise ValueError("every frequency must be greater than zero")
            item = rule_data.get("item") or rule_data.get("screen")
            if item is None:
                raise ValueError("every rule requires an item")
            child_nodes, child_ids = self._parse_step(item, ancestry)
            if len(child_nodes) != 1:
                raise ValueError("every rule item must resolve to a single node")
            return [EveryNode(child_nodes[0], frequency)], child_ids

        raise ValueError(f"Unsupported rule descriptor: {rule_data!r}")


def _parse_hhmm(value: str) -> int:
    if not isinstance(value, str) or len(value) < 4:
        raise ValueError("time values must be HH:MM")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("time values must be in HH:MM format")
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise ValueError("time values must be numeric HH:MM") from exc
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError("time values must be within 00:00-23:59")
    return hours * 60 + minutes


def _validate_screen_id(screen_id: str) -> None:
    if screen_id not in KNOWN_SCREENS:
        raise ValueError(f"Unknown screen id '{screen_id}'")

