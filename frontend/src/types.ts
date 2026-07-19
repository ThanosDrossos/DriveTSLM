export interface EventRow {
  event_id: string;
  source: "vzcrash" | "ciss";
  label: string | null;
  duration_s: number;
  channels: string[];
  meta: Record<string, any>;
  n_narratives: number;
}

export interface Narrative {
  narrative_id: string;
  event_id: string;
  text: string;
  ground_truth: "consistent" | "inconsistent";
  injected_error: string | null;
  source: string;
  note?: string;
}

export interface CitationCheck {
  claim: string;
  tool_id: string;
  numbers: string[];
  unmatched: string[];
  status: "valid" | "invalid" | "unknown_tool_id";
}

export interface Validation {
  citations: CitationCheck[];
  uncited_quantitative_claims: { match: string; context: string }[];
  n_valid: number;
  n_invalid: number;
  n_unknown_id: number;
  n_uncited: number;
  citation_validity_rate: number | null;
  fully_grounded: boolean;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  result?: Record<string, any>;
}

export interface Usage {
  model: string;
  n_api_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd_estimate: number | null;
}

export interface ModelInfo {
  id: string;
  label: string;
  family: string;
}

export interface Verdict {
  assertion_id: string;
  verdict: "supported" | "contradicted" | "unverifiable";
  evidence: string;
}

export interface Assertion {
  id: string;
  type: string;
  text: string;
}

export type StreamEvent = Record<string, any> & { type: string };
