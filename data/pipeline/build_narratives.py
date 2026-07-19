"""Build data/narratives/narratives.json.

CISS: the REAL technician SUMMARY is the consistent narrative; each selected
case gets ONE hand-authored claimant-style variant with a SINGLE injected,
documented error. Every other fact in a perturbed narrative was checked to be
consistent with (or neutral to) the telemetry at authoring time.

VZCrash narratives are appended by author_vzcrash_narratives() once the gated
working set has been fetched (facts must be read off the real signals first).

Run: python data/pipeline/build_narratives.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.events import store  # noqa: E402

OUT = ROOT / "data" / "narratives" / "narratives.json"

# (event_id, injected_error, perturbed_text, perturbation_note)
CISS_PERTURBED: list[tuple[str, str, str, str]] = [
    (
        "ciss_2022_24570_v2", "speed_mismatch",
        "I was driving my Subaru Legacy northbound in the left lane at about 60 km/h. "
        "The car ahead of me drifted into my lane, and the front of my car hit its rear "
        "end. I had braked just before we collided.",
        "claimed ~60 km/h; EDR pre-crash speed is 111-121 km/h (braking + frontal "
        "impact are consistent with the EDR)",
    ),
    (
        "ciss_2022_25326_v1", "speed_mismatch",
        "I was doing roughly 100 km/h in the left lane when the car in front of me "
        "suddenly slowed. I braked for several seconds but could not avoid hitting it "
        "with my front end.",
        "claimed ~100 km/h; EDR shows 203-253 km/h (multi-second braking + frontal "
        "impact are consistent)",
    ),
    (
        "ciss_2022_26540_v1", "speed_mismatch",
        "I was traveling at highway speed, about 90 km/h, when I struck the back of a "
        "parked vehicle with my front bumper. I hit the brakes only at the last moment.",
        "claimed ~90 km/h; EDR shows 32-36 km/h (last-moment braking + frontal impact "
        "are consistent)",
    ),
    (
        "ciss_2022_25411_v1", "claimed_braking_absent",
        "I was heading east at just under 100 km/h when I lost control on the curve. I "
        "braked hard for several seconds, but the car left the road and hit a tree "
        "head-on.",
        "claimed multi-second hard braking; EDR service-brake is OFF for the entire "
        "pre-crash window (speed ~98 km/h and frontal tree impact are consistent)",
    ),
    (
        "ciss_2022_26196_v1", "claimed_braking_absent",
        "I was driving east at about 85 km/h when I drifted off the road. I stood on "
        "the brakes well before leaving the roadway, but the front of my car still "
        "struck the bridge abutment.",
        "claimed braking well before impact; EDR brake is OFF throughout and speed "
        "RISES 77->90 km/h (speed ~85 and frontal impact are consistent)",
    ),
    (
        "ciss_2022_25581_v1", "understated_severity",
        "Coming out of the curve I slid off the road and clipped a utility pole. It was "
        "a light, glancing contact; the car needed only cosmetic repairs.",
        "claimed light glancing contact; EDR max longitudinal delta-V is -76 km/h with "
        "airbag deployment at 3.5 ms (a severe frontal pole impact)",
    ),
    (
        "ciss_2022_24665_v1", "understated_severity",
        "I drifted onto the shoulder and bumped the back of a parked trailer. It was a "
        "light tap; the truck was still driveable.",
        "claimed light tap; EDR max longitudinal delta-V is -99 km/h at ~96 km/h "
        "travel speed with airbag deployment",
    ),
    (
        "ciss_2022_25905_v2", "wrong_impact_direction",
        "As I was making my right turn onto the southbound road, another car struck the "
        "left side of my Outback. I had just accelerated from a near stop.",
        "claimed left-side impact; EDR shows dominant LONGITUDINAL delta-V (-17 km/h "
        "long vs +4 lat), i.e. a frontal impact (acceleration from near stop 6->28 "
        "km/h is consistent)",
    ),
    (
        "ciss_2022_27367_v2", "wrong_impact_direction",
        "I was accelerating eastbound when my Accord was rear-ended from behind by "
        "another vehicle. I braked right as it happened.",
        "claimed rear-ended (would produce POSITIVE longitudinal delta-V); EDR shows "
        "-18 km/h longitudinal, a frontal deceleration (acceleration 5->35 km/h and "
        "late braking are consistent)",
    ),
    (
        "ciss_2022_24878_v1", "event_count_mismatch",
        "My truck left the road and hit the traffic signal pole. That single impact was "
        "the only one in the crash; the truck then simply came to rest.",
        "claimed a single impact; the EDR recorded 3 events (narrative also describes "
        "pole impact, vehicle splitting, and a further impact)",
    ),
]


def build_ciss() -> list[dict]:
    narratives = []
    st = store()
    for event_id, err, text, note in CISS_PERTURBED:
        ev = st.get(event_id)
        narratives.append({
            "narrative_id": f"{event_id}__real",
            "event_id": event_id,
            "text": ev.narrative,
            "ground_truth": "consistent",
            "injected_error": None,
            "source": "ciss_summary",
            "note": ("real CISS technician summary; describes the whole crash, "
                     f"telemetry is from {ev.narrative_vehicle_ref}"),
        })
        narratives.append({
            "narrative_id": f"{event_id}__{err}",
            "event_id": event_id,
            "text": text,
            "ground_truth": "inconsistent",
            "injected_error": err,
            "source": "authored_claimant_style",
            "note": note,
        })
    return narratives


def load_existing_vz() -> list[dict]:
    """Preserve VZCrash narratives if the file already has them."""
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))["narratives"]
        return [n for n in old if n["event_id"].startswith("vz_")]
    return []


def main() -> None:
    narratives = build_ciss() + load_existing_vz()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"narratives": narratives}, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for n in narratives:
        key = n["injected_error"] or "consistent"
        counts[key] = counts.get(key, 0) + 1
    print(f"wrote {len(narratives)} narratives to {OUT}")
    print("by type:", counts)


if __name__ == "__main__":
    main()
