"""Fetch a small stratified working set from the gated VZCrash dataset.

Requires HF_TOKEN with the gate accepted at
https://huggingface.co/datasets/vzc-research-chapter/VZCrash (gate is
auto-approving after HF login). The app itself never touches HF at runtime;
this script caches ~30 events as local JSON once.

Facts confirmed from the dataset card API (2026-07-19), then re-verified
against the actual arrays at fetch time and recorded in
data/working_set/vzcrash_data_facts.json:
- labels: ClassLabel {0: crash, 1: near_miss, 2: normal_driving}
- gsensor: tri-axial accelerometer, 100 Hz, unit g
- gyro: tri-axial gyroscope, 100 Hz, unit deg/s
- gps_speed: GPS-derived speed, 1 Hz, unit km/h
- 16 s windows; splits train/validation/test = 137,954 / 27,175 / 24,174

We stream ONE test-split shard with pyarrow over HfFileSystem (HTTP range
requests) and stop early, so only a fraction of the 7.3 GB is transferred.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "working_set"

REPO = "datasets/vzc-research-chapter/VZCrash"
SHARD = "data/test-00000-of-00002.parquet"
LABELS = {0: "crash", 1: "near_miss", 2: "normal_driving"}


def get_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        sys.exit(
            "HF_TOKEN is not set. Accept the gate at "
            "https://huggingface.co/datasets/vzc-research-chapter/VZCrash "
            "and export a token (read scope) as HF_TOKEN."
        )
    return token


def peak_abs_g(gsensor: np.ndarray) -> float:
    return float(np.max(np.abs(gsensor)))


def to_event(row: dict, split: str) -> dict:
    gs = np.asarray(row["gsensor"], dtype=np.float32)      # (n, 3)
    gy = np.asarray(row["gyro"], dtype=np.float32)         # (n, 3)
    sp = np.asarray(row["gps_speed"], dtype=np.float32)    # (m,)
    n = gs.shape[0]
    duration = n / 100.0
    axes = ["x", "y", "z"]
    channels = {}
    for i, ax in enumerate(axes):
        channels[f"accel_{ax}"] = {
            "unit": "g", "sr_hz": 100, "t_start": 0.0,
            "desc": f"Accelerometer {ax}-axis",
            "v": [round(float(v), 4) for v in gs[:, i]],
        }
    for i, ax in enumerate(axes):
        channels[f"gyro_{ax}"] = {
            "unit": "deg/s", "sr_hz": 100, "t_start": 0.0,
            "desc": f"Gyroscope {ax}-axis",
            "v": [round(float(v), 3) for v in gy[:, i]],
        }
    channels["gps_speed"] = {
        "unit": "km/h", "sr_hz": 1, "t_start": 0.0,
        "desc": "GPS-derived speed",
        "v": [round(float(v), 2) for v in sp],
    }
    return {
        "event_id": f"vz_{row['event_id']}",
        "source": "vzcrash",
        "label": LABELS[int(row["label"])],
        "duration_s": duration,
        "time_zero": "window start (t=0); event typically mid-window",
        "channels": channels,
        "meta": {
            "split": split,
            "vehiclesize": row.get("vehiclesize"),
            "gyro_is_hd": bool(row.get("gyro_is_hd")),
            "peak_abs_accel_g": round(peak_abs_g(gs), 3),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=8000)
    ap.add_argument("--n-crash", type=int, default=15)
    ap.add_argument("--n-near", type=int, default=8)
    ap.add_argument("--n-normal", type=int, default=7)
    args = ap.parse_args()

    token = get_token()
    from huggingface_hub import HfFileSystem
    import pyarrow.parquet as pq

    fs = HfFileSystem(token=token)
    path = f"{REPO}/{SHARD}"
    print(f"streaming {path} (early-stop after {args.max_rows} rows)")

    crashes: list[tuple[float, dict]] = []
    nears: list[dict] = []
    normals: list[dict] = []
    shapes_seen = set()
    speed_lens = set()
    n_rows = 0

    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=200):
            rows = batch.to_pylist()
            for row in rows:
                n_rows += 1
                gs = np.asarray(row["gsensor"], dtype=np.float32)
                shapes_seen.add(gs.shape)
                speed_lens.add(len(row["gps_speed"]))
                label = LABELS[int(row["label"])]
                if label == "crash":
                    crashes.append((peak_abs_g(gs), row))
                elif label == "near_miss" and len(nears) < args.n_near * 40:
                    nears.append(row)
                elif label == "normal_driving" and len(normals) < args.n_normal * 40:
                    normals.append(row)
            if n_rows >= args.max_rows:
                break

    print(f"scanned {n_rows} rows: {len(crashes)} crash, {len(nears)} near_miss buffered, "
          f"{len(normals)} normal buffered")
    print(f"gsensor shapes seen: {shapes_seen}; gps_speed lengths: {speed_lens}")

    # selection: clear high-g crashes plus a few moderate ones
    crashes.sort(key=lambda t: -t[0])
    n_hi = max(1, args.n_crash - 3)
    moderate = [r for p, r in crashes if 1.5 <= p <= 4.0]
    picked_crash = [r for _, r in crashes[:n_hi]] + moderate[:3]
    picked_crash = picked_crash[: args.n_crash]

    rng = np.random.default_rng(7)
    def sample(pool: list, k: int) -> list:
        if len(pool) <= k:
            return pool
        idx = rng.choice(len(pool), size=k, replace=False)
        return [pool[i] for i in idx]

    picked = (
        [(r, "crash") for r in picked_crash]
        + [(r, "near_miss") for r in sample(nears, args.n_near)]
        + [(r, "normal_driving") for r in sample(normals, args.n_normal)]
    )

    OUT.mkdir(parents=True, exist_ok=True)
    for row, _ in picked:
        e = to_event(row, "test")
        (OUT / f"{e['event_id']}.json").write_text(json.dumps(e), encoding="utf-8")

    facts = {
        "verified_at": "fetch time, from actual arrays",
        "rows_scanned": n_rows,
        "shard": SHARD,
        "label_space": sorted({LABELS[int(r["label"])] for r, _ in [(x, None) for x in
                               [row for row, _ in picked]]}),
        "gsensor_shapes_seen": sorted(str(s) for s in shapes_seen),
        "gps_speed_lengths_seen": sorted(speed_lens),
        "units": {"accel": "g", "gyro": "deg/s", "gps_speed": "km/h"},
        "sampling": {"accel_hz": 100, "gyro_hz": 100, "gps_speed_hz": 1},
        "selected": {
            "crash": len(picked_crash),
            "near_miss": len(sample(nears, args.n_near)),
            "normal_driving": len(sample(normals, args.n_normal)),
        },
    }
    (OUT / "vzcrash_data_facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(f"wrote {len(picked)} events + vzcrash_data_facts.json to {OUT}")


if __name__ == "__main__":
    main()
