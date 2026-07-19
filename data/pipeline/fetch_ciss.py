"""Fetch and join NHTSA CISS crash narratives with EDR kinematics.

Produces unified working-set event JSONs (see FORMAT below) plus a join-yield
report used in the README.

All schema facts below were verified against the CISS 2020 Analytical User's
Manual (NHTSA DOT HS 813 243) and the actual 2022/2023 CSV releases:

- CRASH.SUMMARY: technician-written crash narrative. Present for 2929/2929
  cases in the 2022 release; the SUMMARY column is ABSENT from the 2023
  release entirely (checked 2026-07-19).
- EDRPRECRASH (long format, one row per point): PCODE identifies the series:
    1010 Vehicle Speed [km/h]      1020 Engine Throttle [% full]
    1030 Accelerator Pedal [%]     1040 Service Brake [0=off, 1=on]
    1050 Engine RPM                1060 ABS Activity
    1070 Stability Control         1080 Steering input [deg]
  PTIME is seconds relative to crash time zero (typically -8.0..0 at 2Hz or
  slower; sentinels 9996/9997). PVALUE sentinels: 99996/99997.
- EDRPOSTCRASH (same long format): 2010 Delta-V longitudinal [km/h],
  2020 Delta-V lateral [km/h], 2030/2040/2050 accel long/lat/normal [g],
  2060 roll angle [deg]. PTIME in milliseconds from t0.
- EDREVENT: MAXDVLONG / MAXDVLAT [km/h], valid range +-150 (sentinels
  888 = invalid, 997 = not reported); MAXDVLONGTIME / MAXDVLATTIME /
  MAXDVRESTIME [ms] (sentinels 8888/9995/9997); NUMEVNTS; EVENTDESC (the
  EDR's own record label, not an impact direction).
- EDRREST: LFBELT (driver belt status code), LF1STAGEDEP (driver frontal
  airbag 1st stage deployment time [ms]; large sentinel values mean
  non-deployment / not reported).
- Speed unit note: 49 CFR Part 563 mandates metric EDR reporting and the
  manual documents delta-V "in kilometers (kph)"; vehicle speed medians in
  the data (56) are consistent with km/h (~35 mph), not mph.

Join keys: CASEID + VEHNO (+ EDRSUMMNO, EDREVENTNO for the EDR tables).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "working_set"

BUCKET = "https://static.nhtsa.gov/nhtsa/downloads/CISS"

PRECRASH_CODES = {
    1010: ("speed", "km/h", "Vehicle speed (EDR pre-crash)"),
    1020: ("throttle", "%", "Engine throttle, percent full"),
    1030: ("accel_pedal", "%", "Accelerator pedal, percent full"),
    1040: ("brake", "on/off", "Service brake status (0=off, 1=on)"),
    1050: ("rpm", "rpm", "Engine RPM"),
    1080: ("steering", "deg", "Steering input"),
}
POSTCRASH_CODES = {
    2010: ("delta_v_long", "km/h", "Cumulative longitudinal delta-V during impact"),
    2020: ("delta_v_lat", "km/h", "Cumulative lateral delta-V during impact"),
}
PVALUE_MAX_VALID = 90000  # 99996/99997 are sentinels
PTIME_MAX_VALID = 9000    # 9996/9997 are sentinels


def download(year: int) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    zpath = RAW / f"CISS_{year}_CSV_files.zip"
    if not zpath.exists():
        url = f"{BUCKET}/{year}/CISS_{year}_CSV_files.zip"
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, zpath)
    dest = RAW / f"ciss{year}"
    if not (dest / "CRASH.csv").exists():
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
    return dest


def load_tables(base: Path) -> dict[str, pd.DataFrame]:
    names = ["CRASH", "EDRPRECRASH", "EDRPOSTCRASH", "EDREVENT", "EDRSUMM", "EDRREST", "GV"]
    tables = {n: pd.read_csv(base / f"{n}.csv", low_memory=False) for n in names}
    # VPICDECODE (decoded make/model names) ships in latin-1, not utf-8
    tables["VPICDECODE"] = pd.read_csv(base / "VPICDECODE.csv", low_memory=False, encoding="latin-1")
    return tables


def valid_points(df: pd.DataFrame, pcode: int) -> pd.DataFrame:
    sel = df[
        (df.PCODE == pcode)
        & (df.PVALUE.abs() < PVALUE_MAX_VALID)
        & (df.PTIME.abs() < PTIME_MAX_VALID)
    ]
    return sel.sort_values("PTIME")


def build_channels(pre: pd.DataFrame, post: pd.DataFrame) -> dict:
    """Turn long-format EDR points into named channel arrays. Times in seconds
    relative to crash t0 (pre-crash negative, crash pulse 0..~0.3s)."""
    channels = {}
    for pcode, (name, unit, desc) in PRECRASH_CODES.items():
        pts = valid_points(pre, pcode)
        if pcode == 1040:
            # keep only documented 0/1 codes; other codes (7/8 style) are
            # transcription sentinels we do not want to invent semantics for
            dropped = int((pts.PVALUE > 1).sum())
            pts = pts[pts.PVALUE <= 1]
            if dropped:
                desc = f"{desc}; {dropped} points with undocumented codes dropped"
        if len(pts) >= 2:
            channels[name] = {
                "unit": unit,
                "desc": desc,
                "t": [round(float(x), 3) for x in pts.PTIME],
                "v": [round(float(x), 3) for x in pts.PVALUE],
            }
    for pcode, (name, unit, desc) in POSTCRASH_CODES.items():
        pts = valid_points(post, pcode)
        if len(pts) >= 2:
            channels[name] = {
                "unit": unit,
                "desc": desc + " (times converted from ms to s)",
                "t": [round(float(x) / 1000.0, 4) for x in pts.PTIME],
                "v": [round(float(x), 3) for x in pts.PVALUE],
            }
    return channels


def clean_dv(x) -> float | None:
    return float(x) if pd.notna(x) and abs(x) <= 150 else None


def clean_ms(x) -> float | None:
    return float(x) if pd.notna(x) and 0 <= x <= 2000 else None


def build_year(year: int, n_keep: int) -> tuple[list[dict], dict]:
    base = download(year)
    t = load_tables(base)
    crash, pre, post, ev, summ, rest, gv, vpic = (
        t["CRASH"], t["EDRPRECRASH"], t["EDRPOSTCRASH"], t["EDREVENT"], t["EDRSUMM"], t["EDRREST"], t["GV"],
        t["VPICDECODE"],
    )

    report = {"year": year, "cases_total": int(len(crash))}
    has_summary = "SUMMARY" in crash.columns
    report["has_summary_column"] = has_summary
    if has_summary:
        s = crash.SUMMARY.astype(str).str.strip()
        crash = crash[(s.str.len() > 20)]
        report["cases_with_narrative"] = int(len(crash))
    else:
        report["cases_with_narrative"] = 0
        print(f"CISS {year}: no SUMMARY column in this release; skipping narrative join")
        return [], report

    # vehicles with a usable pre-crash speed series
    speed = valid_points(pre, 1010)
    per_vehicle = (
        speed.groupby(["CASEID", "VEHNO", "EDRSUMMNO", "EDREVENTNO"])
        .size()
        .reset_index(name="n_speed_points")
    )
    per_vehicle = per_vehicle[per_vehicle.n_speed_points >= 6]
    report["vehicles_with_precrash_speed"] = int(per_vehicle[["CASEID", "VEHNO"]].drop_duplicates().shape[0])

    # attach delta-V summary
    ev2 = ev.copy()
    ev2["maxdv_long"] = ev2.MAXDVLONG.map(clean_dv)
    ev2["maxdv_lat"] = ev2.MAXDVLAT.map(clean_dv)
    merged = per_vehicle.merge(
        ev2[["CASEID", "VEHNO", "EDRSUMMNO", "EDREVENTNO", "EVENTDESC", "NUMEVNTS",
             "maxdv_long", "maxdv_lat", "MAXDVLONGTIME", "MAXDVLATTIME"]],
        on=["CASEID", "VEHNO", "EDRSUMMNO", "EDREVENTNO"], how="left",
    )
    merged = merged[merged.maxdv_long.notna()]
    report["vehicles_with_speed_and_deltav"] = int(merged[["CASEID", "VEHNO"]].drop_duplicates().shape[0])

    # narrative join
    merged = merged.merge(crash[["CASEID", "CASENUMBER", "SUMMARY", "VEHICLES", "EVENTS", "MANCOLL", "CRASHTIME"]],
                          on="CASEID", how="inner")
    report["joined_cases"] = int(merged.CASEID.nunique())
    report["joined_vehicles"] = int(merged[["CASEID", "VEHNO"]].drop_duplicates().shape[0])

    # one candidate row per (case, vehicle): the EDR event with most speed points
    merged = merged.sort_values(["CASEID", "VEHNO", "n_speed_points"], ascending=[True, True, False])
    cand = merged.groupby(["CASEID", "VEHNO"]).first().reset_index()

    # prefer 1-2 vehicle crashes (narrative V1/V2 references stay unambiguous)
    cand = cand[cand.VEHICLES <= 2]

    # severity-stratified selection by |maxdv_long|: high / mid / low
    cand["sev"] = cand.maxdv_long.abs()
    cand = cand.sort_values("sev", ascending=False).reset_index(drop=True)
    n = len(cand)
    hi = cand.iloc[: n // 3]
    mid = cand.iloc[n // 3: 2 * n // 3]
    lo = cand.iloc[2 * n // 3:]
    k = max(1, n_keep // 3)
    picked = pd.concat([
        hi.head(n_keep - 2 * k),
        mid.sample(n=min(k, len(mid)), random_state=7),
        lo[lo.sev > 3].head(k),  # low but non-trivial
    ]).drop_duplicates(subset=["CASEID", "VEHNO"]).head(n_keep)

    events = []
    for _, row in picked.iterrows():
        cid, veh = int(row.CASEID), int(row.VEHNO)
        sub_pre = pre[(pre.CASEID == cid) & (pre.VEHNO == veh)
                      & (pre.EDRSUMMNO == row.EDRSUMMNO) & (pre.EDREVENTNO == row.EDREVENTNO)]
        sub_post = post[(post.CASEID == cid) & (post.VEHNO == veh)
                        & (post.EDRSUMMNO == row.EDRSUMMNO) & (post.EDREVENTNO == row.EDREVENTNO)]
        channels = build_channels(sub_pre, sub_post)
        if "speed" not in channels:
            continue

        gvrow = gv[(gv.CASEID == cid) & (gv.VEHNO == veh)]
        vrow = vpic[(vpic.CASEID == cid) & (vpic.VEHNO == veh)]
        vehicle = {}
        if len(vrow):
            v = vrow.iloc[0]
            vehicle["make"] = str(v.Make).title() if pd.notna(v.Make) else None
            vehicle["model"] = str(v.Model) if pd.notna(v.Model) else None
            vehicle["model_year"] = int(v.ModelYear) if pd.notna(v.ModelYear) else None
        if len(gvrow):
            g = gvrow.iloc[0]
            vehicle.setdefault("model_year", int(g.MODELYR) if pd.notna(g.MODELYR) and g.MODELYR < 9000 else None)
            # SPEEDLIMIT is metric in CISS (observed 113 for a 70mph highway)
            vehicle["speed_limit_kmh"] = float(g.SPEEDLIMIT) if pd.notna(g.SPEEDLIMIT) and g.SPEEDLIMIT < 900 else None

        restrow = rest[(rest.CASEID == cid) & (rest.VEHNO == veh)
                       & (rest.EDRSUMMNO == row.EDRSUMMNO) & (rest.EDREVENTNO == row.EDREVENTNO)]
        belt_airbag = {}
        if len(restrow):
            r = restrow.iloc[0]
            belt_airbag = {
                "driver_belt_code": int(r.LFBELT) if pd.notna(r.LFBELT) else None,
                "driver_airbag_stage1_ms": clean_ms(r.LF1STAGEDEP),
            }

        events.append({
            "event_id": f"ciss_{year}_{cid}_v{veh}",
            "source": "ciss",
            "label": None,
            "duration_s": None,  # channels carry explicit, irregular timestamps
            "time_zero": "impact (t=0); pre-crash negative, crash pulse positive",
            "narrative": str(row.SUMMARY).strip(),
            "narrative_vehicle_ref": f"V{veh}",
            "channels": channels,
            "edr_summary": {
                "max_delta_v_long_kmh": row.maxdv_long,
                "max_delta_v_long_time_ms": clean_ms(row.MAXDVLONGTIME),
                "max_delta_v_lat_kmh": row.maxdv_lat,
                "max_delta_v_lat_time_ms": clean_ms(row.MAXDVLATTIME),
                "num_events_recorded": int(row.NUMEVNTS) if pd.notna(row.NUMEVNTS) and row.NUMEVNTS <= 10 else None,
                "event_desc": str(row.EVENTDESC),
                **belt_airbag,
            },
            "meta": {
                "year": year,
                "caseid": cid,
                "casenumber": str(row.CASENUMBER),
                "vehno": veh,
                "vehicles_in_crash": int(row.VEHICLES),
                "vehicle": vehicle,
                "note": ("EDR kinematics are sparse: ~2Hz pre-crash series plus a "
                         "crash-pulse delta-V curve, unlike VZCrash's 100Hz streams."),
            },
        })

    return events, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", type=int, default=[2022, 2023])
    ap.add_argument("--keep", type=int, default=20, help="max cases to keep per year")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    all_reports = []
    total = 0
    for year in args.years:
        events, report = build_year(year, args.keep)
        all_reports.append(report)
        for e in events:
            path = OUT / f"{e['event_id']}.json"
            path.write_text(json.dumps(e, indent=1), encoding="utf-8")
        total += len(events)
        print(f"CISS {year}: kept {len(events)} events; report: {report}")

    (OUT / "ciss_join_report.json").write_text(json.dumps(all_reports, indent=2), encoding="utf-8")
    print(f"done: {total} CISS events in {OUT}")


if __name__ == "__main__":
    sys.exit(main())
