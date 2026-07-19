import { useEffect, useState } from "react";
import { api } from "./api";
import type { EventRow } from "./types";
import { Badge } from "./ui";

export default function ExplorerView({
  events,
  selected,
  onSelect,
}: {
  events: EventRow[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    api(`/api/events/${selected}`).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  const vehicleStr = (m: any) =>
    m?.vehicle ? [m.vehicle.model_year, m.vehicle.make, m.vehicle.model].filter(Boolean).join(" ") : "";

  return (
    <>
      <h1>Event Explorer</h1>
      <p className="sub">
        The working set: real crash telemetry cached locally — VZCrash 100 Hz IMU windows and
        NHTSA CISS EDR recordings (sparse ~2 Hz pre-crash series plus the crash-pulse delta-V
        curve). Labels shown here are ground truth from the datasets; the agent never sees them.
      </p>
      <div className="row">
        <div className="col" style={{ maxWidth: 430 }}>
          <div className="panel">
            <h3>Events ({events.length})</h3>
            <table className="data">
              <thead>
                <tr><th>event</th><th>source</th><th>label</th><th></th></tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.event_id}
                      className={`click ${selected === e.event_id ? "sel" : ""}`}
                      onClick={() => onSelect(e.event_id)}>
                    <td>
                      <div className="num">{e.event_id}</div>
                      <div className="small">{vehicleStr(e.meta) || `${e.channels.length} channels`}</div>
                    </td>
                    <td><Badge kind={e.source}>{e.source}</Badge></td>
                    <td>{e.label ? <Badge kind={e.label}>{e.label}</Badge> : <span className="small">—</span>}</td>
                    <td className="small">{e.n_narratives > 0 ? `${e.n_narratives} narr.` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="col">
          {!selected && <div className="panel"><p className="small mt0" style={{ margin: 0 }}>Select an event to inspect its channels.</p></div>}
          {selected && (
            <>
              <div className="panel">
                <h3>Telemetry — {selected}</h3>
                <img className="plot-img" src={`/api/events/${selected}/plot.png`} alt="telemetry plot"
                     key={selected} />
                <p className="small" style={{ marginBottom: 0 }}>
                  Dashed markers = deterministic detections (documented thresholds). Rendered by the same
                  render_plot tool the agent can call.
                </p>
              </div>
              {detail && (
                <div className="panel">
                  <h3>Deterministic detections ({detail.detections.n_detections})</h3>
                  <table className="data">
                    <thead><tr><th>type</th><th>channel</th><th>time</th><th>magnitude</th><th>criterion</th></tr></thead>
                    <tbody>
                      {detail.detections.detections.map((d: any, i: number) => (
                        <tr key={i}>
                          <td><Badge kind="neutral">{d.type}</Badge></td>
                          <td className="num">{d.channel}</td>
                          <td className="num">{d.peak_t ?? d.t ?? d.t_at_max ?? `${d.t_start}–${d.t_end}`} s</td>
                          <td className="num">
                            {d.magnitude ?? d.magnitude_kmh ?? d.drop_kmh ?? d.peak_rate ?? d.net_rotation ?? d.mean_magnitude ?? "—"} {d.unit}
                          </td>
                          <td className="small">{d.criterion}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {detail.edr_summary && (
                    <>
                      <h3 style={{ marginTop: 16 }}>EDR summary (CISS)</h3>
                      <pre style={{ background: "#fafbfc", border: "1px solid var(--border)", borderRadius: 8, padding: 12, fontSize: 12, fontFamily: "var(--mono)", overflowX: "auto" }}>
                        {JSON.stringify(detail.edr_summary, null, 1)}
                      </pre>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
