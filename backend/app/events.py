"""Unified event store.

Loads the cached working set (data/working_set/*.json) produced by the data
pipelines. Two channel encodings are normalized here:

- implicit time (VZCrash): {"sr_hz": 100, "t_start": 0.0, "v": [...]}
- explicit time (CISS):    {"t": [...], "v": [...]}

After loading, every channel exposes numpy arrays `t` and `v` plus unit/desc.
Labels are kept on the event but MUST NOT be exposed to the agent through
tools; they exist for the UI and the evaluation harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
WORKING_SET = ROOT / "data" / "working_set"


@dataclass
class Channel:
    name: str
    unit: str
    desc: str
    t: np.ndarray
    v: np.ndarray
    sr_hz: float | None = None  # set for regularly sampled channels

    @property
    def t_range(self) -> tuple[float, float]:
        return (float(self.t[0]), float(self.t[-1]))


@dataclass
class Event:
    event_id: str
    source: str  # "vzcrash" | "ciss"
    label: str | None
    channels: dict[str, Channel]
    meta: dict = field(default_factory=dict)
    narrative: str | None = None
    narrative_vehicle_ref: str | None = None
    edr_summary: dict | None = None
    time_zero: str = ""

    @property
    def t_min(self) -> float:
        return min(c.t_range[0] for c in self.channels.values())

    @property
    def t_max(self) -> float:
        return max(c.t_range[1] for c in self.channels.values())


def _load_channel(name: str, raw: dict) -> Channel:
    v = np.asarray(raw["v"], dtype=np.float64)
    if "t" in raw:
        t = np.asarray(raw["t"], dtype=np.float64)
        sr = None
    else:
        sr = float(raw["sr_hz"])
        t0 = float(raw.get("t_start", 0.0))
        t = t0 + np.arange(len(v)) / sr
    if len(t) != len(v):
        raise ValueError(f"channel {name}: len(t) {len(t)} != len(v) {len(v)}")
    return Channel(name=name, unit=raw["unit"], desc=raw.get("desc", ""), t=t, v=v, sr_hz=sr)


def load_event(path: Path) -> Event:
    d = json.loads(path.read_text(encoding="utf-8"))
    channels = {name: _load_channel(name, raw) for name, raw in d["channels"].items()}
    return Event(
        event_id=d["event_id"],
        source=d["source"],
        label=d.get("label"),
        channels=channels,
        meta=d.get("meta", {}),
        narrative=d.get("narrative"),
        narrative_vehicle_ref=d.get("narrative_vehicle_ref"),
        edr_summary=d.get("edr_summary"),
        time_zero=d.get("time_zero", ""),
    )


class EventStore:
    def __init__(self, directory: Path = WORKING_SET):
        self.directory = directory
        self._events: dict[str, Event] = {}
        self.reload()

    def reload(self) -> None:
        self._events = {}
        for path in sorted(self.directory.glob("*.json")):
            if path.name in ("ciss_join_report.json", "vzcrash_data_facts.json"):
                continue
            try:
                e = load_event(path)
            except (KeyError, ValueError) as exc:
                print(f"skipping {path.name}: {exc}")
                continue
            self._events[e.event_id] = e

    def get(self, event_id: str) -> Event:
        if event_id not in self._events:
            raise KeyError(f"unknown event_id {event_id!r}")
        return self._events[event_id]

    def ids(self) -> list[str]:
        return list(self._events)

    def all(self) -> list[Event]:
        return list(self._events.values())


_store: EventStore | None = None


def store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore()
    return _store
