# Claims Desk — evidence-grounded agentic reasoning over crash telemetry

Proof-of-concept accompanying the DriveTSLM + CrashCheck research exposé (ETH Agentic Systems Lab application, Thanos Drossos, July 2026).

An LLM agent inspects real automotive crash telemetry through deterministic tools and produces natural-language event descriptions in which **every quantitative claim must cite a tool-computed value** (validated by the backend, flagged in the UI). The same machinery cross-examines accident narratives against the sensor evidence and returns per-assertion verdicts.

> Status: under construction. This README is filled in as milestones land.

## Quick start

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY, DEMO_PASSWORD
docker compose up
```

## Repository layout

```
backend/    FastAPI app: telemetry tools, agent loop, citation validator, consistency checker
frontend/   React UI: Event Explorer, Grounded Analysis, Claims Desk
data/       Pipelines for VZCrash + NHTSA CISS, cached working set, narrative sets
eval/       Evaluation harness and committed results
```
