"""Claims Desk CLI — everything the app does, with JSON output.

  python -m backend.cli list-events
  python -m backend.cli event <event_id>                 # evidence facts (authoring aid)
  python -m backend.cli analyze <event_id> [--arm agent|baseline|both]
  python -m backend.cli check <event_id> --narrative-id ID
  python -m backend.cli check <event_id> --text "..."
  python -m backend.cli narratives [event_id]

Progress goes to stderr; the final JSON result goes to stdout (or --json FILE).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import narratives  # noqa: E402
from app.events import store  # noqa: E402
from app.tools import compute_stats, detect_events, get_window_info  # noqa: E402


def _progress(ev: dict) -> None:
    t = ev.get("type")
    if t == "tool_call":
        print(f"  -> {ev['id']} {ev['name']}({json.dumps(ev['args'])})", file=sys.stderr)
    elif t == "tool_result":
        blob = json.dumps(ev["result"])
        print(f"  <- {ev['id']} {blob[:160]}{'...' if len(blob) > 160 else ''}",
              file=sys.stderr)
    elif t == "assertions":
        print(f"  extracted {len(ev['assertions'])} assertions", file=sys.stderr)
    elif t == "start":
        print(f"[{ev['arm']}] {ev['event_id']} on {ev['model']}", file=sys.stderr)


def _emit(result: dict, path: str | None) -> None:
    blob = json.dumps(result, indent=1)
    if path:
        Path(path).write_text(blob, encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    else:
        print(blob)


def _drain(gen) -> dict:
    last = {}
    for ev in gen:
        _progress(ev)
        last = ev
    return last


def cmd_list_events(_args) -> None:
    rows = []
    for e in store().all():
        rows.append({"event_id": e.event_id, "source": e.source, "label": e.label,
                     "channels": list(e.channels),
                     "narratives": len(narratives.for_event(e.event_id))})
    _emit({"events": rows}, None)


def cmd_event(args) -> None:
    _emit({
        "info": get_window_info(args.event_id),
        "detections": detect_events(args.event_id),
        "stats": compute_stats(args.event_id),
    }, args.json)


def cmd_analyze(args) -> None:
    from app.agent import run_grounded_analysis
    from app.baseline import run_baseline

    out = {}
    if args.arm in ("agent", "both"):
        out["agent"] = _drain(run_grounded_analysis(args.event_id, model=args.model))
    if args.arm in ("baseline", "both"):
        out["baseline"] = _drain(run_baseline(args.event_id, model=args.model))
    _emit(out, args.json)


def cmd_check(args) -> None:
    from app.consistency import run_consistency_check

    if args.narrative_id:
        n = narratives.get(args.narrative_id)
        text = n["text"]
        meta = {"narrative_id": n["narrative_id"], "ground_truth": n["ground_truth"],
                "injected_error": n["injected_error"]}
    else:
        text = args.text
        meta = {"narrative_id": None, "ground_truth": None, "injected_error": None}

    result = _drain(run_consistency_check(args.event_id, text, model=args.model))
    result["narrative_meta"] = meta
    _emit(result, args.json)


def cmd_narratives(args) -> None:
    ns = narratives.for_event(args.event_id) if args.event_id else narratives.load_all()
    _emit({"narratives": ns}, None)


def main() -> None:
    ap = argparse.ArgumentParser(prog="claims-desk")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-events").set_defaults(fn=cmd_list_events)

    p = sub.add_parser("event")
    p.add_argument("event_id")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_event)

    p = sub.add_parser("analyze")
    p.add_argument("event_id")
    p.add_argument("--arm", choices=["agent", "baseline", "both"], default="both")
    p.add_argument("--model")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("check")
    p.add_argument("event_id")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--narrative-id")
    g.add_argument("--text")
    p.add_argument("--model")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("narratives")
    p.add_argument("event_id", nargs="?")
    p.set_defaults(fn=cmd_narratives)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
