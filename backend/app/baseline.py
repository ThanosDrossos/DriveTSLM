"""Baseline arm: same model, no tools. Input is a well-rendered full-window
plot of every channel plus the channel legend (names, units, sampling) — a fair
plot-reading setup, deliberately not strawmanned. Its claims cannot carry
citations; the UI labels the arm accordingly."""

from __future__ import annotations

import base64
from typing import Iterator

from .events import store
from .llm import MODEL, UsageTotal, get_client
from .tools import get_window_info, render_plot

BASELINE_SYSTEM = """You are an expert automotive crash analyst. You are shown a \
rendered plot of one recorded driving event (all sensor channels) plus a channel \
legend. You have no other tools — read the plot carefully.

Give your best analysis in this markdown format, under 350 words:
**Classification**: crash / near_miss / normal_driving + rough severity.
**What happened**: 2-5 sentences with the quantitative values you can read off the plot.
**Top evidence**: 3 bullets.
**What would change my confidence**: 1-2 sentences."""


def run_baseline(event_id: str, model: str | None = None) -> Iterator[dict]:
    model = model or MODEL
    client = get_client()
    ev = store().get(event_id)

    info = get_window_info(event_id)
    legend_lines = [
        f"- {c['name']}: unit {c['unit']}, {c['sampling']}, t {c['t_start']}..{c['t_end']} s"
        for c in info["channels"]
    ]
    legend = (
        f"Event {event_id} (source: {ev.source}). {info.get('notes', '')}\n"
        "Channels:\n" + "\n".join(legend_lines)
    )

    _, png = render_plot(event_id)
    yield {"type": "start", "arm": "baseline", "event_id": event_id, "model": model}

    usage = UsageTotal(model)
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=BASELINE_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png",
                            "data": base64.standard_b64encode(png).decode()}},
                {"type": "text",
                 "text": legend + "\n\nAnalyze this event following the required format."},
            ],
        }],
    )
    usage.add(response.usage)
    answer = "\n".join(b.text for b in response.content if b.type == "text")
    yield {
        "type": "final",
        "arm": "baseline",
        "event_id": event_id,
        "answer": answer,
        "validation": None,
        "tool_trace": [],
        "usage": usage.to_dict(),
    }
