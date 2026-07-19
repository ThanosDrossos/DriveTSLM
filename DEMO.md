# DEMO.md — video walkthrough script (~4 min)

One continuous screen recording of the deployed app, unhurried pace. Two tabs prepared:
the app (logged in, Welcome view) and the repository README. Pre-run one Grounded
Analysis and one Claims Desk check in separate reloads so completed runs can be shown
instantly if live latency is poor; run live where possible — the tool-call stream is
part of the argument.

---

## 0:00–0:50 — Research framing and what this artifact is (Welcome view on screen)

> "This proof-of-concept accompanies my exposé for a thesis on two connected
> contributions. First, DriveTSLM: a generative time-series language model for automotive
> telematics, built with the OpenTSLM-Flamingo recipe on VZCrash — 190,000 real
> 100-hertz crash windows, 31,000 verified crashes — to test whether TSLM reasoning
> transfers from the medical domains where the lab established it to kinematic sensor
> data. Second, CrashCheck: to my knowledge the first benchmark for cross-modal
> consistency checking between accident narratives and vehicle telemetry, constructed
> from NHTSA CISS cases, which pair real written crash summaries with the vehicle's
> event-data-recorder download — I verified a join yield of 1,322 usable narrative-EDR
> cases in the 2022 release alone.
>
> What exists today, and what you're seeing, is the no-training arm of that thesis: a
> frontier model given deterministic signal-processing tools, operating under a
> machine-checked grounding constraint — every quantitative claim must cite the tool
> result that produced it, and a validator re-derives every cited number. Around it, a
> miniature of the CrashCheck protocol: thirty-five narrative variants with
> ground-truth-by-construction, evaluated at three repetitions with deterministic
> scoring. No training, no GPU, all public data — the thesis upgrades each component
> rather than replacing the loop."

- Gesture briefly at the four view cards; do not click yet.

## 0:50–1:50 — Grounded analysis: the accountability mechanism (Grounded Analysis view)

- Select a VZCrash crash event, *Run both arms*.
> "Both arms are the same model. The left arm holds tools — window metadata, slicing,
> per-channel statistics, threshold detections, plot rendering — and is bound by the
> citation rule. The right arm receives a fully rendered plot of every channel: a
> deliberately fair plot-reading baseline."
- While the trace streams, point at individual calls:
> "Each call is logged with arguments and returned values; citations in the final answer
> resolve to these exact results. The validator is unit-aware — kilometres per hour
> against metres per second, g against metres per second squared — and
> rounding-consistent: a claim is valid only if the tool value rounds to it at the
> claimed precision."
- Hover a green chip, then any red flag:
> "Green: the number exists in the cited result. Red: it does not — in an early run the
> validator caught the model asserting a seventy-four-degree net rotation where the
> cited integral was nineteen. The baseline's numbers, whatever their quality, are
> structurally unverifiable — that asymmetry, at identical model capability, is the
> point of the comparison. Token counts and cost per arm are reported below; a full
> grounded analysis costs about a third of a cent on the default model."

## 1:50–2:50 — Consistency checking: one detection, one failure (Claims Desk view)

- Select the Toyota Camry pole impact (`ciss_2022_25581_v1`), narrative "Claimant
  statement A"; run without revealing its ground truth.
> "The checker first decomposes the narrative into typed atomic assertions — speed,
> braking, impact direction, impact count, severity, sequence — then verifies each
> against the sensors and must commit to per-assertion verdicts through a typed
> submission interface."
- When the verdict table renders, point at the contradicted severity row:
> "The claimant describes a light, glancing pole contact. The EDR records a
> seventy-six-kilometre-per-hour longitudinal delta-V with airbag command at
> three-point-five milliseconds — contradicted, with the evidence cited. Note the
> abstentions: repair costs and pre-impact intent are not sensor-decidable, and the
> checker is instructed that abstention is the correct output there."
- Click **Reveal ground truth**:
> "One error was injected into this narrative — understated severity — and every other
> stated fact was authored to agree with the telemetry. That construction is what makes
> the verdict scorable rather than anecdotal."
- Switch to the prepared failure, the Honda Accord (`ciss_2022_27367_v2`), fabricated
  rear-end variant:
> "And a documented failure: the EDR shows minus eighteen kilometres per hour of
> longitudinal delta-V — a frontal deceleration, physically incompatible with being
> struck from behind — yet the checker accepts the rear-end claim in all three
> repetitions. Sign-convention physics does not survive contact with this model tier,
> and the evaluation quantifies exactly that."

## 2:50–3:25 — The evaluation (Results view)

> "Every narrative, three repetitions, scored deterministically — a run flags a
> narrative if and only if at least one assertion is contradicted; no LLM judge
> anywhere. Contradiction precision zero-point-eight-six, recall zero-point-eight-two,
> at half a cent per case with run-to-run agreement of zero-point-eight-nine. The
> per-error-type gradient is the substantive result: severity and speed
> misstatements are detected at or near one-hundred percent, event-count errors at
> eight of nine — impact direction at one of six. Which error classes are detectable,
> under which grounding constraints, is precisely the research question the thesis
> scales up. I also report a calibration experiment: tightening the contradiction
> criterion raised precision and doubled event-count detection while collapsing
> direction detection — the per-type trade-off is in the README with both prompt
> versions archived."

## 3:25–4:00 — Thesis trajectory and lab fit (README architecture section on screen)

> "The six-month plan replaces neither the data nor the protocol — it upgrades the
> arms. DriveTSLM becomes the trained arm: OpenTSLM-Flamingo curriculum on VZCrash,
> evaluated against the dataset's published specialized baselines and against this
> tool agent, with token cost as a reported axis. CrashCheck becomes the scaled
> benchmark: thirteen-hundred-plus real narrative-EDR cases per release year, a
> systematic perturbation taxonomy, and a synthetic first-notice-of-loss track. The
> citation validator and the scoring harness transfer unchanged. The application
> domain aligns with the lab's Zurich Insurance partnership — claims processing is a
> setting where auditable grounding is the deliverable itself — and automotive
> telematics extends the OpenTSLM programme into a vertical it does not yet occupy.
> Code, data pipelines, and all one-hundred-and-five-times-two evaluation runs are in
> the repository."

- Close with the repository URL and the hosted-demo URL on screen.

---

## Recording checklist

- [ ] Fresh session against the deployed app; type the password on camera (gate shown once).
- [ ] Browser zoom 110%, 1080p capture, bookmarks bar hidden.
- [ ] Pre-runs completed in background tabs (Camry check, one grounded analysis).
- [ ] Results view populated (eval results are committed with the repo).
- [ ] Repo README open in the second tab for the closing section.
