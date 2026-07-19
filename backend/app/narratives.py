"""Narrative sets for the consistency demo.

data/narratives/narratives.json holds hand-authored narratives:
- for CISS events: the REAL technician SUMMARY (ground_truth "consistent") plus
  perturbed variants with exactly ONE injected, documented error each;
- for VZCrash events: hand-written FNOL-style narratives (no real narrative
  exists), one consistent + 1-2 single-error variants.

injected_error taxonomy: wrong_impact_direction | understated_severity |
claimed_braking_absent | speed_mismatch | event_count_mismatch | null
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NARRATIVES_FILE = ROOT / "data" / "narratives" / "narratives.json"

ERROR_TYPES = ["wrong_impact_direction", "understated_severity",
               "claimed_braking_absent", "speed_mismatch", "event_count_mismatch"]


def load_all() -> list[dict]:
    if not NARRATIVES_FILE.exists():
        return []
    return json.loads(NARRATIVES_FILE.read_text(encoding="utf-8"))["narratives"]


def for_event(event_id: str) -> list[dict]:
    return [n for n in load_all() if n["event_id"] == event_id]


def get(narrative_id: str) -> dict:
    for n in load_all():
        if n["narrative_id"] == narrative_id:
            return n
    raise KeyError(f"unknown narrative_id {narrative_id!r}")
