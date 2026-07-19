# Claims Desk — evidence-grounded agentic reasoning over real crash telemetry

Proof-of-concept accompanying the **DriveTSLM + CrashCheck** research exposé (ETH Agentic
Systems Lab application, Thanos Drossos, July 2026).

An LLM agent inspects real automotive crash telemetry through deterministic tools and
produces event descriptions in which **every quantitative claim must cite the tool result
that contains it** — validated by the backend, flagged red in the UI when wrong. The same
machinery cross-examines accident narratives against the sensors and returns per-assertion
verdicts (supported / contradicted / unverifiable) with cited evidence, scored against
ground-truth-by-construction narrative perturbations.

## Quick start

```bash
cp .env.example .env        # fill in OPENAI_API_KEY (KIT AI Toolbox) + DEMO_PASSWORD
docker compose up           # build + serve everything on http://localhost:8000
```

Local dev without Docker: create a venv from `backend/requirements.txt`, build the
frontend once (`docker run --rm -v "$PWD/frontend:/app" -w /app node:22-alpine sh -c
"npm install && npm run build"`), then `scripts/dev.ps1` (or
`uvicorn app.main:app --app-dir backend`). Everything also runs headless:

```bash
python -m backend.cli list-events
python -m backend.cli analyze ciss_2022_25581_v1 --arm both
python -m backend.cli check ciss_2022_25581_v1 --narrative-id ciss_2022_25581_v1__understated_severity
python eval/run_eval.py --reps 3
```

## The two capabilities

1. **Grounded event analysis** (view: *Grounded Analysis*) — side-by-side arms on the same
   model: the **agent** gets `get_window_info`, `slice_window`, `compute_stats`,
   `detect_events`, `render_plot` and must cite a tool result for every number; the
   **baseline** gets a well-rendered full-window plot and nothing else. Tool-call trace,
   citation chips, token/cost shown for both.
2. **Narrative-vs-telemetry consistency checking** (view: *Claims Desk*) — an LLM call
   extracts atomic typed assertions ({speed, braking, impact_direction, impact_count,
   severity, sequence}); the agent verifies each against the sensors and submits verdicts
   through a strict tool; the backend validates every citation. Ground truth (which single
   error was injected, if any) is revealed only after the verdict.

## Data (real only — no synthetic sensor data anywhere)

**VZCrash** (Verizon Connect, HF `vzc-research-chapter/VZCrash`, gated CC BY-NC 4.0).
100 Hz tri-axial accelerometer [g] + gyroscope [deg/s], 1 Hz GPS speed [km/h], 16 s windows,
3-class labels `{crash, near_miss, normal_driving}` (confirmed from the dataset card — the
paper's binary description is outdated). `data/pipeline/fetch_vzcrash.py` streams a single
test-split shard via HTTP range requests (never the 7.3 GB), verifies shapes/units against
the card at fetch time (recorded in `data/working_set/vzcrash_data_facts.json`), and caches
a stratified ~30-event working set locally. Requires `HF_TOKEN` once; the app never touches
HF at runtime. One documented gap: the device-to-vehicle **axis alignment is not
documented**, so the agent is instructed to treat vehicle-frame direction claims as
unverifiable unless cross-checked against GPS speed.

**NHTSA CISS** (fully public). `data/pipeline/fetch_ciss.py` downloads the yearly CSV zips
from the NHTSA S3 bucket and joins the `CRASH.SUMMARY` technician narrative with the EDR
tables per (case, vehicle). Facts verified against the CISS Analytical User's Manual
(DOT HS 813 243): `EDRPRECRASH` is long-format `PCODE/PTIME/PVALUE` (1010 speed [km/h],
1030 accelerator [%], 1040 service brake on/off, 1080 steering [deg], ~2 Hz, t<0);
`EDRPOSTCRASH` carries the crash-pulse cumulative delta-V curve [km/h] at ~10 ms steps;
`EDREVENT` the delta-V maxima (±150 km/h valid range, sentinels 888/997) and the recorded
event count. **Join yield (2022): 2,929 cases, 100% with narrative; 1,552 vehicles with a
usable pre-crash speed series; 1,467 with speed + valid delta-V; 1,322 cases (45%) fully
joined.** Surprise worth recording: the **2023 release has no SUMMARY column at all**, so
narratives come from 2022. Working set: 20 severity-stratified cases committed under
`data/working_set/`.

The two sources are deliberately different: VZCrash gives dense 100 Hz IMU streams without
narratives; CISS gives real narrative+EDR pairs with sparse kinematics. The unified event
model (`backend/app/events.py`) and every tool handle both.

## Architecture

```
data/pipeline/*  --one-time-->  data/working_set/*.json   (committed, real data)
                                        |
backend/app: events.py (store) -> tools.py (5 deterministic tools, unit-tested)
             citations.py (validator) <- agent.py / baseline.py / consistency.py
             main.py (FastAPI: SSE runs, password gate, plots)
frontend/    Vite+React+TS SPA: Explorer | Grounded Analysis | Claims Desk | Results
eval/run_eval.py  ->  eval/results/summary.{json,md}  (rendered in the app)
```

Models: the agent speaks the OpenAI-compatible chat-completions API against the **KIT AI
Toolbox** (`https://ki-toolbox.scc.kit.edu/api/v1`, any OpenAI-compatible endpoint works
via `OPENAI_BASE_URL`). A curated **model picker** in the UI covers the latest ChatGPT
generations (GPT-5.4/5.5/5.6 variants, GPT-5 mini/nano), Gemini (2.5 Flash/Pro, 3.1,
3.5 Flash) and Claude (Sonnet 5, Opus 4.8, Haiku 4.5) as exposed by the toolbox — all
probed for tool-calling + vision support. Default: `azure.gpt-5-mini` (cheap and reliable;
a full grounded analysis costs ~$0.003 at public list prices, a consistency check ~$0.004).
Costs shown per run are estimates from public per-MTok prices; models newer than the
public price sheets show "n/a".

One robustness mechanism worth naming: **validator-in-the-loop**. If a final answer
contains zero valid citations (typically a model using bare `[T2]` tags instead of
`[claim](T2)` links), the backend feeds the validator's complaints back once and demands a
rewrite. In live testing this took gpt-5-mini from 0 valid / 25 uncited to 12 valid — and
the validator then caught a genuinely fabricated number (a claimed 74.1° net rotation
where the cited tool result said 19.1°), which is precisely the failure mode the PoC is
built to expose.

## Agent rules (enforced, not vibes)

1. Every quantitative claim in a final answer must be written `[claim](Tn)`, citing the
   tool call whose result contains the number. The backend validator re-checks every
   number against that exact result — **unit-aware** (km/h↔m/s↔mph, %↔fraction, s↔ms) and
   **rounding-consistent** (a claim is valid iff the tool value rounds to it at the
   claim's stated precision). Invalid citations and uncited quantitative claims are
   flagged red in the UI and counted in the eval.
2. Insufficient evidence ⇒ say **unverifiable**; abstention is a neutral badge, not an
   error.
3. Axis caution for VZCrash (undocumented device frame): no longitudinal/lateral claims
   without a GPS cross-check.
4. Final answers must contain: classification guess + severity, the narrated event with
   citations, top-3 evidence, and what additional data would change confidence.

The validator (`backend/app/citations.py`, ~140 lines) is the heart of the PoC: without
it, citations are decoration.

## Evaluation

`eval/run_eval.py` runs the consistency checker over **every narrative variant × 3
repetitions** and scores deterministically: a run flags a narrative iff ≥1 assertion comes
back *contradicted* (no LLM judge anywhere). Narratives are ground-truth-by-construction:
for each selected CISS case the real technician summary (consistent) plus a hand-authored
claimant-style variant with **exactly one documented injected error** from the taxonomy
{wrong_impact_direction, understated_severity, claimed_braking_absent, speed_mismatch,
event_count_mismatch}; every other fact in a perturbed narrative was checked against the
telemetry at authoring time (see `note` fields in `data/narratives/narratives.json`).

> **Results: pending the first full eval run** (needs `ANTHROPIC_API_KEY`; the harness is
> committed and resumable). This section will carry the real numbers, including per-error-type
> recall, abstention and citation-validity rates, cost per case, run-to-run agreement — and
> at least one honest failure case.

## Limitations (known, deliberate)

- **VZCrash axis frame is undocumented** — vehicle-frame direction claims on VZCrash are
  by design unverifiable; the eval treats abstaining there as correct, which also means
  direction errors on VZCrash events are hard to catch by construction.
- **CISS "consistent" narratives are technician summaries**, not claimant FNOL statements
  (no real FNOL corpus is public anywhere); the perturbed variants are authored, so the
  benchmark measures detection of *injected* errors, not real-world fraud base rates.
- **CISS kinematics are sparse** (~2 Hz + crash pulse): fine-grained sequence claims often
  end unverifiable.
- Narrative sets are small (~30 variants); the thesis-scale CrashCheck extends this to
  thousands of CISS cases with systematic perturbation generation.
- Costs are estimates from public per-MTok prices.

## PoC → thesis

This PoC proves the loop — telemetry in, grounded reasoning out, narrative cross-examined —
with zero training. The 6-month thesis turns each half into a research contribution:
**DriveTSLM** trains the first generative time-series language model on automotive
telematics (OpenTSLM-Flamingo curriculum on VZCrash's 190k windows) and evaluates it
against the specialized baselines and against this no-training agent, with cost as a
reported axis (RQ1: medical→kinematic transfer; RQ2: grounded reasoning vs specialized
models). **CrashCheck** scales the consistency benchmark from the ~1,322 joinable CISS
narrative+EDR cases (2022 alone) with a systematic perturbation taxonomy and a synthetic
FNOL track over VZCrash, evaluated over three arms — tool agent, DriveTSLM-based checker,
hybrid (RQ3). The citation validator and the deterministic scoring harness carry over
unchanged.

## Repository layout

```
backend/     FastAPI app, agent loop, tools, citation validator, tests, CLI
frontend/    React SPA (4 views)
data/        pipelines (VZCrash gated fetch, CISS join), working set, narratives
eval/        harness + committed results
```

Tests: `python -m pytest backend/tests` (25 validator + tool sanity tests).
