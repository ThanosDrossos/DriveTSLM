"""Sanity tests for the telemetry tools.

Two fixture kinds:
- the committed real CISS working set (no synthetic sensor data in the app;
  these are real EDR values), used end-to-end;
- tiny constructed arrays with known ground truth for the math invariants
  (integration, peak finding). These exist only inside the tests.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import events, tools  # noqa: E402
from app.toolspec import run_tool  # noqa: E402


@pytest.fixture(scope="module")
def ciss_event_id():
    ids = [i for i in events.store().ids() if i.startswith("ciss_")]
    assert ids, "CISS working set missing; run data/pipeline/fetch_ciss.py"
    return ids[0]


def make_synthetic_store(tmp_path, monkeypatch):
    """Constructed test fixture (NOT app data): 100 Hz accel with a known
    0.5 g plateau, plus a linear speed ramp."""
    n = 400  # 4 s at 100 Hz
    accel = np.zeros(n)
    accel[100:200] = 0.5          # 1 s plateau between t=1 and t=2
    speed = {"unit": "km/h", "t": [0.0, 1.0, 2.0, 3.0], "v": [50.0, 50.0, 30.0, 10.0]}
    ev = {
        "event_id": "test_1", "source": "vzcrash", "label": "crash",
        "duration_s": 4.0, "time_zero": "window start",
        "channels": {
            "accel_x": {"unit": "g", "sr_hz": 100, "t_start": 0.0, "v": accel.tolist()},
            "gps_speed": speed,
        },
        "meta": {},
    }
    (tmp_path / "test_1.json").write_text(json.dumps(ev), encoding="utf-8")
    st = events.EventStore(tmp_path)
    monkeypatch.setattr(events, "_store", st)
    return st


def test_window_info_real(ciss_event_id):
    info = tools.get_window_info(ciss_event_id)
    assert info["source"] == "ciss"
    assert any(c["name"] == "speed" for c in info["channels"])
    assert "edr_summary" in info
    # ground-truth label must never leak through tools
    assert "label" not in json.dumps(info)


def test_slice_budget_real(ciss_event_id):
    out = tools.slice_window(ciss_event_id, max_points_per_channel=100)
    n_numbers = sum(2 * len(c.get("points", [])) for c in out["channels"].values())
    assert n_numbers <= tools.NUMBER_BUDGET + 40  # small slack for tiny channels


def test_compute_stats_real(ciss_event_id):
    out = tools.compute_stats(ciss_event_id)
    assert "speed" in out["channels"]
    sp = out["channels"]["speed"]
    assert sp["first_t"] <= sp["last_t"] <= 0.01  # pre-crash series ends at t<=0


def test_detect_events_real(ciss_event_id):
    out = tools.detect_events(ciss_event_id)
    assert out["n_detections"] >= 1  # working set selected for valid delta-V
    assert any(d["type"] == "impact_delta_v" for d in out["detections"])


def test_render_plot_real(ciss_event_id):
    meta, png = tools.render_plot(ciss_event_id)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert meta["rendered"]["channels"]


def test_integration_known_truth(tmp_path, monkeypatch):
    make_synthetic_store(tmp_path, monkeypatch)
    # 0.5 g for 1 s = 0.5*9.80665 m/s = 17.65 km/h (baseline median = 0)
    st = tools.compute_stats("test_1", channels=["accel_x"])
    dv = st["channels"]["accel_x"]["integrated_delta_v_kmh"]
    assert abs(dv - 17.7) < 0.3
    assert st["channels"]["accel_x"]["peak_abs_dev"] == 0.5
    assert 1.0 <= st["channels"]["accel_x"]["peak_t"] <= 2.0


def test_speed_drop_detection_known_truth(tmp_path, monkeypatch):
    make_synthetic_store(tmp_path, monkeypatch)
    out = tools.detect_events("test_1")
    drops = [d for d in out["detections"] if d["type"] == "speed_drop"]
    assert drops and drops[0]["drop_kmh"] >= 15
    sustained = [d for d in out["detections"] if d["type"] == "sustained_accel_or_decel"]
    assert sustained, "0.5 g / 1 s plateau must be detected as sustained accel"


def test_slice_downsampling_keeps_spike(tmp_path, monkeypatch):
    st = make_synthetic_store(tmp_path, monkeypatch)
    ev = st.get("test_1")
    ev.channels["accel_x"].v[250] = 6.0  # single-sample spike at t=2.5
    out = tools.slice_window("test_1", channels=["accel_x"], max_points_per_channel=20)
    values = [p[1] for p in out["channels"]["accel_x"]["points"]]
    assert 6.0 in values, "peak-preserving downsampling must keep the spike"


def test_error_paths(ciss_event_id):
    res, png = run_tool("slice_window", {"event_id": ciss_event_id, "channels": ["nope"]})
    assert "error" in res
    res, _ = run_tool("compute_stats", {"event_id": "missing"})
    assert "error" in res
    res, _ = run_tool("compute_stats", {"event_id": ciss_event_id, "t_start": 99, "t_end": 100})
    assert "error" in res
