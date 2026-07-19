"""Narrative-vs-telemetry consistency checker.

Step 1: extract_assertions — one LLM call turning the narrative into atomic,
typed, checkable assertions (structured output, guaranteed JSON).
Step 2: verification agent — same telemetry tools as the analysis agent; must
finish by calling the strict submit_verdicts tool with a per-assertion verdict
(supported / contradicted / unverifiable) whose evidence strings carry [claim](Tn)
citations, validated by the backend.

The eval harness scores the DERIVED overall verdict (deterministic aggregation
of per-assertion verdicts), not the model's own overall, to avoid judge noise.
"""

from __future__ import annotations

import json
from typing import Iterator

from . import citations
from .agent import AGENT_RULES, _serialize_result
from .events import store
from .llm import MODEL, UsageTotal, get_client
from .toolspec import TOOL_SPECS, run_tool

MAX_STEPS = 10

ASSERTION_TYPES = ["speed", "braking", "impact_direction", "impact_count",
                   "severity", "sequence", "other"]

EXTRACT_SYSTEM = """You turn accident narratives into atomic, checkable assertions \
for verification against vehicle telemetry. Each assertion is one claim that could \
independently be true or false. Type them:
- speed: a stated or implied travel speed
- braking: braking claimed to have happened (or explicitly not happened)
- impact_direction: where/from which direction the vehicle was struck or struck something
- impact_count: how many distinct impacts occurred
- severity: how severe the collision was (including "minor"/"light tap" style claims)
- sequence: temporal ordering of events (e.g. braked before impact)
- other: checkable claims outside these types
Only extract claims about the physics of the event (motion, impacts, braking, speeds, \
ordering). Ignore administrative details (names, roads, insurance, weather, injuries)."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "a1, a2, ..."},
                    "type": {"type": "string", "enum": ASSERTION_TYPES},
                    "text": {"type": "string",
                             "description": "the assertion, self-contained"},
                },
                "required": ["id", "type", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["assertions"],
    "additionalProperties": False,
}

SUBMIT_TOOL = {
    "name": "submit_verdicts",
    "description": ("Submit your final per-assertion verdicts. Call this exactly once, "
                    "after you have gathered the evidence. This ends the analysis."),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "assertion_id": {"type": "string"},
                        "verdict": {"type": "string",
                                    "enum": ["supported", "contradicted", "unverifiable"]},
                        "evidence": {
                            "type": "string",
                            "description": ("1-3 sentences; every quantitative claim as a "
                                            "[claim](Tn) citation of a tool result"),
                        },
                    },
                    "required": ["assertion_id", "verdict", "evidence"],
                    "additionalProperties": False,
                },
            },
            "overall": {"type": "string",
                        "enum": ["consistent", "inconsistent", "uncertain"]},
            "rationale": {"type": "string"},
        },
        "required": ["verdicts", "overall", "rationale"],
        "additionalProperties": False,
    },
}

CHECK_SYSTEM = f"""You are the consistency checker of Claims Desk. You receive an \
accident narrative and access to the vehicle's recorded telemetry through tools. \
Verify each provided assertion against the sensor evidence.

Verdict semantics:
- supported: telemetry positively backs the assertion (within reasonable tolerance; \
a stated speed within ~15% or ~10 km/h of the recorded one is supported).
- contradicted: telemetry positively shows the assertion is false.
- unverifiable: the available channels cannot decide it (e.g. vehicle-frame impact \
direction when IMU axis alignment is undocumented; facts about road/weather/intent).
Judge each assertion on the sensors alone, not on plausibility.

CISS events: t=0 is the impact; pre-crash channels are sparse (~2 Hz) and the EDR \
summary in get_window_info (max delta-V etc.) is citable evidence. The narrative \
describes the whole crash; the telemetry belongs to ONE vehicle (stated in the task).

Tool results are JSON prefixed with their tool_call_id ("T1", "T2", ...). Budget: \
{MAX_STEPS} tool calls; a good run needs 3-6. When done, call submit_verdicts \
exactly once — its evidence fields must follow the citation rules below.

{AGENT_RULES}"""

CHECK_TASK = """Narrative to check{vehicle_note}:
---
{narrative}
---
Assertions to verify against event {event_id}:
{assertions_json}

Verify each assertion with the tools, then call submit_verdicts."""


def extract_assertions(narrative: str, model: str | None = None) -> tuple[list[dict], UsageTotal]:
    model = model or MODEL
    client = get_client()
    usage = UsageTotal(model)
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=EXTRACT_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
        messages=[{"role": "user",
                   "content": f"Extract the checkable assertions:\n---\n{narrative}\n---"}],
    )
    usage.add(response.usage)
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["assertions"], usage


def derive_overall(verdicts: list[dict]) -> str:
    """Deterministic aggregation used for scoring."""
    vs = [v["verdict"] for v in verdicts]
    if any(v == "contradicted" for v in vs):
        return "inconsistent"
    if vs and all(v == "supported" for v in vs):
        return "consistent"
    return "uncertain"


def run_consistency_check(event_id: str, narrative: str,
                          model: str | None = None,
                          max_steps: int = MAX_STEPS) -> Iterator[dict]:
    model = model or MODEL
    client = get_client()
    ev = store().get(event_id)

    yield {"type": "start", "arm": "consistency", "event_id": event_id, "model": model}

    assertions, usage = extract_assertions(narrative, model)
    yield {"type": "assertions", "assertions": assertions}

    vehicle_note = ""
    if ev.source == "ciss" and ev.narrative_vehicle_ref:
        vehicle_note = (f" (telemetry is from vehicle {ev.narrative_vehicle_ref}; "
                        "verify assertions about that vehicle)")

    tool_results: dict[str, dict] = {}
    trace: list[dict] = []
    messages = [{"role": "user", "content": CHECK_TASK.format(
        vehicle_note=vehicle_note, narrative=narrative, event_id=event_id,
        assertions_json=json.dumps(assertions, indent=1))}]

    n_calls = 0
    submitted: dict | None = None
    for _step in range(max_steps + 3):
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=[{"type": "text", "text": CHECK_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOL_SPECS + [SUBMIT_TOOL],
            messages=messages,
        )
        usage.add(response.usage)
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            if n_calls >= max_steps:
                break
            # nudge once if the model answered in prose instead of submitting
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",
                             "content": "Call submit_verdicts to finish."})
            continue

        messages.append({"role": "assistant", "content": response.content})
        result_blocks = []
        for tu in tool_uses:
            if tu.name == "submit_verdicts":
                submitted = dict(tu.input)
                result_blocks.append({"type": "tool_result", "tool_use_id": tu.id,
                                      "content": "verdicts recorded"})
                continue
            n_calls += 1
            tool_id = f"T{n_calls}"
            yield {"type": "tool_call", "id": tool_id, "name": tu.name, "args": tu.input}
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
                                "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.standard_b64encode(png).decode()}})
            result_blocks.append({"type": "tool_result", "tool_use_id": tu.id,
                                  "content": content,
                                  **({"is_error": True} if "error" in result else {})})
        messages.append({"role": "user", "content": result_blocks})
        if submitted is not None:
            break

    if submitted is None:
        yield {"type": "error",
               "message": "checker did not submit verdicts within the step budget"}
        return

    evidence_text = "\n".join(v.get("evidence", "") for v in submitted["verdicts"])
    validation = citations.validate(evidence_text, tool_results)

    yield {
        "type": "final",
        "arm": "consistency",
        "event_id": event_id,
        "assertions": assertions,
        "verdicts": submitted["verdicts"],
        "model_overall": submitted["overall"],
        "derived_overall": derive_overall(submitted["verdicts"]),
        "rationale": submitted["rationale"],
        "validation": validation.to_dict(),
        "tool_trace": trace,
        "usage": usage.to_dict(),
    }
