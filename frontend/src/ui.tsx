import React from "react";
import type { CitationCheck, ToolCall, Usage, Validation } from "./types";

export const Badge = ({ kind, children }: { kind: string; children: React.ReactNode }) => (
  <span className={`badge ${kind}`}>{children}</span>
);

export const Spinner = () => <span className="spinner" />;

export const Stat = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="stat">
    <div className="k">{k}</div>
    <div className="v">{v}</div>
  </div>
);

export const UsageStats = ({ usage }: { usage: Usage }) => (
  <div className="statrow">
    <Stat k="input tokens" v={usage.input_tokens.toLocaleString()} />
    <Stat k="output tokens" v={usage.output_tokens.toLocaleString()} />
    <Stat k="cache read" v={usage.cache_read_tokens.toLocaleString()} />
    <Stat k="API calls" v={usage.n_api_calls} />
    <Stat k="est. cost" v={`$${usage.cost_usd_estimate.toFixed(4)}`} />
  </div>
);

/** Inline bold (**x**) rendering. */
const bold = (text: string, keyBase: string): React.ReactNode[] =>
  text.split(/\*\*([^*]+)\*\*/g).map((part, i) =>
    i % 2 === 1 ? <strong key={`${keyBase}b${i}`}>{part}</strong> : part,
  );

const CITE_RE = /\[([^\]]+)\]\((T\d+)\)/g;

/** Render text with [claim](Tn) citations as colored chips. */
export function CitedText({
  text,
  validation,
  onCite,
}: {
  text: string;
  validation?: Validation | null;
  onCite?: (toolId: string) => void;
}) {
  const lookup = new Map<string, CitationCheck[]>();
  for (const c of validation?.citations ?? []) {
    const key = `${c.claim}|${c.tool_id}`;
    lookup.set(key, [...(lookup.get(key) ?? []), c]);
  }
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  CITE_RE.lastIndex = 0;
  while ((m = CITE_RE.exec(text))) {
    if (m.index > last) nodes.push(...bold(text.slice(last, m.index), `t${k}`));
    const [, claim, toolId] = m;
    const checks = lookup.get(`${claim}|${toolId}`);
    const status = checks?.shift()?.status ?? "valid";
    nodes.push(
      <span
        key={`c${k++}`}
        className={`cite ${status}`}
        title={status === "valid" ? `verified against ${toolId}` : `FAILED validation against ${toolId}`}
        onClick={() => onCite?.(toolId)}
      >
        {bold(claim, `cb${k}`)}
        <sup>{toolId}</sup>
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(...bold(text.slice(last), "tail"));
  return <>{nodes}</>;
}

/** Minimal markdown-ish renderer: headings-in-bold, bullets, paragraphs, citations. */
export function Answer({
  text,
  validation,
  onCite,
}: {
  text: string;
  validation?: Validation | null;
  onCite?: (toolId: string) => void;
}) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = (key: string) => {
    if (bullets.length) {
      blocks.push(
        <ul key={key}>
          {bullets.map((b, i) => (
            <li key={i}>
              <CitedText text={b} validation={validation} onCite={onCite} />
            </li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };
  lines.forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith("- ") || t.startsWith("* ")) {
      bullets.push(t.slice(2));
    } else {
      flush(`ul${i}`);
      if (t)
        blocks.push(
          <p key={`p${i}`}>
            <CitedText text={t.replace(/^#+\s*/, "")} validation={validation} onCite={onCite} />
          </p>,
        );
    }
  });
  flush("ulEnd");
  return <div className="answer">{blocks}</div>;
}

export function ValidationSummary({ v }: { v: Validation }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div className="statrow">
        <Stat k="citations" v={v.citations.length} />
        <Stat k="valid" v={<span style={{ color: "var(--ok)" }}>{v.n_valid}</span>} />
        <Stat
          k="invalid"
          v={<span style={{ color: v.n_invalid + v.n_unknown_id > 0 ? "var(--bad)" : undefined }}>{v.n_invalid + v.n_unknown_id}</span>}
        />
        <Stat
          k="uncited claims"
          v={<span style={{ color: v.n_uncited > 0 ? "var(--bad)" : undefined }}>{v.n_uncited}</span>}
        />
        <Stat k="fully grounded" v={v.fully_grounded ? "yes" : "no"} />
      </div>
      {v.citations
        .filter((c) => c.status !== "valid")
        .map((c, i) => (
          <div className="flag" key={`iv${i}`}>
            Invalid citation <span className="m">[{c.claim}]({c.tool_id})</span>
            {c.unmatched.length > 0 && <> — numbers not found in {c.tool_id}: <span className="m">{c.unmatched.join(", ")}</span></>}
            {c.status === "unknown_tool_id" && <> — tool id does not exist</>}
          </div>
        ))}
      {v.uncited_quantitative_claims.map((u, i) => (
        <div className="flag" key={`uc${i}`}>
          Uncited quantitative claim <span className="m">"{u.match}"</span>
          <span className="small"> — …{u.context}…</span>
        </div>
      ))}
    </div>
  );
}

export function ToolTimeline({
  calls,
  openId,
}: {
  calls: ToolCall[];
  openId?: string | null;
}) {
  return (
    <div>
      {calls.map((c) => (
        <details key={c.id} className="tool-step" open={openId === c.id} id={`tool-${c.id}`}>
          <summary>
            <span className="tid">{c.id}</span>
            <span className="tname">{c.name}</span>
            <span className="targs">{JSON.stringify(c.args)}</span>
          </summary>
          <pre>{JSON.stringify(c.result ?? "(running…)", null, 1)}</pre>
        </details>
      ))}
    </div>
  );
}
