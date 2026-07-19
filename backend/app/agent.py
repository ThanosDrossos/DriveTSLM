"""Grounded-analysis agent: Anthropic tool-use loop with our sequential
tool-call ids (T1, T2, ...) so the citation validator can bind claims to the
exact result the model saw.

The loop is a generator yielding progress events; the FastAPI SSE endpoint,
the CLI, and the eval harness all consume the same stream. The last event is
always {"type": "final", ...} or {"type": "error", ...}.
"""

from __future__ import annotations

import json
from typing import Iterator

from . import citations
from .events import store
from .llm import MODEL, UsageTotal, get_client
from .toolspec import TOOL_SPECS, run_tool

MAX_STEPS = 10

AGENT_RULES = """NON-NEGOTIABLE AGENT RULES (enforced by a backend validator, shown to the user):
1. CITE EVERY NUMBER. Every quantitative claim in your final answer — magnitude, \
axis/direction, timing, speed, count — must be written as a markdown citation \
[claim](Tn), where Tn is the id of the tool call whose RESULT contains the number. \
Example: "[peak of 5.2 g at t=8.13 s](T2)". The validator checks that every number \
in the bracket appears in that tool result (rounding to fewer digits is fine; \
km/h<->m/s<->mph conversions are fine). Uncited or wrongly cited numbers are \
flagged in red to the user.
2. NEVER GUESS. If the evidence is insufficient or ambiguous, write "unverifiable" \
for that point; abstention is rendered as a neutral badge, not an error.
3. AXIS CAUTION. VZCrash accelerometer/gyro axes are device-frame; vehicle-frame \
alignment is undocumented. Do not call an axis "longitudinal"/"lateral" unless you \
cross-checked against GPS speed; otherwise say "axis x/y/z" and treat vehicle-frame \
direction as unverifiable.
4. FINAL ANSWER must contain these markdown sections:
   **Classification**: crash / near_miss / normal_driving + rough severity, as your \
evidence-based guess.
   **What happened**: 2-5 sentences, every quantitative claim cited.
   **Top evidence**: the 3 strongest pieces of evidence as bullets, each cited.
   **What would change my confidence**: 1-2 sentences on missing data."""

SYSTEM = f"""You are the telemetry analysis agent of Claims Desk, a research prototype \
for evidence-grounded reasoning over automotive crash data. You inspect one recorded \
event through deterministic tools and describe what physically happened.

Tool results are JSON prefixed with their tool_call_id ("T1", "T2", ...). You have a \
budget of {MAX_STEPS} tool calls; a good run needs 3-6 (get_window_info, detect_events, \
compute_stats on interesting ranges, optionally slice_window or render_plot to inspect \
detail). Keep the final answer under 350 words.

{AGENT_RULES}"""

TASK_PROMPT = """Analyze event {event_id}. Work out what happened from the sensors, \
then give your final answer following the required format."""


def _serialize_result(tool_id: str, result: dict) -> str:
    return json.dumps({"tool_call_id": tool_id, **result}, separators=(",", ":"))


def run_grounded_analysis(event_id: str, model: str | None = None,
                          max_steps: int = MAX_STEPS) -> Iterator[dict]:
    model = model or MODEL
    client = get_client()
    store().get(event_id)  # raises KeyError early for unknown ids

    usage = UsageTotal(model)
    tool_results: dict[str, dict] = {}
    trace: list[dict] = []
    messages = [{"role": "user", "content": TASK_PROMPT.format(event_id=event_id)}]
    yield {"type": "start", "arm": "agent", "event_id": event_id, "model": model,
           "rules": AGENT_RULES}

    n_calls = 0
    final_text = ""
    for _step in range(max_steps + 2):
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOL_SPECS,
            messages=messages,
        )
        usage.add(response.usage)

        text_parts = [b.text for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_parts and tool_uses:
            yield {"type": "assistant_text", "text": "\n".join(text_parts)}

        if not tool_uses or n_calls >= max_steps:
            final_text = "\n".join(text_parts)
            break

        messages.append({"role": "assistant", "content": response.content})
        result_blocks = []
        for tu in tool_uses:
            n_calls += 1
            tool_id = f"T{n_calls}"
            yield {"type": "tool_call", "id": tool_id, "name": tu.name,
                   "args": tu.input}
            result, png = run_tool(tu.name, dict(tu.input))
            tool_results[tool_id] = result
            trace.append({"id": tool_id, "name": tu.name, "args": dict(tu.input),
                          "result": result})
            yield {"type": "tool_result", "id": tool_id, "name": tu.name,
                   "result": result, "has_image": png is not None}
            content: list[dict] = [{"type": "text",
                                    "text": _serialize_result(tool_id, result)}]
            if png is not None:
                import base64
                content.append({"type": "image",
                                "source": {"type": "base64",
                                           "media_type": "image/png",
                                           "data": base64.standard_b64encode(png).decode()}})
            result_blocks.append({"type": "tool_result", "tool_use_id": tu.id,
                                  "content": content,
                                  **({"is_error": True} if "error" in result else {})})
        messages.append({"role": "user", "content": result_blocks})

    validation = citations.validate(final_text, tool_results)
    yield {
        "type": "final",
        "arm": "agent",
        "event_id": event_id,
        "answer": final_text,
        "validation": validation.to_dict(),
        "tool_trace": trace,
        "usage": usage.to_dict(),
    }


def collect(gen: Iterator[dict]) -> dict:
    """Drain a run generator and return its final event (for CLI/eval use)."""
    last = {}
    for ev in gen:
        last = ev
    return last
