const ext = { target: "_blank", rel: "noreferrer" };

export default function WelcomeView({
  onNavigate,
  nEvents,
  model,
}: {
  onNavigate: (tab: "explorer" | "analysis" | "claims" | "results") => void;
  nEvents: number;
  model: string;
}) {
  const pages: {
    tab: "explorer" | "analysis" | "claims" | "results";
    title: string;
    text: string;
  }[] = [
    {
      tab: "explorer",
      title: "1 · Event Explorer",
      text:
        `The raw material: ${nEvents || 50} real events — VZCrash windows (100 Hz accelerometer + ` +
        "gyroscope, 1 Hz GPS speed, labeled crash / near-miss / normal) and NHTSA CISS cases " +
        "(real technician crash narratives paired with the vehicle's EDR recording). Inspect " +
        "every channel and the deterministic threshold detections the agent will later use.",
    },
    {
      tab: "analysis",
      title: "2 · Grounded Analysis",
      text:
        "The core comparison, side by side on the same model: an agent that must inspect the " +
        "signals through tools and cite a tool result for every number it states — versus a " +
        "baseline given only a rendered plot. The backend re-validates every citation; wrong " +
        "or missing ones are flagged red. Tool-call trace, token counts and cost are shown " +
        "for both arms.",
    },
    {
      tab: "claims",
      title: "3 · Claims Desk",
      text:
        "The application: pick an accident narrative (real technician summary or a claimant " +
        "statement with exactly one injected, documented error), and the checker extracts " +
        "atomic assertions, verifies each against the sensors, and returns supported / " +
        "contradicted / unverifiable verdicts with cited evidence. Ground truth is revealed " +
        "only after the verdict — an evaluation, not a magic trick.",
    },
    {
      tab: "results",
      title: "4 · Results",
      text:
        "The numbers behind the demo: every narrative variant × 3 repetitions, scored " +
        "deterministically against ground-truth-by-construction (no LLM judge). " +
        "Contradiction precision/recall per error type, abstention rate, citation validity, " +
        "cost per case, and run-to-run agreement — failures included.",
    },
  ];

  return (
    <>
      <h1>Claims Desk — evidence-grounded agentic reasoning over crash telemetry</h1>
      <p className="sub">
        Proof-of-concept for the <b>DriveTSLM + CrashCheck</b> master-thesis proposal
        (ETH Agentic Systems Lab application, Thanos Drossos). Everything here runs on real,
        public sensor data — no synthetic traces anywhere.
      </p>

      <div className="panel">
        <h3>The problem</h3>
        <p className="mt0" style={{ lineHeight: 1.65, margin: 0 }}>
          Insurers collect high-frequency driving telemetry, yet claims are settled on
          narratives that nobody systematically checks against what the vehicle actually
          recorded — while telematics risk scoring stays a black box no adjuster, customer or
          court can audit. Large language models could bridge the two, but only if every
          quantitative statement they make is <i>verifiably grounded</i> in the signal. This
          PoC builds that accountability loop with a frontier model and deterministic tools:
          the agent may only state numbers it can cite from a tool result, a backend validator
          re-checks every citation (unit-aware, rounding-consistent), and accident narratives
          are cross-examined against the sensors with per-assertion verdicts.
        </p>
      </div>

      <div className="panel">
        <h3>The four views</h3>
        <div className="card-grid">
          {pages.map((p) => (
            <button key={p.tab} className="nav-card" onClick={() => onNavigate(p.tab)}>
              <div className="nav-card-title">{p.title}</div>
              <div className="nav-card-text">{p.text}</div>
              <div className="nav-card-go">open view →</div>
            </button>
          ))}
        </div>
        <p className="small" style={{ marginBottom: 0 }}>
          Agent rules, enforced (not vibes): every quantitative claim must be written as a
          citation of the tool call that produced it; insufficient evidence must become
          "unverifiable" rather than a guess; undocumented sensor frames (VZCrash device axes)
          may not be interpreted as vehicle directions. Current model:{" "}
          <code>{model}</code> — switchable in the sidebar (ChatGPT, Gemini and Claude
          generations via the KIT AI Toolbox), with cost reported per run.
        </p>
      </div>

      <div className="panel">
        <h3>Connection to the Agentic Systems Lab · OpenTSLM</h3>
        <p className="mt0" style={{ lineHeight: 1.65 }}>
          The lab's{" "}
          <a href="https://github.com/StanfordBDHG/OpenTSLM" {...ext}>OpenTSLM</a>{" "}
          (<a href="https://arxiv.org/abs/2510.02410" {...ext}>ICML 2026</a>) established
          time-series language models: natural-language reasoning grounded directly in raw
          sensor streams — so far in medical domains (ECG, sleep, activity). This PoC previews
          a thesis that brings that idea to a vertical the lab's TSLM portfolio does not yet
          occupy, automotive telematics — and one that sits squarely on the lab's second
          flagship asset, the partnership with the <b>Zurich Insurance AI Lab</b>: insurance
          claims are a setting where auditable, evidence-grounded reasoning is not an
          interpretability nicety but the product itself, and where a validated
          narrative-vs-telemetry checker has a direct route to real-world evaluation:
        </p>
        <ul style={{ lineHeight: 1.65 }}>
          <li>
            <b>DriveTSLM</b> — the first generative TSLM for automotive telemetry, trained with
            the OpenTSLM-Flamingo recipe on{" "}
            <a href="https://huggingface.co/datasets/vzc-research-chapter/VZCrash" {...ext}>
              VZCrash
            </a>{" "}
            (190k real crash windows), evaluated against specialized detectors <i>and</i>{" "}
            against the no-training tool agent shown here — accuracy and cost as reported axes
            (medical→kinematic transfer is the open scientific question).
          </li>
          <li>
            <b>CrashCheck</b> — the first benchmark for narrative-vs-telemetry consistency
            checking, scaled from the ~1,300 joinable{" "}
            <a href="https://www.nhtsa.gov/crash-data-systems/crash-investigation-sampling-system" {...ext}>
              NHTSA CISS
            </a>{" "}
            narrative+EDR cases per year with controlled perturbations — exactly the
            ground-truth-by-construction scoring this demo already runs in miniature.
          </li>
        </ul>
        <p className="small" style={{ marginBottom: 0 }}>
          The citation validator and the deterministic eval harness carry over to the thesis
          unchanged. Style deliberately echoes the lab's example PoC: naive model vs
          tool-using agent, side by side, on real data, with inspectable traces. Code:{" "}
          <a href="https://github.com/ThanosDrossos/DriveTSLM" {...ext}>
            github.com/ThanosDrossos/DriveTSLM
          </a>{" "}
          · Lab:{" "}
          <a href="https://www.agenticsystemslab.org" {...ext}>agenticsystemslab.org</a> · Data
          licenses: VZCrash CC BY-NC 4.0 (gated), CISS public.
        </p>
      </div>
    </>
  );
}
