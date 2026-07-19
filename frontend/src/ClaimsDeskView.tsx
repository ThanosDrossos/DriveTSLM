import { useEffect, useMemo, useState } from "react";
import { api, streamRun } from "./api";
import type { Assertion, EventRow, Narrative, StreamEvent, ToolCall, Verdict } from "./types";
import { Badge, CitedText, Spinner, ToolTimeline, UsageStats, ValidationSummary } from "./ui";

/** Neutral display names so ground truth is not telegraphed before the verdict. */
function displayName(n: Narrative, idx: number): string {
  if (n.source === "ciss_summary") return "Technician crash summary";
  return `Claimant statement ${String.fromCharCode(65 + idx)}`;
}

export default function ClaimsDeskView({ events, model }: { events: EventRow[]; model: string }) {
  const withNarr = useMemo(() => events.filter((e) => e.n_narratives > 0), [events]);
  const [eventId, setEventId] = useState("");
  const [narrs, setNarrs] = useState<Narrative[]>([]);
  const [narrId, setNarrId] = useState("");
  const [running, setRunning] = useState(false);
  const [assertions, setAssertions] = useState<Assertion[]>([]);
  const [calls, setCalls] = useState<ToolCall[]>([]);
  const [final, setFinal] = useState<StreamEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [openTool, setOpenTool] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) { setNarrs([]); return; }
    api(`/api/narratives?event_id=${eventId}`).then((r) => {
      setNarrs(r.narratives);
      setNarrId(r.narratives[0]?.narrative_id ?? "");
    });
  }, [eventId]);

  const narrative = narrs.find((n) => n.narrative_id === narrId);
  const claimantIdx = narrs.filter((n) => n.source !== "ciss_summary")
    .findIndex((n) => n.narrative_id === narrId);

  const reset = () => {
    setAssertions([]); setCalls([]); setFinal(null); setError(null); setRevealed(false);
  };

  const run = async () => {
    if (!eventId || !narrId) return;
    reset();
    setRunning(true);
    try {
      await streamRun(`/api/check/${eventId}`, { narrative_id: narrId, model }, (ev) => {
        if (ev.type === "assertions") setAssertions(ev.assertions);
        if (ev.type === "tool_call")
          setCalls((s) => [...s, { id: ev.id, name: ev.name, args: ev.args }]);
        if (ev.type === "tool_result")
          setCalls((s) => s.map((c) => (c.id === ev.id ? { ...c, result: ev.result } : c)));
        if (ev.type === "final") setFinal(ev);
        if (ev.type === "error") setError(ev.message);
      });
    } catch (e: any) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const typeOf = (id: string) => assertions.find((a) => a.id === id);

  return (
    <>
      <h1>Claims Desk — narrative vs. telemetry</h1>
      <p className="sub">
        Pick an event and a narrative. The checker extracts atomic assertions, verifies each
        against the sensors through tools, and returns per-assertion verdicts with cited
        evidence. The narrative's ground truth (whether an error was injected, and which) is
        revealed only <i>after</i> the verdict has been rendered.
      </p>
      <div className="panel">
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
          <select value={eventId} onChange={(e) => { setEventId(e.target.value); reset(); }}>
            <option value="">select event…</option>
            {withNarr.map((e) => (
              <option key={e.event_id} value={e.event_id}>
                {e.event_id} ({e.source})
              </option>
            ))}
          </select>
          <select value={narrId} onChange={(e) => { setNarrId(e.target.value); reset(); }}
                  disabled={!narrs.length}>
            {narrs.map((n, i) => (
              <option key={n.narrative_id} value={n.narrative_id}>
                {displayName(n, narrs.filter((x) => x.source !== "ciss_summary").indexOf(n))}
              </option>
            ))}
          </select>
          <button className="primary" onClick={run} disabled={!narrId || running}>
            Run consistency check
          </button>
        </div>
        {narrative && (
          <div className="narr-text" style={{ marginTop: 12 }}>{narrative.text}</div>
        )}
      </div>

      {running && !final && (
        <div className="panel"><Spinner />
          {assertions.length === 0 ? "extracting assertions…" : "verifying against telemetry…"}
        </div>
      )}
      {error && <div className="panel"><div className="flag">{error}</div></div>}

      {assertions.length > 0 && (
        <div className="row">
          <div className="col">
            <div className="panel">
              <h3>Assertion verdicts</h3>
              <table className="data">
                <thead>
                  <tr><th>assertion</th><th>type</th><th>verdict</th><th>evidence (cited)</th></tr>
                </thead>
                <tbody>
                  {(final?.verdicts as Verdict[] | undefined ?? assertions.map((a) => null as any)).map(
                    (v: Verdict | null, i: number) => {
                      const a = v ? typeOf(v.assertion_id) : assertions[i];
                      return (
                        <tr key={i}>
                          <td style={{ maxWidth: 300 }}>{a?.text}</td>
                          <td><Badge kind="neutral">{a?.type}</Badge></td>
                          <td>{v ? <Badge kind={v.verdict}>{v.verdict}</Badge> : <span className="small">…</span>}</td>
                          <td style={{ maxWidth: 380 }}>
                            {v && <CitedText text={v.evidence} validation={final?.validation} onCite={setOpenTool} />}
                          </td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
              {final && (
                <div style={{ marginTop: 14 }}>
                  <span style={{ marginRight: 8 }}>Overall verdict:</span>
                  <Badge kind={final.derived_overall}>{final.derived_overall}</Badge>
                  <span className="small" style={{ marginLeft: 10 }}>
                    (derived: any contradiction ⇒ inconsistent; model's own call: {final.model_overall})
                  </span>
                  <p className="small" style={{ marginTop: 8 }}>{final.rationale}</p>
                </div>
              )}
              {final?.validation && <ValidationSummary v={final.validation} />}
              {final && !revealed && (
                <div className="reveal">
                  <h4>Ground truth</h4>
                  <button className="ghost" onClick={() => setRevealed(true)}>
                    Reveal ground truth for this narrative
                  </button>
                </div>
              )}
              {final && revealed && narrative && (
                <div className="reveal">
                  <h4>Ground truth</h4>
                  <p style={{ margin: "4px 0" }}>
                    <Badge kind={narrative.ground_truth}>{narrative.ground_truth}</Badge>{" "}
                    {narrative.injected_error && (
                      <>with injected error <Badge kind="neutral">{narrative.injected_error}</Badge></>
                    )}
                    {!narrative.injected_error && <span className="small"> — no error injected</span>}
                  </p>
                  {narrative.note && <p className="small">{narrative.note}</p>}
                  <p className="small" style={{ marginBottom: 0 }}>
                    Checker {final.derived_overall === narrative.ground_truth
                      ? "✔ matched the ground truth."
                      : final.derived_overall === "uncertain"
                        ? "abstained (uncertain)."
                        : "✘ did not match the ground truth."}
                  </p>
                </div>
              )}
            </div>
          </div>
          <div className="col" style={{ maxWidth: 460 }}>
            <div className="panel">
              <h3>Tool-call trace</h3>
              {calls.length === 0 && <p className="small">no tool calls yet…</p>}
              <ToolTimeline calls={calls} openId={openTool} />
            </div>
            {final && (
              <div className="panel">
                <h3>Cost</h3>
                <UsageStats usage={final.usage} />
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
