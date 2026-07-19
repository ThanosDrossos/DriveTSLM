# DEMO.md — Loom walkthrough script (3–4 min)

Target: one continuous screen recording of the deployed app, calm pace, cursor-driven.
Have two browser tabs ready: the app (logged in) and the repo README. Pre-run one
Grounded Analysis and one Claims Desk check so the timeline fills instantly if the live
run is slow; run live if latency cooperates.

## 0:00–0:30 — The problem (Event Explorer open)

> "Insurers settle claims on narratives nobody checks against what the car actually
> recorded. This is Claims Desk: real crash telemetry — Verizon Connect's VZCrash,
> 100 Hz IMU, and NHTSA CISS, which pairs real written crash summaries with black-box
> EDR data — and an agent that has to *prove* every number it says."

- Click one crash event: point at the accel spike in the plot, then at the deterministic
  detections table ("documented thresholds, not the contribution — the tools the agent
  gets").

## 0:30–1:30 — Grounded analysis, side by side (Grounded Analysis view)

- Select the same event, *Run both arms*.
- While the agent streams: "Left: the agent calling get_window_info, detect_events,
  compute_stats — every call logged. Right: the same model, given only this plot."
- When final answers land, hover the citation chips:
> "Every quantitative claim links to the tool call that produced it, and the backend
> re-validates every number — unit-aware, rounding-consistent. Green means verified;
> red means the model said a number the tools never produced. The baseline can't cite
> anything — its numbers are plot-reading guesses, and that difference is the point."
- Point at the cost cards: "tokens and dollars per arm, reported, not hidden."

## 1:30–2:30 — One caught contradiction + one failure (Claims Desk view)

- Pick the Toyota Camry pole crash (`ciss_2022_25581_v1`), narrative "Claimant
  statement A" (*don't* reveal what it is yet). Run.
> "The checker first extracts atomic assertions — speed, braking, direction, severity,
> count — then verifies each against the sensors."
- Verdict table appears: point at the *contradicted* severity row and its citation
  ("claimed a light tap; the EDR recorded a 76 km/h delta-V with airbag at 3.5 ms").
- Click **Reveal ground truth**: "single injected error, understated severity — caught
  and localized. This is scored, not curated: every narrative variant carries its
  ground truth by construction."
- Switch to the prepared failure case — the Honda Accord (`ciss_2022_27367_v2`),
  narrative "Claimant statement A" (fabricated "rear-ended from behind"):
> "And an honest miss: the EDR recorded a −18 km/h longitudinal delta-V — a frontal
> deceleration, physically incompatible with being struck from behind — yet the checker
> marks the rear-end claim as supported in all three repetitions. Sign-convention
> physics is a real capability gap at this model tier, and the eval quantifies it:
> direction errors are the weakest type at 1 of 6 detected. This demo is an evaluation,
> not a highlight reel."

## 2:30–3:15 — The numbers (Results view)

- Scroll the results table:
> "Every narrative, three repetitions: contradiction precision/recall per error type,
> abstention rate, citation validity, cost per case, and run-to-run agreement —
> deterministic scoring, no LLM judge. Precision 0.86, recall 0.82 at half a cent per
> case; severity and speed errors detect at or near 100%, direction errors barely at
> all — knowing *which* error types are detectable is the research question."
- Point briefly at the sidebar model picker: "everything reruns on any of these
> ChatGPT, Gemini or Claude models — cost and behavior become comparable axes."

## 3:15–4:00 — Thesis framing (README architecture section on screen)

> "This PoC is the no-training arm of the thesis. DriveTSLM trains the first generative
> time-series language model on automotive telematics — OpenTSLM's recipe, new domain —
> and competes against exactly this agent, on accuracy and on cost. CrashCheck scales
> this benchmark: 1,300+ real CISS narrative-EDR pairs a year, systematic perturbations,
> three arms. The citation validator and this harness carry over unchanged. Everything
> here is public data and zero GPUs — the thesis upgrade path is scoped, not
> speculative."

## Recording checklist

- [ ] `docker compose up` fresh, password gate shown once (type it on camera).
- [ ] Browser zoom 110%, 1080p capture, no bookmarks bar.
- [ ] Eval results committed so the Results view is populated.
- [ ] Close with the repo URL on screen.
