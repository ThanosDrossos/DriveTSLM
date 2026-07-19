import { useEffect, useState } from "react";
import AnalysisView from "./AnalysisView";
import { api } from "./api";
import ClaimsDeskView from "./ClaimsDeskView";
import ExplorerView from "./ExplorerView";
import ResultsView from "./ResultsView";
import WelcomeView from "./WelcomeView";
import type { EventRow, ModelInfo } from "./types";

type Tab = "welcome" | "explorer" | "analysis" | "claims" | "results";

function Login({ onOk }: { onOk: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api("/api/login", { method: "POST", body: JSON.stringify({ password: pw }) });
      onOk();
    } catch {
      setErr("Wrong password.");
    }
  };
  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>Claims Desk</h1>
        <p>
          Evidence-grounded agentic reasoning over real crash telemetry (VZCrash + NHTSA CISS).
          PoC accompanying the DriveTSLM / CrashCheck exposé.
        </p>
        <form onSubmit={submit}>
          <input type="password" placeholder="demo password" value={pw}
                 onChange={(e) => setPw(e.target.value)} autoFocus />
          <button className="primary" type="submit">Enter</button>
        </form>
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  );
}

export default function App() {
  const [locked, setLocked] = useState<boolean | null>(null);
  const [tab, setTab] = useState<Tab>("welcome");
  const [events, setEvents] = useState<EventRow[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState("");

  const load = async () => {
    try {
      const r = await api("/api/events");
      setEvents(r.events);
      const m = await api("/api/models");
      setModels(m.models);
      setModel((cur) => cur || m.default);
      setLocked(false);
    } catch (e: any) {
      setLocked(true);
    }
  };
  useEffect(() => { load(); }, []);

  const families = [...new Set(models.map((m) => m.family))];

  const [selected, setSelected] = useState<string | null>(null);

  if (locked === null) return null;
  if (locked) return <Login onOk={load} />;

  const tabs: [Tab, string][] = [
    ["welcome", "Welcome"],
    ["explorer", "Event Explorer"],
    ["analysis", "Grounded Analysis"],
    ["claims", "Claims Desk"],
    ["results", "Results"],
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          Claims Desk
          <small>evidence-grounded crash telemetry · DriveTSLM / CrashCheck PoC</small>
        </div>
        <nav>
          {tabs.map(([t, label]) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="model-pick">
          <label>Model (KIT AI Toolbox)</label>
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {families.map((fam) => (
              <optgroup key={fam} label={fam}>
                {models.filter((m) => m.family === fam).map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <div className="foot">
          {events.length} real events · agent runs on <code>{model}</code>
          <br />data: VZCrash (Verizon Connect) + NHTSA CISS
        </div>
      </aside>
      <main className="main">
        {tab === "welcome" && (
          <WelcomeView onNavigate={setTab} nEvents={events.length} model={model} />
        )}
        {tab === "explorer" && (
          <ExplorerView events={events} selected={selected} onSelect={setSelected} />
        )}
        {tab === "analysis" && <AnalysisView events={events} model={model} />}
        {tab === "claims" && <ClaimsDeskView events={events} model={model} />}
        {tab === "results" && <ResultsView />}
      </main>
    </div>
  );
}
