"""Narrative-vs-telemetry consistency checker (OpenAI-compatible endpoint).

Step 1: extract_assertions — one forced function call turning the narrative
into atomic, typed, checkable assertions.
Step 2: verification agent — same telemetry tools as the analysis agent; must
finish by calling the submit_verdicts function with a per-assertion verdict
(supported / contradicted / unverifiable) whose evidence strings carry [claim](Tn)
citations, validated by the backend.

The eval harness scores the DERIVED overall verdict (deterministic aggregation
of per-assertion verdicts), not the model's own overall, to avoid judge noise.
"""

from __future__ import annotations

import json
from typing import Iterator

from . import citations
from .agent import (AGENT_RULES, assistant_to_message, execute_tool_calls,
                    parse_args)
from .events import store
from .llm import UsageTotal, get_client, resolve_model
from .toolspec import OPENAI_TOOLS

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

EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_assertions",
        "description": "Submit the extracted checkable assertions.",
        "parameters": {
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
                    },
                }
            },
            "required": ["assertions"],
        },
    },
}

SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_verdicts",
        "description": ("Submit your final per-assertion verdicts. Call this exactly "
                        "once, after you have gathered the evidence. This ends the "
                        "analysis."),
        "parameters": {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "assertion_id": {"type": "string"},
                            "verdict": {"type": "string",
                                        "enum": ["supported", "contradicted",
                                                 "unverifiable"]},
                            "evidence": {
                                "type": "string",
                                "description": ("1-3 sentences; every quantitative "
                                                "claim as a [claim](Tn) citation of a "
                                                "tool result"),
                            },
                        },
                        "required": ["assertion_id", "verdict", "evidence"],
                    },
                },
                "overall": {"type": "string",
                            "enum": ["consistent", "inconsistent", "uncertain"]},
                "rationale": {"type": "string"},
            },
            "required": ["verdicts", "overall", "rationale"],
        },
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


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def extract_assertions(narrative: str, model: str,
                       client) -> tuple[list[dict], UsageTotal]:
    usage = UsageTotal(model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user",
             "content": f"Extract the checkable assertions:\n---\n{narrative}\n---"},
        ],
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_assertions"}},
    )
    usage.add(response.usage)
    msg = response.choices[0].message
    if msg.tool_calls:
        args, err = parse_args(msg.tool_calls[0].function.arguments)
        if err:
            raise ValueError(f"assertion extraction returned bad JSON: {err}")
        assertions = args.get("assertions", [])
    else:  # fallback: some routes may answer in text despite tool_choice
        assertions = json.loads(_strip_fences(msg.content or ""))["assertions"]
    cleaned = []
    for i, a in enumerate(assertions, 1):
        cleaned.append({
            "id": str(a.get("id") or f"a{i}"),
            "type": a.get("type") if a.get("type") in ASSERTION_TYPES else "other",
            "text": str(a.get("text", "")).strip(),
        })
    return [a for a in cleaned if a["text"]], usage


def _valid_verdicts(raw: dict, assertions: list[dict]) -> list[dict] | None:
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return None
    ok_ids = {a["id"] for a in assertions}
    out = []
    for v in verdicts:
        if not isinstance(v, dict):
            return None
        if v.get("verdict") not in ("supported", "contradicted", "unverifiable"):
            return None
        out.append({
            "assertion_id": str(v.get("assertion_id", "")),
            "verdict": v["verdict"],
            "evidence": str(v.get("evidence", "")),
        })
    # tolerate ids the model invented as long as most map back
    mapped = sum(1 for v in out if v["assertion_id"] in ok_ids)
    return out if mapped >= max(1, len(out) // 2) else None


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
    model = resolve_model(model)
    client = get_client()
    ev = store().get(event_id)

    yield {"type": "start", "arm": "consistency", "event_id": event_id, "model": model}

    assertions, usage = extract_assertions(narrative, model, client)
    yield {"type": "assertions", "assertions": assertions}

    vehicle_note = ""
    if ev.source == "ciss" and ev.narrative_vehicle_ref:
        vehicle_note = (f" (telemetry is from vehicle {ev.narrative_vehicle_ref}; "
                        "verify assertions about that vehicle)")

    tool_results: dict[str, dict] = {}
    trace: list[dict] = []
    messages: list[dict] = [
        {"role": "system", "content": CHECK_SYSTEM},
        {"role": "user", "content": CHECK_TASK.format(
            vehicle_note=vehicle_note, narrative=narrative, event_id=event_id,
            assertions_json=json.dumps(assertions, indent=1))},
    ]
    tools = OPENAI_TOOLS + [SUBMIT_TOOL]

    n_calls = 0
    nudges = 0
    format_retried = False
    submitted: dict | None = None
    for _step in range(max_steps + 5):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=tools)
        usage.add(response.usage)
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            if nudges >= 2 or n_calls >= max_steps + 2:
                break
            nudges += 1
            messages.append(assistant_to_message(msg))
            messages.append({"role": "user",
                             "content": "Call submit_verdicts to finish."})
            continue

        messages.append(assistant_to_message(msg))
        telemetry_calls = []
        for tc in tool_calls:
            if tc.function.name == "submit_verdicts":
                args, err = parse_args(tc.function.arguments)
                verdicts = None if err else _valid_verdicts(args, assertions)
                if verdicts is None:
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": "invalid submission; call "
                                                "submit_verdicts again with the "
                                                "required fields"})
                else:
                    submitted = {"verdicts": verdicts,
                                 "overall": args.get("overall", "uncertain"),
                                 "rationale": str(args.get("rationale", ""))}
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": "verdicts recorded"})
            else:
                telemetry_calls.append(tc)
        if telemetry_calls:
            n_calls = yield from execute_tool_calls(
                telemetry_calls, messages, tool_results, trace, n_calls)
        if submitted is not None:
            # validator-in-the-loop: one re-submission if evidence is uncited
            ev_text = "\n".join(v["evidence"] for v in submitted["verdicts"])
            val = citations.validate(ev_text, tool_results)
            if (not format_retried and val.n_valid == 0 and val.n_uncited > 0
                    and tool_results):
                format_retried = True
                yield {"type": "format_retry",
                       "message": f"validator found {val.n_uncited} uncited claims "
                                  "in the evidence; requesting one re-submission"}
                messages.append({"role": "user", "content": (
                    "The citation validator rejected your evidence fields: they "
                    "contain ZERO valid [claim](Tn) citations. Call submit_verdicts "
                    "again with the SAME verdicts, but write every quantitative "
                    "claim in each evidence field as a markdown link "
                    "[claim text with the numbers](Tn) pointing at the tool result "
                    "that contains them. Bare [Tn] tags do not count.")})
                submitted = None
                continue
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
