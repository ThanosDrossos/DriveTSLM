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


# VZCrash has no real narratives (no FNOL corpus is public anywhere), so BOTH
# variants are hand-authored claimant-style texts: the consistent one was
# checked fact-by-fact against the real signals (see digest values in the
# notes); the inconsistent one differs by exactly ONE injected error.
# No vehicle-frame direction claims anywhere (axis alignment undocumented).
# (event_id, [(suffix, ground_truth, injected_error, text, note), ...])
VZ_NARRATIVES: list[tuple[str, list[tuple[str, str, str | None, str, str]]]] = [
    ("vz_1511197", [
        ("consistent", "consistent", None,
         "I was on the highway doing just under 80 km/h and had been easing off "
         "gradually for a few seconds as traffic ahead slowed. Then the collision "
         "happened: I felt two distinct jolts about a second apart, and the car "
         "dropped from motorway pace to a crawl within two or three seconds.",
         "matches GPS 79->70 km/h gradual, two accel_x spikes at 9.20 s (-4.7 g) "
         "and 10.17 s (+5.75 g), speed 70->43->16 km/h after impact"),
        ("event_count_mismatch", "inconsistent", "event_count_mismatch",
         "I was on the highway doing just under 80 km/h, easing off as traffic "
         "slowed. There was a single impact - one jolt only - and the car dropped "
         "to a crawl within a couple of seconds.",
         "claims exactly one impact; accelerometer shows two distinct spikes "
         "(-4.7 g at 9.20 s, +5.75 g at 10.17 s, ~1 s apart)"),
    ]),
    ("vz_2026308", [
        ("consistent", "consistent", None,
         "I was traveling at motorway speed, right around 100 km/h, when the crash "
         "happened without much warning. The impact was violent and the car rotated "
         "sharply before coming to a standstill within a few seconds.",
         "matches GPS ~102 km/h steady, +5.89 g spike at 9.74 s, gyro peak "
         "~779 deg/s, speed 98->0 km/h in ~5 s"),
        ("speed_mismatch", "inconsistent", "speed_mismatch",
         "I was driving at about 50 km/h when the crash happened without much "
         "warning. The impact was violent and the car rotated sharply before "
         "coming to a stop.",
         "claims ~50 km/h; GPS shows 98-103 km/h in the seconds before the impact"),
    ]),
    ("vz_1529161", [
        ("consistent", "consistent", None,
         "I was doing about 60 km/h when something hit us more or less out of "
         "nowhere. There were a couple of rapid jolts in quick succession, and we "
         "went from cruising to fully stopped within about four seconds.",
         "matches GPS 60-63 km/h steady, spikes at 6.74/7.44/7.77 s, speed "
         "60->0 km/h between t=6 and t=11"),
        ("claimed_braking_absent", "inconsistent", "claimed_braking_absent",
         "I saw the danger well ahead and braked hard for a good four or five "
         "seconds, but could not avoid the collision. Even after all that heavy "
         "braking from about 60 km/h we still hit and came to a stop.",
         "claims 4-5 s of hard braking BEFORE the impact; GPS is constant "
         "60-63 km/h until the impact spikes at ~6.7 s - deceleration only "
         "begins with the impact itself"),
    ]),
    ("vz_2076649", [
        ("consistent", "consistent", None,
         "I was on the motorway at around 105 to 110 km/h when we took one strong "
         "blow. The car stayed drivable and slowed steadily over the following "
         "seconds.",
         "matches GPS 102-110 km/h, single dominant accel_x spike -5.51 g at "
         "9.97 s, gradual decel 104->27 km/h afterwards"),
        ("understated_severity", "inconsistent", "understated_severity",
         "On the motorway there was a gentle nudge from another vehicle - barely "
         "noticeable, just a light tap. We slowed down afterwards as a precaution.",
         "claims a barely noticeable tap; accelerometer records a -5.5 g spike at "
         "~10 s with multi-g transients on other axes at motorway speed"),
    ]),
    ("vz_2698954", [
        ("consistent", "consistent", None,
         "I had just pulled away and was accelerating for about ten seconds, up to "
         "roughly 45 km/h, when a single heavy impact occurred. After the collision "
         "we slowed and rolled to a near stop.",
         "matches GPS 0->47 km/h acceleration over ~11 s, single -5.86 g spike at "
         "11.01 s, decel to 2 km/h afterwards"),
        ("speed_mismatch", "inconsistent", "speed_mismatch",
         "We were stationary, waiting, when a single heavy impact struck the car. "
         "We had not been moving at all at the time of the collision.",
         "claims the vehicle was stationary at impact; GPS shows ~45 km/h at the "
         "moment of the 11.01 s spike"),
    ]),
    ("vz_2128081", [
        ("consistent", "consistent", None,
         "I accelerated up to about 85 km/h, and then it all went wrong: there "
         "were several impacts in quick succession and the car was thrown about "
         "before we came to a complete stop.",
         "matches GPS 30->86 km/h acceleration, repeated multi-g spikes at "
         "11.0-12.3 s across axes, gyro ~133 deg/s, speed to 0 km/h"),
        ("understated_severity", "inconsistent", "understated_severity",
         "After speeding up, we had a light touch with another vehicle - we barely "
         "made contact, and there was hardly anything to feel inside the car "
         "before we pulled over and stopped.",
         "claims barely perceptible contact; accelerometer records repeated "
         "multi-g spikes (-4.3 g, +4.5 g) and the vehicle goes from 66 km/h to 0"),
    ]),
    ("vz_61371", [
        ("consistent", "consistent", None,
         "A car pulled out in front of me on the fast road. I emergency-braked "
         "from around 110 km/h down to walking pace within a few seconds and we "
         "never touched - no contact at all. Once clear, I picked up speed again.",
         "matches GPS 113->10 km/h hard braking over ~8 s, zero impact spikes, "
         "speed recovering to 42 km/h at window end (near_miss label)"),
        ("event_count_mismatch", "inconsistent", "event_count_mismatch",
         "A car pulled out in front of me on the fast road. I emergency-braked "
         "from around 110 km/h, but it still clipped my car once - a single "
         "impact - before I slowed to walking pace.",
         "claims one impact occurred; the accelerometer shows no impact spike "
         "anywhere in the window (pure braking profile, max |dev| < 1 g)"),
    ]),
    ("vz_23172", [
        ("consistent", "consistent", None,
         "Ordinary city driving: I sped up to about 50 km/h, then slowed down for "
         "a junction and continued at low speed. Nothing unusual happened on this "
         "stretch.",
         "matches GPS 43->52->14 km/h profile, zero impact spikes "
         "(normal_driving label)"),
    ]),
]


def build_vz() -> list[dict]:
    narratives = []
    st = store()
    for event_id, variants in VZ_NARRATIVES:
        st.get(event_id)  # fail fast if the working set lacks the event
        for suffix, gt, err, text, note in variants:
            narratives.append({
                "narrative_id": f"{event_id}__{suffix}",
                "event_id": event_id,
                "text": text,
                "ground_truth": gt,
                "injected_error": err,
                "source": "authored_claimant_style",
                "note": note,
            })
    return narratives


def main() -> None:
    narratives = build_ciss() + build_vz()
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
