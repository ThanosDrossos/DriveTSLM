import { useEffect, useState } from "react";
import { api } from "./api";
import { Stat } from "./ui";

export default function ResultsView() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api("/api/results").then(setData).catch(() => setData({ available: false }));
  }, []);

  if (!data) return <p>loading…</p>;
  if (!data.available)
    return (
      <>
        <h1>Results</h1>
        <div className="panel">
          <p className="mt0" style={{ margin: 0 }}>
            No committed evaluation yet. Run <code>python eval/run_eval.py</code> (needs
            ANTHROPIC_API_KEY) — the summary lands here and in <code>eval/results/</code>.
          </p>
        </div>
      </>
    );

  const s = data.summary;
  return (
    <>
      <h1>Evaluation results</h1>
      <p className="sub">
        The consistency checker over every narrative variant, {s.n_runs / Object.keys(s.per_narrative_overalls).length}
        &nbsp;repetitions each, scored deterministically against ground-truth-by-construction
        (injected single errors). Model: <code>{s.model}</code>.
      </p>
      <div className="panel">
        <h3>Headline metrics</h3>
        <div className="statrow">
          <Stat k="runs ok" v={`${s.n_ok}/${s.n_runs}`} />
          <Stat k="precision" v={s.contradiction_precision ?? "—"} />
          <Stat k="recall" v={s.contradiction_recall ?? "—"} />
          <Stat k="FP rate" v={s.false_positive_rate ?? "—"} />
          <Stat k="abstention" v={s.abstention_rate ?? "—"} />
          <Stat k="citation validity" v={s.citation_validity_rate_mean ?? "—"} />
          <Stat k="cost/case" v={`$${s.mean_cost_usd_per_case}`} />
          <Stat k="rep agreement" v={s.run_to_run_agreement_mean ?? "—"} />
        </div>
      </div>
      <div className="panel">
        <h3>Per injected error type</h3>
        <table className="data">
          <thead>
            <tr><th>error type</th><th>runs</th><th>detected</th><th>recall</th><th>localized to right assertion</th></tr>
          </thead>
          <tbody>
            {Object.entries(s.per_error_type).map(([err, c]: [string, any]) => (
              <tr key={err}>
                <td>{err}</td>
                <td className="num">{c.n}</td>
                <td className="num">{c.detected}</td>
                <td className="num">{c.recall}</td>
                <td className="num">{c.localized}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h3>Per-narrative verdicts across repetitions</h3>
        <table className="data">
          <thead><tr><th>narrative</th><th>verdicts</th></tr></thead>
          <tbody>
            {Object.entries(s.per_narrative_overalls).map(([nid, vs]: [string, any]) => (
              <tr key={nid}>
                <td className="num">{nid}</td>
                <td className="num">{(vs as string[]).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
