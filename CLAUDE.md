# CLAUDE.md

Working guidance for Claude Code (and any agent) in this repository. `README.md` carries
the research framing, the verified data facts, the results table and the named failure
modes. This file covers what the README does not: the operational map, the invariants that
must not be broken, and the conventions this repo is written to.

## What this is, and what state it is in

**Claims Desk** is a proof-of-concept in which an LLM agent reasons over real automotive
crash telemetry through deterministic tools, under a machine-enforced rule that every
quantitative claim must cite the tool result containing the number. A backend validator
re-derives each cited value. The same machinery cross-examines accident narratives against
the sensors and returns per-assertion verdicts, scored against narrative perturbations with
ground truth by construction.

It accompanies the **DriveTSLM + CrashCheck** research exposé (application to the ETH
Agentic Systems Lab, Thanos Drossos, July 2026). The exposé and application notes live
outside this repository and are deliberately not tracked here.

**Status: complete and submitted.** The evaluation is final, the results are committed
under `eval/results/`, and the numbers in `README.md` are quoted verbatim in the submitted
application materials. Treat this as a frozen artifact: fix bugs, improve docs, but do not
silently change behaviour that would invalidate a committed result. If a change does move
the numbers, re-run the eval with a new `--tag` and update the README table in the same
commit.

Deployed (password gated, min-replicas 1, no cold start):
`https://claims-desk.graybush-6924b6da.germanywestcentral.azurecontainerapps.io`

## Commands

Setup: copy `.env.example` to `.env` and fill `OPENAI_API_KEY` (KIT AI Toolbox) and
`DEMO_PASSWORD`. `HF_TOKEN` is only needed to rebuild the VZCrash working set.

```bash
docker compose up
```

Everything else, from a venv built off `backend/requirements.txt`:

```bash
python -m pytest backend/tests          # 25 tests, ~3 s, no API key needed
python -m backend.cli list-events
python -m backend.cli analyze ciss_2022_25581_v1 --arm both
python -m backend.cli check ciss_2022_25581_v1 --narrative-id ciss_2022_25581_v1__understated_severity
python eval/run_eval.py --reps 3 --workers 3 --tag my-change
scripts/dev.ps1                         # Windows: loads .env, serves on :8000
```

The frontend is a separate build step; it is not rebuilt by the dev server:

```bash
docker run --rm -v "$PWD/frontend:/app" -w /app node:22-alpine sh -c "npm install && npm run build"
```

Deployment and data regeneration have their own runbooks: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
and [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md).

## Architecture

```
data/pipeline/*.py   one-time -->  data/working_set/*.json   (committed, real data)
                                   data/narratives/narratives.json
                                            |
backend/app/  events.py     unified event store (both sources, numpy channels)
              tools.py      5 deterministic telemetry tools, fixed thresholds
              toolspec.py   tool schemas + dispatcher (single source of truth)
              citations.py  the validator
              agent.py      grounded-analysis loop  \
              baseline.py   no-tool plot-reading arm  } all yield the same event stream
              consistency.py narrative checker       /
              llm.py        OpenAI-compatible client, model catalog, cost accounting
              main.py       FastAPI: password gate, SSE runs, plots, results
frontend/src/ Vite + React + TS SPA: Welcome | Explorer | Grounded Analysis | Claims Desk | Results
eval/run_eval.py  -->  eval/results/summary.{json,md} + runs/<model>__<tag>/*.json
```

**The run-stream contract.** `run_grounded_analysis`, `run_baseline` and
`run_consistency_check` are generators yielding progress dicts, and the last event is always
`{"type": "final", ...}` or `{"type": "error", ...}`. Three consumers share that stream:
the SSE endpoint (`_sse` in `main.py`), the CLI (`_drain`), and the eval harness. Adding a
new event type is safe; changing the shape of `final` breaks all three plus the frontend.

**Tool-call ids.** The loop assigns its own sequential ids `T1, T2, ...` (not the provider's
tool-call ids) and prefixes every result with `tool_call_id`. Citations bind to those ids,
so the validator can check a claim against the exact result the model saw. `execute_tool_calls`
in `agent.py` is shared by the analysis and consistency loops; it also handles the
chat-completions quirk that tool results must be strings, so `render_plot` images are
delivered in a follow-up user message.

**Validator-in-the-loop.** If a final answer (or a verdict's evidence field) has zero valid
citations and at least one uncited quantitative claim, the backend feeds the validator's
complaints back once and demands a rewrite. This fires at most once per run and is what
makes smaller models comply with the citation format. It is a real mechanism, not a
workaround to delete.

## Invariants: do not break these

1. **Labels must never reach the agent.** `Event.label` exists for the UI and the eval only.
   No tool in `tools.py` may return it, and no prompt may include it. `events.py` says so in
   its docstring; keep it true.
2. **Ground truth is revealed only after the verdict.** `injected_error` and `ground_truth`
   live on narratives and are shown post-hoc in the UI. Never put them in a prompt.
3. **Citations bind claims to tool results, not to prose.** The format is `[claim text](Tn)`.
   Bare `[Tn]` tags are not citations and the validator ignores them by design. If you loosen
   `CITATION_RE`, the headline citation-validity number stops meaning what the README says it
   means.
4. **The validator is deliberately strict and unit-aware.** A claim is valid iff some tool
   value, converted only by the unit the claim itself states, rounds to the claim at the
   claim's stated precision. Blind cross-unit matching was rejected on purpose (see the
   comment above `UNIT_FACTORS`). Do not widen the conversion table to make runs look better.
5. **Scoring uses `derive_overall`, not the model's own `overall`.** A run flags a narrative
   iff at least one assertion comes back `contradicted`. There is no LLM judge anywhere in the
   eval, and adding one would change the character of the result.
6. **No synthetic sensor data.** Every signal in `data/working_set/` is real. Narratives are
   hand-authored (that is stated and scoped); telemetry is not. Do not generate fake windows
   for tests or demos.
7. **Detector thresholds are fixed and documented.** `detect_events` reports its criterion
   with every detection and `thresholds_doc` in the result. The tools are the instrument, not
   the contribution; tuning them to improve eval numbers would be measuring the wrong thing.
8. **Abstention is a first-class outcome.** `unverifiable` is neutral, not a failure. Prompts,
   UI and metrics all treat it that way.

## Data

`data/working_set/` holds 50 committed events plus two provenance reports
(`ciss_join_report.json`, `vzcrash_data_facts.json`, both skipped by the store loader):

- **20 CISS events** (`ciss_2022_*`): real NHTSA technician narrative plus EDR kinematics,
  sparse (~2 Hz pre-crash) with a crash-pulse delta-V curve. `t=0` is the impact.
- **30 VZCrash events** (`vz_*`): 100 Hz tri-axial accelerometer and gyroscope plus 1 Hz GPS
  speed, no narrative.

Two channel encodings are normalised in `events.py`: implicit time (`sr_hz` + `t_start`, for
VZCrash) and explicit time (`t` array, for CISS). Every channel ends up with numpy `t` and
`v` plus unit and description.

`data/narratives/narratives.json`: 35 narratives, 18 consistent and 17 with exactly one
injected error (speed_mismatch 5, understated_severity 4, claimed_braking_absent 3,
event_count_mismatch 3, wrong_impact_direction 2). For CISS the consistent narrative is the
real technician summary; the perturbed variants are hand-authored with a `note` field
recording what was injected and which facts were checked against the telemetry at authoring
time. Preserve those notes; they are the audit trail for the benchmark.

## Models and cost

The agent speaks the OpenAI chat-completions API against the **KIT AI Toolbox**
(`https://ki-toolbox.scc.kit.edu/api/v1`); any OpenAI-compatible endpoint works via
`OPENAI_BASE_URL`. Model ids are whitelisted in `CURATED_MODELS` (`llm.py`) and
`resolve_model` rejects anything else, so the UI picker cannot be used to call arbitrary
models. Default `azure.gpt-5-mini`.

Costs shown per run are estimates from public per-MTok list prices of the underlying models,
not KIT billing. Models with no public price sheet show `null` and render as "n/a". If you
add a model, add it to both `CURATED_MODELS` and `PRICES_PER_MTOK` (price `None` is fine and
is the honest answer for unpriced models).

## Conventions

- **Commits.** Plain `git commit -m` with a descriptive subject in the existing style
  (`area: what changed`, imperative, specific). **Never add AI attribution**: no
  `Co-Authored-By: Claude`, no "Generated with Claude Code". This repo is an application
  artifact and reads as the applicant's work.
- **Prose voice.** Applicant-voiced text (`DEMO.md`, anything spoken or submitted) uses **no
  em-dashes** and an academic, unhurried register. `README.md` predates that rule and uses
  them; do not churn it just to normalise punctuation.
- **Honesty over polish.** The README names five failure modes with their run JSONs, and the
  worst per-type result (impact direction, 1/6) is reported prominently. That is the point of
  the artifact. Do not soften, round up, or drop a limitation.
- **Both eval sweeps stay.** `summary__v1-prompt.*` and `summary__v2-prompt.*` are kept
  deliberately: the v1 to v2 prompt change traded direction recall for precision, and showing
  both is the evidence that the trade-off is structural rather than incidental.

## Gotchas

- `python -m backend.cli` must run from the repo root; `cli.py` and `run_eval.py` both insert
  `backend/` on `sys.path` themselves.
- The eval is **resumable by cache**: `run_one` returns an existing
  `eval/results/runs/<model>__<tag>/<narrative_id>__rep<k>.json` without calling the API. If
  you change the prompt and forget `--tag`, you will silently re-read old runs. Always pass a
  new `--tag` for a changed configuration.
- The SPA is served by FastAPI from `frontend/dist`, mounted last with a catch-all route.
  Any new API route must be registered before that mount, and must start with `/api` or the
  auth middleware will not gate it.
- Without `DEMO_PASSWORD` set, the gate is disabled and every `/api` route is open. That is
  intended for local dev only; the deployed app always has it set.
- `backend/requirements.txt` still pins `anthropic`, left over from before the migration to
  the OpenAI-compatible KIT endpoint. Nothing imports it.
- The venv here runs Python 3.14; the Docker image is `python:3.13-slim`. Both work, but if
  you hit a version-specific issue, check which one you are in.
- VZCrash windows are **not uniformly 16 s** (roughly 12.5 to 16 in the sampled shard) and the
  device-to-vehicle axis alignment is undocumented. Both are load-bearing facts, not bugs.

## Numbers, and what not to claim

Headline results (`azure.gpt-5-mini`, 35 narratives x 3 reps, 105/105 runs): contradiction
precision 0.857, recall 0.824, false-positive rate 0.130, abstention 0.402, citation validity
0.956, $0.0059 per case, run-to-run agreement 0.886. Per injected error type: speed 15/15,
severity 12/12, count 8/9, braking 6/9, direction 1/6.

Four claims this artifact does **not** support, and that no doc in this repo should make:

- Not "first LLM over IMU data". The human-activity-recognition family (LLaSA, SensorLLM,
  HARGPT) predates it. The defensible claim is narrower: first generative TSLM with
  evidence-grounded rationales over automotive telematics for insurance-relevant reasoning.
- Not that the validator verifies reasoning. It verifies numeric grounding. The direction
  failures are exactly the case where every cited number was real and the physical inference
  from them was wrong.
- Not that any precision figure generalises. It is 35 narratives on one model.
- Not that a trained model will beat the agent. That is RQ2, the question, not the premise.
