const ext = { target: "_blank", rel: "noreferrer" };

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const Icons = {
  explorer: (
    <svg width="19" height="19" viewBox="0 0 24 24" {...stroke}>
      <polyline points="2 12 6 12 9 5 13 19 16 12 22 12" />
    </svg>
  ),
  analysis: (
    <svg width="19" height="19" viewBox="0 0 24 24" {...stroke}>
      <rect x="3" y="4" width="7.5" height="16" rx="1.5" />
      <rect x="13.5" y="4" width="7.5" height="16" rx="1.5" />
    </svg>
  ),
  claims: (
    <svg width="19" height="19" viewBox="0 0 24 24" {...stroke}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 8h8M8 12h8" />
      <path d="M8 16.5l2 2 4-4" />
    </svg>
  ),
  results: (
    <svg width="19" height="19" viewBox="0 0 24 24" {...stroke}>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  ),
};

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
    icon: React.ReactNode;
    title: string;
    text: string;
  }[] = [
    {
      tab: "explorer",
      icon: Icons.explorer,
      title: "Event Explorer",
      text:
        `${nEvents || 50} real events: VZCrash windows (100 Hz IMU, GPS speed, labeled) and ` +
        "NHTSA CISS cases (technician narrative + EDR recording), with per-channel plots and " +
        "the deterministic threshold detections available to the agent.",
    },
    {
      tab: "analysis",
      icon: Icons.analysis,
      title: "Grounded Analysis",
      text:
        "The same model in two arms: a tool-using agent under the citation constraint versus " +
        "a plot-only baseline. Tool-call trace, validated citations, token counts and cost " +
        "are shown for both.",
    },
    {
      tab: "claims",
      icon: Icons.claims,
      title: "Claims Desk",
      text:
        "A narrative is decomposed into typed assertions, each verified against the sensors: " +
        "supported, contradicted, or unverifiable, with cited evidence. Ground truth is " +
        "revealed only after the verdict.",
    },
    {
      tab: "results",
      icon: Icons.results,
      title: "Results",
      text:
        "All narrative variants × 3 repetitions, scored deterministically against injected " +
        "single errors: precision/recall per error type, abstention, citation validity, " +
        "cost per case, run-to-run agreement.",
    },
  ];

  return (
    <>
      <h1>Claims Desk — evidence-grounded agentic reasoning over crash telemetry</h1>
      <p className="sub">
        Proof-of-concept for the <b>DriveTSLM + CrashCheck</b> thesis proposal
        (ETH Agentic Systems Lab application, Thanos Drossos). Real, public sensor data
        throughout; no synthetic traces.
      </p>

      <div className="panel prose">
        <h3>Overview</h3>
        <p className="mt0" style={{ margin: 0 }}>
          Insurance claims are settled on narratives that are rarely checked against what the
          vehicle recorded. Claims Desk investigates whether an LLM agent can close that gap
          under verifiable grounding: the agent inspects raw crash telemetry exclusively
          through deterministic tools, every quantitative statement must cite the tool result
          that produced it, and a backend validator re-derives each cited number (unit-aware,
          rounding-consistent). The same machinery cross-examines accident narratives and
          returns per-assertion verdicts with cited evidence. Current model:{" "}
          <code>{model}</code>, selectable in the sidebar; cost is reported per run.
        </p>
      </div>

      <div className="panel">
        <h3>The four views</h3>
        <div className="card-grid">
          {pages.map((p) => (
            <button key={p.tab} className="nav-card" onClick={() => onNavigate(p.tab)}>
              <div className="nav-card-head">
                <span className="nav-card-icon">{p.icon}</span>
                <span className="nav-card-title">{p.title}</span>
              </div>
              <div className="nav-card-text">{p.text}</div>
              <div className="nav-card-go">open view →</div>
            </button>
          ))}
        </div>
      </div>

      <div className="panel prose">
        <h3>Connection to the Agentic Systems Lab · OpenTSLM</h3>
        <p className="mt0">
          <a href="https://github.com/StanfordBDHG/OpenTSLM" {...ext}>OpenTSLM</a>{" "}
          (<a href="https://arxiv.org/abs/2510.02410" {...ext}>ICML 2026</a>) established
          time-series language models — natural-language reasoning grounded in raw sensor
          streams — in medical domains. The proposed thesis extends this line to automotive
          telematics, a vertical the lab's TSLM portfolio does not yet occupy and one aligned
          with the lab's <b>Zurich Insurance AI Lab</b> partnership: in claims processing,
          auditable grounding is the deliverable itself.
        </p>
        <ul>
          <li>
            <b>DriveTSLM</b> — a generative TSLM for automotive telemetry
            (OpenTSLM-Flamingo recipe,{" "}
            <a href="https://huggingface.co/datasets/vzc-research-chapter/VZCrash" {...ext}>
              VZCrash
            </a>, 190k windows), evaluated against specialized detectors and against the
            tool-using agent shown here.
          </li>
          <li>
            <b>CrashCheck</b> — a benchmark for narrative-vs-telemetry consistency checking
            built from{" "}
            <a href="https://www.nhtsa.gov/crash-data-systems/crash-investigation-sampling-system" {...ext}>
              NHTSA CISS
            </a>{" "}
            narrative+EDR pairs with controlled perturbations; this demo runs the protocol in
            miniature.
          </li>
        </ul>
        <div className="rq-box">
          <div className="rq-head">Research questions of the thesis</div>
          <ol>
            <li>
              <b>Transfer.</b> Do time-series language models transfer from medical to
              kinematic sensor domains, zero-shot and fine-tuned?
            </li>
            <li>
              <b>Grounded reasoning vs. specialized models.</b> Can a telematics TSLM match
              specialized crash detectors while producing auditable rationales, and at what
              token and compute cost relative to a no-training tool-using agent?
            </li>
            <li>
              <b>Consistency.</b> At what precision can narrative-vs-telemetry checking
              detect misreported claims, and which error types — direction, magnitude,
              count, sequence — are detectable?
            </li>
          </ol>
        </div>
        <p className="small" style={{ marginBottom: 0 }}>
          Code:{" "}
          <a href="https://github.com/ThanosDrossos/DriveTSLM" {...ext}>
            github.com/ThanosDrossos/DriveTSLM
          </a>{" "}
          · Lab: <a href="https://www.agenticsystemslab.org" {...ext}>agenticsystemslab.org</a>{" "}
          · Data: VZCrash (CC BY-NC 4.0, gated), NHTSA CISS (public).
        </p>
      </div>
    </>
  );
}
