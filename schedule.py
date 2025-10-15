"""Schedule parsing and iteration helpers."""
from __future__ import annotations

import json
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
    sequence = config.get("sequence")
    nodes, requested = _parse_sequence(sequence)
    return ScreenScheduler(nodes, requested)


def _parse_sequence(sequence: Any) -> Tuple[List[ScheduleNode], Set[str]]:
    if not isinstance(sequence, list) or not sequence:
        raise ValueError("Schedule sequence must be a non-empty list")

    nodes: List[ScheduleNode] = []
    requested: Set[str] = set()
    for item in sequence:
        node, ids = _parse_item(item)
        nodes.append(node)
        requested.update(ids)
    return nodes, requested


def _parse_item(item: Any) -> Tuple[ScheduleNode, Set[str]]:
    if isinstance(item, str):
        _validate_screen_id(item)
        return ScreenNode(item), {item}

    if isinstance(item, dict):
        if "variants" in item:
            options = item["variants"]
            if not isinstance(options, list) or not options:
                raise ValueError("variants must be a non-empty list")
            parsed_options: List[str] = []
            for opt in options:
                if not isinstance(opt, str):
                    raise ValueError("variants entries must be screen IDs")
                _validate_screen_id(opt)
                parsed_options.append(opt)
            return VariantsNode(parsed_options), set(parsed_options)

        if "cycle" in item:
            children_raw = item["cycle"]
            if not isinstance(children_raw, list) or not children_raw:
                raise ValueError("cycle must be a non-empty list")
            children: List[ScheduleNode] = []
            requested: Set[str] = set()
            for child_raw in children_raw:
                child_node, child_ids = _parse_item(child_raw)
                children.append(child_node)
                requested.update(child_ids)
            return CycleNode(children), requested

        if "every" in item:
            freq_raw = item["every"]
            try:
                freq = int(freq_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("every rule requires an integer frequency") from exc
            if freq <= 0:
                raise ValueError("every frequency must be greater than zero")
            child_raw = item.get("screen") or item.get("item")
            if child_raw is None:
                raise ValueError("every rule requires a child screen")
            child_node, child_ids = _parse_item(child_raw)
            return EveryNode(child_node, freq), child_ids

        if "screen" in item:
            return _parse_item(item["screen"])

    raise ValueError(f"Unsupported schedule item: {item!r}")


def _validate_screen_id(screen_id: str) -> None:
    if screen_id not in KNOWN_SCREENS:
        raise ValueError(f"Unknown screen id '{screen_id}'")

