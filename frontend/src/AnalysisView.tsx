import { useState } from "react";
import { streamRun } from "./api";
import type { EventRow, StreamEvent, ToolCall } from "./types";
import { Answer, Spinner, ToolTimeline, UsageStats, ValidationSummary } from "./ui";

interface ArmState {
  running: boolean;
  calls: ToolCall[];
  final: StreamEvent | null;
  error: string | null;
}

const empty = (): ArmState => ({ running: false, calls: [], final: null, error: null });

function ArmPanel({ title, subtitle, state, openTool, children }: {
  title: string; subtitle: string; state: ArmState; openTool?: string | null;
  children?: React.ReactNode;
}) {
  return (
    <div className="col panel">
      <h3>{title}</h3>
      <p className="small" style={{ marginTop: -4 }}>{subtitle}</p>
      {children}
      {state.running && <p><Spinner />running…</p>}
      {state.error && <div className="flag">{state.error}</div>}
      {state.calls.length > 0 && (
        <>
          <h3 style={{ marginTop: 14 }}>Tool-call trace</h3>
          <ToolTimeline calls={state.calls} openId={openTool} />
        </>
      )}
      {state.final && (
        <>
          <h3 style={{ marginTop: 14 }}>Answer</h3>
          <Answer text={state.final.answer} validation={state.final.validation} />
          {state.final.validation && <ValidationSummary v={state.final.validation} />}
          {!state.final.validation && (
            <div className="note">
              No citations possible — this arm has no tools, so its numbers cannot be
              validated against computed evidence.
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <UsageStats usage={state.final.usage} />
          </div>
        </>
      )}
    </div>
  );
}

export default function AnalysisView({ events, model }: { events: EventRow[]; model: string }) {
  const [eventId, setEventId] = useState<string>("");
  const [agent, setAgent] = useState<ArmState>(empty());
  const [baseline, setBaseline] = useState<ArmState>(empty());
  const [openTool, setOpenTool] = useState<string | null>(null);
  const [rules, setRules] = useState<string | null>(null);

  const runArm = async (arm: "agent" | "baseline",
                        set: React.Dispatch<React.SetStateAction<ArmState>>) => {
    set({ ...empty(), running: true });
    try {
      await streamRun(`/api/analyze/${eventId}?arm=${arm}&model=${encodeURIComponent(model)}`, undefined, (ev) => {
        if (ev.type === "start" && ev.rules) setRules(ev.rules);
        if (ev.type === "tool_call")
          set((s) => ({ ...s, calls: [...s.calls, { id: ev.id, name: ev.name, args: ev.args }] }));
        if (ev.type === "tool_result")
          set((s) => ({
            ...s,
            calls: s.calls.map((c) => (c.id === ev.id ? { ...c, result: ev.result } : c)),
          }));
        if (ev.type === "final") set((s) => ({ ...s, final: ev, running: false }));
        if (ev.type === "error") set((s) => ({ ...s, error: ev.message, running: false }));
      });
    } catch (e: any) {
      set((s) => ({ ...s, error: String(e), running: false }));
    } finally {
      set((s) => ({ ...s, running: false }));
    }
  };

  const run = () => {
    if (!eventId) return;
    runArm("agent", setAgent);
    runArm("baseline", setBaseline);
  };

  return (
    <>
      <h1>Grounded Analysis — agent vs. plot-only baseline</h1>
      <p className="sub">
        Same model, two arms. The <b>agent</b> inspects the raw signals through deterministic
        tools and must cite a tool result for every number (validated by the backend — invalid
        or missing citations are flagged red). The <b>baseline</b> gets a well-rendered plot of
        the full window and nothing else.
      </p>
      <div className="panel">
        <div className="row" style={{ alignItems: "center" }}>
          <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
            <option value="">select event…</option>
            {events.map((e) => (
              <option key={e.event_id} value={e.event_id}>
                {e.event_id} ({e.source}{e.label ? `, ${e.label}` : ""})
              </option>
            ))}
          </select>
          <button className="primary" disabled={!eventId || agent.running || baseline.running} onClick={run}>
            Run both arms
          </button>
          {rules && (
            <details style={{ flex: 1 }}>
              <summary className="small" style={{ cursor: "pointer" }}>agent rules (enforced, shown as sent)</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 11.5, fontFamily: "var(--mono)", background: "#fafbfc", border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>{rules}</pre>
            </details>
          )}
        </div>
      </div>
      {eventId && (
        <div className="row">
          <ArmPanel title="Agent (tools)" state={agent} openTool={openTool}
                    subtitle="tool access, cite-every-number rule, validator active" />
          <ArmPanel title="Baseline (plot only)" state={baseline}
                    subtitle="same model, full-window plot + channel legend, no tools">
            {eventId && <img className="plot-img" src={`/api/events/${eventId}/plot.png?annotate=false`} alt="baseline input plot" />}
          </ArmPanel>
        </div>
      )}
    </>
  );
}
