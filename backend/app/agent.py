"""Grounded-analysis agent: OpenAI-compatible tool-use loop (KIT AI Toolbox)
with our sequential tool-call ids (T1, T2, ...) so the citation validator can
bind claims to the exact result the model saw.

The loop is a generator yielding progress events; the FastAPI SSE endpoint,
the CLI, and the eval harness all consume the same stream. The last event is
always {"type": "final", ...} or {"type": "error", ...}.

Chat-completions specifics: tool results go back as role="tool" messages
(string content only), so render_plot images are delivered in a follow-up
user message with an image_url part referencing the tool id.
"""

from __future__ import annotations

import base64
import json
from typing import Iterator

from . import citations
from .events import store
from .llm import UsageTotal, get_client, resolve_model
from .toolspec import OPENAI_TOOLS, run_tool

MAX_STEPS = 10

AGENT_RULES = """NON-NEGOTIABLE AGENT RULES (enforced by a backend validator, shown to the user):
1. CITE EVERY NUMBER. Every quantitative claim in your final answer — magnitude, \
axis/direction, timing, speed, count — must be written as a markdown-link citation \
with the CLAIM TEXT inside [ ] and the tool id inside ( ):
   RIGHT: "[GPS speed fell from 70.0 km/h to 43.0 km/h](T3) during the impact."
   RIGHT: "[peak of 5.2 g at t=8.13 s](T2)"
   WRONG: "GPS speed fell from 70.0 km/h to 43.0 km/h [T3]." — bare [T3] tags are \
NOT citations; the validator ignores them and every number counts as uncited.
Tn must be the id of the tool call whose RESULT contains the number. The validator \
checks that every number inside [ ] appears in that tool result (rounding to fewer \
digits is fine; km/h<->m/s<->mph conversions are fine). Uncited or wrongly cited \
numbers are flagged in red to the user.
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


def serialize_result(tool_id: str, result: dict) -> str:
    return json.dumps({"tool_call_id": tool_id, **result}, separators=(",", ":"))


def assistant_to_message(msg) -> dict:
    """Convert an SDK assistant message to a plain dict for the history."""
    out: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name,
                          "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return out


def parse_args(raw: str) -> tuple[dict, str | None]:
    try:
        val = json.loads(raw or "{}")
        if not isinstance(val, dict):
            return {}, f"tool arguments must be an object, got {type(val).__name__}"
        return val, None
    except json.JSONDecodeError as exc:
        return {}, f"unparseable tool arguments: {exc}"


def execute_tool_calls(tool_calls, messages: list, tool_results: dict,
                       trace: list, start_n: int):
    """Run each requested telemetry tool, append role=tool results (+ image
    follow-up), yield progress events. Returns via StopIteration.value the new
    call count."""
    n_calls = start_n
    image_parts: list[tuple[str, bytes]] = []
    for tc in tool_calls:
        n_calls += 1
        tool_id = f"T{n_calls}"
        args, arg_err = parse_args(tc.function.arguments)
        yield {"type": "tool_call", "id": tool_id, "name": tc.function.name,
               "args": args}
        if arg_err:
            result, png = {"error": arg_err}, None
        else:
            result, png = run_tool(tc.function.name, args)
        tool_results[tool_id] = result
        trace.append({"id": tool_id, "name": tc.function.name, "args": args,
                      "result": result})
        yield {"type": "tool_result", "id": tool_id, "name": tc.function.name,
               "result": result, "has_image": png is not None}
        messages.append({"role": "tool", "tool_call_id": tc.id,
                         "content": serialize_result(tool_id, result)})
        if png is not None:
            image_parts.append((tool_id, png))
    if image_parts:
        content: list[dict] = [{
            "type": "text",
            "text": "Rendered plot(s) for " + ", ".join(t for t, _ in image_parts) + ":",
        }]
        for _tid, png in image_parts:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64,"
                       + base64.standard_b64encode(png).decode()}})
        messages.append({"role": "user", "content": content})
    return n_calls


def run_grounded_analysis(event_id: str, model: str | None = None,
                          max_steps: int = MAX_STEPS) -> Iterator[dict]:
    model = resolve_model(model)
    client = get_client()
    store().get(event_id)  # raises KeyError early for unknown ids

    usage = UsageTotal(model)
    tool_results: dict[str, dict] = {}
    trace: list[dict] = []
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": TASK_PROMPT.format(event_id=event_id)},
    ]
    yield {"type": "start", "arm": "agent", "event_id": event_id, "model": model,
           "rules": AGENT_RULES}

    n_calls = 0
    final_text = ""
    for _step in range(max_steps + 2):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=OPENAI_TOOLS)
        usage.add(response.usage)
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if msg.content and tool_calls:
            yield {"type": "assistant_text", "text": msg.content}

        if not tool_calls or n_calls >= max_steps:
            final_text = msg.content or ""
            break

        messages.append(assistant_to_message(msg))
        n_calls = yield from execute_tool_calls(
            tool_calls, messages, tool_results, trace, n_calls)

    validation = citations.validate(final_text, tool_results)

    # validator-in-the-loop: one rewrite pass if the answer is effectively
    # uncited (wrong citation syntax or none at all)
    if final_text and validation.n_valid == 0 and validation.n_uncited > 0:
        yield {"type": "format_retry",
               "message": f"validator found {validation.n_uncited} uncited claims "
                          "and no valid citations; requesting one rewrite"}
        complaints = ", ".join(u["match"] for u in
                               validation.to_dict()["uncited_quantitative_claims"][:12])
        messages.append({"role": "assistant", "content": final_text})
        messages.append({"role": "user", "content": (
            "The citation validator rejected this answer: it contains ZERO valid "
            f"[claim](Tn) citations and these uncited numbers: {complaints}. "
            "Rewrite the SAME final answer, wrapping every quantitative claim as a "
            "markdown link [claim text with the numbers](Tn) pointing at the tool "
            "result that contains them. Do not call tools; output only the "
            "corrected answer.")})
        response = client.chat.completions.create(
            model=model, messages=messages, tools=OPENAI_TOOLS)
        usage.add(response.usage)
        retry_text = response.choices[0].message.content or ""
        if retry_text:
            retry_validation = citations.validate(retry_text, tool_results)
            if retry_validation.n_valid > 0:
                final_text, validation = retry_text, retry_validation
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
