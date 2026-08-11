# Data pipeline runbook

The working set under `data/working_set/` and the narrative set under `data/narratives/` are
**committed**, so nothing here is needed to run the app, the tests, or the eval. This
document exists so the corpus can be regenerated or extended, and so the schema decisions
behind it are not lost.

Raw downloads land in `data/raw/`, which is gitignored. Only the small derived working set is
tracked.

## Order matters

```
fetch_ciss.py  ─┐
                ├─→  data/working_set/*.json  ─→  build_narratives.py  ─→  narratives.json
fetch_vzcrash.py┘
```

`build_narratives.py` imports the event store and reads real signal values, so both fetch
steps must have run first. Run everything from the repository root.

## 1. CISS (public, no login)

```bash
python data/pipeline/fetch_ciss.py --years 2022 2023 --keep 20
```

Downloads the yearly NHTSA CSV zips (~10 to 14 MB each), joins `CRASH.SUMMARY` with the EDR
tables per (case, vehicle), and writes severity-stratified working-set events plus
`ciss_join_report.json`.

Schema facts, verified against the CISS 2020 Analytical User's Manual (DOT HS 813 243) and
the actual releases, and encoded in the script:

- `CRASH.SUMMARY` is the technician narrative. Present for 2929/2929 cases in the 2022
  release. **Absent entirely from the 2023 release**, which is why every narrative in the
  benchmark comes from 2022.
- `EDRPRECRASH` is long format (`PCODE` / `PTIME` / `PVALUE`), ~2 Hz, `PTIME` negative:
  `1010` speed [km/h], `1020` throttle [% full], `1030` accelerator [%], `1040` service brake
  [0/1], `1050` engine RPM, `1060` ABS, `1070` stability control, `1080` steering [deg].
  `PTIME` sentinels 9996/9997, `PVALUE` sentinels 99996/99997.
- `EDRPOSTCRASH` is the same long format with `PTIME` in **milliseconds**: `2010`/`2020`
  delta-V longitudinal/lateral [km/h], `2030`/`2040`/`2050` accel [g], `2060` roll [deg].
- `EDREVENT`: `MAXDVLONG` / `MAXDVLAT` [km/h], valid range +-150, sentinels 888 (invalid) and
  997 (not reported); time fields in ms with sentinels 8888/9995/9997; `NUMEVNTS`.
  `EVENTDESC` is the recorder's own label, **not** an impact direction.
- SAE sign convention: longitudinal delta-V is negative when the vehicle decelerates (frontal
  impact) and positive when pushed forward (struck from behind). The consistency checker is
  told this verbatim.

Join yield for 2022: 2,929 cases, 100% with a narrative; 1,552 vehicles with a usable
pre-crash speed series; 1,467 with speed plus a valid delta-V; **1,322 cases (45%) fully
joined**. That number is the scale argument for thesis-scale CrashCheck, so keep
`ciss_join_report.json` in sync if the join changes.

## 2. VZCrash (gated)

Requires `HF_TOKEN` in `.env` with the gate accepted at
`https://huggingface.co/datasets/vzc-research-chapter/VZCrash` (auto-approving after login).
The app never touches HuggingFace at runtime.

```bash
python data/pipeline/fetch_vzcrash.py --max-rows 8000 --n-crash 15 --n-near 8 --n-normal 7
```

Streams **one** test-split parquet shard over `HfFileSystem` with HTTP range requests and
stops early, so only a fraction of the 7.3 GB moves. Shapes and units are re-verified against
the real arrays at fetch time and recorded in `data/working_set/vzcrash_data_facts.json`.

Facts confirmed from the dataset card and the arrays:

- Labels are 3-class: `{0: crash, 1: near_miss, 2: normal_driving}`. The paper's binary
  description is outdated.
- `gsensor` tri-axial accelerometer 100 Hz [g]; `gyro` tri-axial gyroscope 100 Hz [deg/s];
  `gps_speed` 1 Hz [km/h].
- Nominally 16 s windows, but **lengths vary in practice** (roughly 12.5 to 16 s in the
  sampled shard, GPS 13 to 17 samples). Any dataset class built on this must pad and mask.
- **The device-to-vehicle axis alignment is undocumented.** This is why the agent is
  instructed to treat vehicle-frame direction as unverifiable on VZCrash unless it can
  cross-check against GPS speed, and why direction errors on VZCrash events are hard to catch
  by construction.
- Splits: train/validation/test = 137,954 / 27,175 / 24,174. License CC BY-NC 4.0, which is
  thesis-compatible and blocks commercial use.

## 3. Narratives

```bash
python data/pipeline/build_narratives.py
```

Rewrites `data/narratives/narratives.json` in full from the tables inside the script. The
narratives are **hand-authored in source**, not generated, so the script is the master copy
and the JSON is derived. Editing the JSON directly will be overwritten.

Structure per narrative: `narrative_id`, `event_id`, `text`, `ground_truth`
(`consistent` | `inconsistent`), `injected_error`, `source`, `note`.

- For CISS events the real technician `SUMMARY` is the consistent narrative; each selected
  case gets one claimant-style variant carrying exactly **one** documented injected error.
- For VZCrash events, where no real narrative exists, both the consistent and the perturbed
  narratives are authored FNOL-style from the real signals.
- The `note` field records what was injected and which surrounding facts were checked against
  the telemetry at authoring time. It is the audit trail that makes "ground truth by
  construction" a defensible claim; do not drop it when adding cases.

Injected error taxonomy: `wrong_impact_direction`, `understated_severity`,
`claimed_braking_absent`, `speed_mismatch`, `event_count_mismatch`.

Current set: 35 narratives, 18 consistent and 17 perturbed (speed_mismatch 5,
understated_severity 4, claimed_braking_absent 3, event_count_mismatch 3,
wrong_impact_direction 2).

## Adding cases

`python -m backend.cli event <event_id>` prints window info, detections and per-channel stats
as JSON. That is the authoring aid: read the real evidence first, then write a narrative whose
every fact except the injected one is consistent with it, and record the reasoning in `note`.

After changing the corpus the committed evaluation no longer describes it. Re-run with a fresh
tag and update the README table in the same commit:

```bash
python eval/run_eval.py --reps 3 --workers 3 --tag <new-tag>
```
