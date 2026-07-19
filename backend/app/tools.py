"""Deterministic telemetry tools exposed to the agent.

Every tool returns a JSON-serializable dict. Numbers are rounded once, here,
so that what the model reads is exactly what the citation validator later
checks against. Tools never reveal the ground-truth label.

Axis-orientation caveat (VZCrash): the dataset documents units (accel g,
gyro deg/s, speed km/h) but NOT the device-to-vehicle frame alignment. Tools
therefore report per-axis values and never claim an axis is "longitudinal";
the agent is instructed to reason about orientation via GPS-speed
cross-checks or to abstain.

detect_events thresholds (transparent, documented; a tool, not the
contribution):

    IMPACT_SPIKE_G     2.5 g   |a - baseline| above this, >= 2 samples,
                               spikes closer than 0.25 s merged
    SUSTAINED_G band   0.35-1.2 g  moving 0.5 s mean magnitude in band
    SWERVE_YAW_DPS     40 deg/s sustained >= 0.3 s on a gyro axis
    ROLLOVER_ANGLE     60 deg net integrated rotation on one axis, or
    ROLLOVER_RATE      90 deg/s sustained 0.3 s
    SPEED_DROP_KMH     15 km/h decrease within <= 3 s (GPS / EDR speed)
    CISS impact        crash-pulse delta-V magnitude at its max
    CISS braking       brake channel 0 -> 1 transitions
"""

from __future__ import annotations

import base64
import io
import math

import numpy as np

from .events import Channel, Event, store

IMPACT_SPIKE_G = 2.5
IMPACT_MIN_SAMPLES = 2
IMPACT_MERGE_S = 0.25
SUSTAINED_G_LO = 0.35
SUSTAINED_G_HI = 1.2
SUSTAINED_MIN_S = 0.5
SWERVE_YAW_DPS = 40.0
SWERVE_MIN_S = 0.3
ROLLOVER_ANGLE_DEG = 60.0
ROLLOVER_RATE_DPS = 90.0
ROLLOVER_RATE_MIN_S = 0.3
SPEED_DROP_KMH = 15.0
SPEED_DROP_MAX_S = 3.0

G_TO_MS2 = 9.80665
NUMBER_BUDGET = 200  # max numbers returned by one slice_window call


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def _clamp_range(ev: Event, t_start, t_end) -> tuple[float, float]:
    lo = ev.t_min if t_start is None else max(float(t_start), ev.t_min)
    hi = ev.t_max if t_end is None else min(float(t_end), ev.t_max)
    if hi <= lo:
        raise ValueError(f"empty time range [{t_start}, {t_end}] for this event "
                         f"(available: {ev.t_min:.2f}..{ev.t_max:.2f} s)")
    return lo, hi


def _in_range(ch: Channel, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    m = (ch.t >= lo - 1e-9) & (ch.t <= hi + 1e-9)
    return ch.t[m], ch.v[m]


# ---------------------------------------------------------------- tool 1

def get_window_info(event_id: str) -> dict:
    ev = store().get(event_id)
    channels = []
    for c in ev.channels.values():
        channels.append({
            "name": c.name,
            "unit": c.unit,
            "sampling": f"{c.sr_hz:g} Hz" if c.sr_hz else f"irregular, {len(c.t)} points",
            "t_start": _r(c.t_range[0], 3),
            "t_end": _r(c.t_range[1], 3),
            "desc": c.desc,
        })
    out = {
        "event_id": ev.event_id,
        "source": ev.source,
        "time_zero": ev.time_zero,
        "t_min": _r(ev.t_min, 3),
        "t_max": _r(ev.t_max, 3),
        "channels": channels,
    }
    if ev.source == "vzcrash":
        out["notes"] = (
            "100 Hz IMU over a 16 s window. Units: accel g, gyro deg/s, speed km/h. "
            "Device-to-vehicle axis alignment is NOT documented; do not assume which "
            "axis is longitudinal without cross-checking against GPS speed."
        )
    if ev.source == "ciss":
        out["notes"] = (
            "NHTSA CISS EDR data: sparse pre-crash series (~2 Hz, t<0) plus a "
            "crash-pulse delta-V curve (t>=0, ~10 ms steps). t=0 is the impact."
        )
        if ev.edr_summary:
            out["edr_summary"] = ev.edr_summary
        if ev.meta.get("vehicle"):
            out["vehicle"] = ev.meta["vehicle"]
        out["vehicles_in_crash"] = ev.meta.get("vehicles_in_crash")
        out["edr_vehicle"] = ev.narrative_vehicle_ref
    return out


# ---------------------------------------------------------------- tool 2

def slice_window(event_id: str, t_start=None, t_end=None,
                 channels: list[str] | None = None,
                 max_points_per_channel: int = 40) -> dict:
    ev = store().get(event_id)
    lo, hi = _clamp_range(ev, t_start, t_end)
    names = channels or list(ev.channels)
    unknown = [n for n in names if n not in ev.channels]
    if unknown:
        return {"error": f"unknown channels {unknown}; available: {list(ev.channels)}"}

    per_channel = min(max_points_per_channel, max(10, NUMBER_BUDGET // (2 * len(names))))
    out = {"range": {"t_start": _r(lo, 3), "t_end": _r(hi, 3)},
           "downsampling": "per-bucket sample with the largest |deviation from channel median| is kept",
           "channels": {}}
    for n in names:
        ch = ev.channels[n]
        t, v = _in_range(ch, lo, hi)
        if len(t) == 0:
            out["channels"][n] = {"unit": ch.unit, "points": [], "note": "no samples in range"}
            continue
        if len(t) > per_channel:
            baseline = float(np.median(ch.v))
            idx_buckets = np.array_split(np.arange(len(t)), per_channel)
            keep = [int(b[np.argmax(np.abs(v[b] - baseline))]) for b in idx_buckets if len(b)]
            t, v = t[keep], v[keep]
            note = f"downsampled from {int(np.sum((ch.t >= lo) & (ch.t <= hi)))} samples"
        else:
            note = "raw samples"
        out["channels"][n] = {
            "unit": ch.unit,
            "note": note,
            "points": [[_r(a, 3), _r(b, 3)] for a, b in zip(t, v)],
        }
    return out


# ---------------------------------------------------------------- tool 3

def _stats_motion(ch: Channel, t: np.ndarray, v: np.ndarray) -> dict:
    baseline = float(np.median(ch.v))  # full-window median: gravity/mount offset
    dev = v - baseline
    i = int(np.argmax(np.abs(dev)))
    stats = {
        "unit": ch.unit,
        "n_samples": int(len(v)),
        "baseline_median": _r(baseline, 3),
        "peak_abs_dev": _r(abs(dev[i]), 3),
        "peak_signed_dev": _r(dev[i], 3),
        "peak_t": _r(t[i], 2),
        "peak_raw_value": _r(v[i], 3),
        "rms_dev": _r(math.sqrt(float(np.mean(dev ** 2))), 3),
    }
    if len(v) >= 3:
        dt = np.diff(t)
        dt[dt == 0] = np.nan
        jerk = np.diff(v) / dt
        j = int(np.nanargmax(np.abs(jerk)))
        stats["max_rate_of_change_per_s"] = _r(abs(jerk[j]), 1)
        stats["max_rate_of_change_t"] = _r(t[j], 2)
    if ch.name.startswith("accel"):
        dv_ms = float(np.trapezoid(dev, t)) * G_TO_MS2
        stats["integrated_delta_v_kmh"] = _r(dv_ms * 3.6, 1)
        stats["integrated_delta_v_note"] = (
            "integral of (a - baseline) over the range; device-frame axis, "
            "sign/orientation not vehicle-aligned"
        )
    if ch.name.startswith("gyro"):
        stats["integrated_rotation_deg"] = _r(float(np.trapezoid(dev, t)), 1)
    return stats


def _stats_speedlike(ch: Channel, t: np.ndarray, v: np.ndarray) -> dict:
    return {
        "unit": ch.unit,
        "n_samples": int(len(v)),
        "first_value": _r(v[0], 1), "first_t": _r(t[0], 2),
        "last_value": _r(v[-1], 1), "last_t": _r(t[-1], 2),
        "min": _r(float(np.min(v)), 1), "max": _r(float(np.max(v)), 1),
        "change": _r(float(v[-1] - v[0]), 1),
    }


def _stats_binary(ch: Channel, t: np.ndarray, v: np.ndarray) -> dict:
    transitions = []
    for k in range(1, len(v)):
        if v[k] != v[k - 1]:
            transitions.append({"t": _r(t[k], 2), "from": int(v[k - 1]), "to": int(v[k])})
    return {
        "unit": ch.unit,
        "n_samples": int(len(v)),
        "fraction_on": _r(float(np.mean(v > 0)), 2),
        "first_value": int(v[0]),
        "last_value": int(v[-1]),
        "transitions": transitions,
    }


def _stats_deltav(ch: Channel, t: np.ndarray, v: np.ndarray) -> dict:
    i = int(np.argmax(np.abs(v)))
    return {
        "unit": ch.unit,
        "n_samples": int(len(v)),
        "max_abs_value": _r(abs(v[i]), 1),
        "value_at_max": _r(v[i], 1),
        "t_at_max": _r(t[i], 3),
        "final_value": _r(v[-1], 1),
        "note": "cumulative velocity change during the crash pulse",
    }


def compute_stats(event_id: str, t_start=None, t_end=None,
                  channels: list[str] | None = None) -> dict:
    ev = store().get(event_id)
    lo, hi = _clamp_range(ev, t_start, t_end)
    names = channels or list(ev.channels)
    unknown = [n for n in names if n not in ev.channels]
    if unknown:
        return {"error": f"unknown channels {unknown}; available: {list(ev.channels)}"}
    out = {"range": {"t_start": _r(lo, 3), "t_end": _r(hi, 3)}, "channels": {}}
    for n in names:
        ch = ev.channels[n]
        t, v = _in_range(ch, lo, hi)
        if len(v) == 0:
            out["channels"][n] = {"note": "no samples in range"}
            continue
        if n.startswith(("accel", "gyro")) or n == "steering":
            out["channels"][n] = _stats_motion(ch, t, v)
        elif n.startswith("delta_v"):
            out["channels"][n] = _stats_deltav(ch, t, v)
        elif n == "brake":
            out["channels"][n] = _stats_binary(ch, t, v)
        else:  # speed, rpm, throttle, accel_pedal, gps_speed
            out["channels"][n] = _stats_speedlike(ch, t, v)
    return out


# ---------------------------------------------------------------- tool 4

def _segments_above(t: np.ndarray, mask: np.ndarray, min_samples: int,
                    merge_s: float) -> list[tuple[int, int]]:
    """Contiguous True runs of >= min_samples, merged when gaps < merge_s."""
    runs, start = [], None
    for k, m in enumerate(mask):
        if m and start is None:
            start = k
        elif not m and start is not None:
            runs.append((start, k - 1)); start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    runs = [(a, b) for a, b in runs if b - a + 1 >= min_samples]
    merged = []
    for a, b in runs:
        if merged and t[a] - t[merged[-1][1]] < merge_s:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def detect_events(event_id: str) -> dict:
    ev = store().get(event_id)
    found: list[dict] = []

    for n, ch in ev.channels.items():
        t, v = ch.t, ch.v
        if n.startswith("accel"):
            dev = v - float(np.median(v))
            for a, b in _segments_above(t, np.abs(dev) > IMPACT_SPIKE_G,
                                        IMPACT_MIN_SAMPLES, IMPACT_MERGE_S):
                i = a + int(np.argmax(np.abs(dev[a:b + 1])))
                found.append({
                    "type": "impact_spike", "channel": n,
                    "t_start": _r(t[a], 2), "t_end": _r(t[b], 2),
                    "peak_t": _r(t[i], 2), "magnitude": _r(abs(dev[i]), 2),
                    "signed_peak": _r(dev[i], 2), "unit": "g",
                    "criterion": f"|a-baseline| > {IMPACT_SPIKE_G} g for >= {IMPACT_MIN_SAMPLES} samples",
                })
            if ch.sr_hz:
                w = int(SUSTAINED_MIN_S * ch.sr_hz)
                if w > 1 and len(v) > w:
                    mov = np.convolve(dev, np.ones(w) / w, mode="same")
                    band = (np.abs(mov) >= SUSTAINED_G_LO) & (np.abs(mov) <= SUSTAINED_G_HI)
                    for a, b in _segments_above(t, band, w, 0.5):
                        seg = mov[a:b + 1]
                        i = a + int(np.argmax(np.abs(seg)))
                        found.append({
                            "type": "sustained_accel_or_decel", "channel": n,
                            "t_start": _r(t[a], 2), "t_end": _r(t[b], 2),
                            "mean_magnitude": _r(float(np.mean(np.abs(seg))), 2),
                            "peak_moving_avg": _r(mov[i], 2), "unit": "g",
                            "criterion": f"0.5 s moving avg |a-baseline| in {SUSTAINED_G_LO}-{SUSTAINED_G_HI} g",
                            "note": "direction ambiguous: device axis orientation undocumented",
                        })
        if n.startswith("gyro"):
            dev = v - float(np.median(v))
            if ch.sr_hz:
                w = int(SWERVE_MIN_S * ch.sr_hz)
                for a, b in _segments_above(t, np.abs(dev) > SWERVE_YAW_DPS, w, 0.3):
                    i = a + int(np.argmax(np.abs(dev[a:b + 1])))
                    found.append({
                        "type": "high_rotation_rate", "channel": n,
                        "t_start": _r(t[a], 2), "t_end": _r(t[b], 2),
                        "peak_rate": _r(dev[i], 1), "unit": "deg/s",
                        "criterion": f"|omega| > {SWERVE_YAW_DPS} deg/s sustained >= {SWERVE_MIN_S} s",
                    })
                rot = float(np.trapezoid(dev, t))
                if abs(rot) > ROLLOVER_ANGLE_DEG:
                    found.append({
                        "type": "large_net_rotation", "channel": n,
                        "t_start": _r(t[0], 2), "t_end": _r(t[-1], 2),
                        "net_rotation": _r(rot, 1), "unit": "deg",
                        "criterion": f"|integrated rotation| > {ROLLOVER_ANGLE_DEG} deg over window",
                        "note": "rollover-suspect if on a roll/pitch axis; axis frame undocumented",
                    })
        if n in ("gps_speed", "speed"):
            for k in range(len(v)):
                for m in range(k + 1, len(v)):
                    if t[m] - t[k] > SPEED_DROP_MAX_S:
                        break
                    if v[k] - v[m] >= SPEED_DROP_KMH:
                        found.append({
                            "type": "speed_drop", "channel": n,
                            "t_start": _r(t[k], 2), "t_end": _r(t[m], 2),
                            "from_kmh": _r(v[k], 1), "to_kmh": _r(v[m], 1),
                            "drop_kmh": _r(v[k] - v[m], 1), "unit": "km/h",
                            "criterion": f">= {SPEED_DROP_KMH} km/h drop within {SPEED_DROP_MAX_S} s",
                        })
                        break
                else:
                    continue
        if n == "brake":
            for k in range(1, len(v)):
                if v[k] > 0 and v[k - 1] == 0:
                    found.append({
                        "type": "brake_application", "channel": n,
                        "t": _r(t[k], 2), "unit": "on/off",
                        "criterion": "brake status transition 0 -> 1",
                    })
        if n.startswith("delta_v"):
            i = int(np.argmax(np.abs(v)))
            if abs(v[i]) >= 3:
                found.append({
                    "type": "impact_delta_v", "channel": n,
                    "t_at_max": _r(t[i], 3), "magnitude_kmh": _r(abs(v[i]), 1),
                    "signed_kmh": _r(v[i], 1), "unit": "km/h",
                    "criterion": "crash-pulse cumulative delta-V at its maximum",
                })

    # deduplicate speed_drop chains: keep first per channel overlapping window
    dedup: list[dict] = []
    for f in found:
        if f["type"] == "speed_drop" and any(
            d["type"] == "speed_drop" and d["channel"] == f["channel"]
            and abs(d["t_start"] - f["t_start"]) < 2.0 for d in dedup
        ):
            continue
        dedup.append(f)

    return {
        "event_id": event_id,
        "n_detections": len(dedup),
        "detections": dedup,
        "thresholds_doc": (
            f"impact spike: |a-baseline|>{IMPACT_SPIKE_G}g (>=20ms, merged<{IMPACT_MERGE_S}s); "
            f"sustained: 0.5s-avg in {SUSTAINED_G_LO}-{SUSTAINED_G_HI}g; "
            f"rotation: >{SWERVE_YAW_DPS}deg/s for {SWERVE_MIN_S}s; net rotation >{ROLLOVER_ANGLE_DEG}deg; "
            f"speed drop: >={SPEED_DROP_KMH}km/h in <={SPEED_DROP_MAX_S}s; "
            "brake: 0->1 transitions; CISS impact: max |crash-pulse delta-V|"
        ),
    }


# ---------------------------------------------------------------- tool 5

UNIT_GROUPS = [
    ("g", "acceleration [g]"),
    ("deg/s", "rotation rate [deg/s]"),
    ("km/h", "speed / delta-V [km/h]"),
    ("%", "pedal / throttle [%]"),
    ("rpm", "engine [rpm]"),
    ("deg", "steering [deg]"),
    ("on/off", "brake status"),
]


def render_plot(event_id: str, t_start=None, t_end=None,
                channels: list[str] | None = None,
                annotations: list[dict] | None = None) -> tuple[dict, bytes]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ev = store().get(event_id)
    lo, hi = _clamp_range(ev, t_start, t_end)
    names = channels or list(ev.channels)
    unknown = [n for n in names if n not in ev.channels]
    if unknown:
        return {"error": f"unknown channels {unknown}; available: {list(ev.channels)}"}, b""

    groups: list[tuple[str, list[str]]] = []
    for unit, title in UNIT_GROUPS:
        members = [n for n in names if ev.channels[n].unit == unit]
        if members:
            groups.append((title, members))

    fig, axes = plt.subplots(len(groups), 1, figsize=(9, 2.1 * len(groups)),
                             sharex=True, squeeze=False)
    for ax, (title, members) in zip(axes[:, 0], groups):
        for n in members:
            ch = ev.channels[n]
            t, v = _in_range(ch, lo, hi)
            style = dict(lw=0.8) if ch.sr_hz and ch.sr_hz >= 50 else dict(lw=1.4, marker=".", ms=4)
            ax.plot(t, v, label=n, **style)
        for ann in annotations or []:
            ax.axvline(float(ann["t"]), color="crimson", ls="--", lw=0.9)
        ax.set_ylabel(title, fontsize=8)
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(alpha=0.3)
    for ann in annotations or []:
        axes[0, 0].annotate(str(ann.get("label", "")), xy=(float(ann["t"]), 1.0),
                            xycoords=("data", "axes fraction"), fontsize=7,
                            color="crimson", ha="left", va="bottom")
    axes[-1, 0].set_xlabel("time [s]")
    fig.suptitle(f"{event_id}  ({lo:.2f}s – {hi:.2f}s)", fontsize=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    png = buf.getvalue()

    meta = {
        "rendered": {"t_start": _r(lo, 3), "t_end": _r(hi, 3), "channels": names,
                     "annotations": annotations or []},
        "note": "plot returned as image",
    }
    return meta, png


def render_plot_b64(event_id: str, **kwargs) -> tuple[dict, str]:
    meta, png = render_plot(event_id, **kwargs)
    return meta, base64.standard_b64encode(png).decode() if png else ""
