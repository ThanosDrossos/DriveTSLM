"""Claims Desk API.

- DEMO_PASSWORD gate: /api/login sets an auth cookie; every other /api route
  requires it. The SPA itself is served openly; all data sits behind the gate.
- Long-running agent runs stream progress as SSE (fetch-stream consumable).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import narratives
from .agent import AGENT_RULES, run_grounded_analysis
from .baseline import run_baseline
from .consistency import run_consistency_check
from .events import store
from .llm import MODEL
from .tools import compute_stats, detect_events, get_window_info, render_plot

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")
AUTH_COOKIE = "cd_auth"


def _token() -> str:
    return hashlib.sha256(f"claims-desk::{DEMO_PASSWORD}".encode()).hexdigest()


def _authed(request: Request) -> bool:
    if not DEMO_PASSWORD:
        return True  # gate disabled (local dev without env)
    cookie = request.cookies.get(AUTH_COOKIE, "")
    return hmac.compare_digest(cookie, _token())


app = FastAPI(title="Claims Desk", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api") and path not in ("/api/login", "/api/health"):
        if not _authed(request):
            return Response(json.dumps({"detail": "locked"}), status_code=401,
                            media_type="application/json")
    return await call_next(request)


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    if not DEMO_PASSWORD:
        return {"ok": True, "gate": "disabled"}
    if not hmac.compare_digest(body.password, DEMO_PASSWORD):
        raise HTTPException(401, "wrong password")
    response.set_cookie(AUTH_COOKIE, _token(), httponly=True, samesite="lax",
                        max_age=7 * 24 * 3600)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "events": len(store().ids()), "model": MODEL,
            "gate": bool(DEMO_PASSWORD),
            "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/rules")
def rules():
    return {"model": MODEL, "rules": AGENT_RULES}


@app.get("/api/events")
def list_events():
    out = []
    for e in store().all():
        out.append({
            "event_id": e.event_id,
            "source": e.source,
            "label": e.label,
            "duration_s": round(e.t_max - e.t_min, 2),
            "channels": list(e.channels),
            "meta": e.meta,
            "n_narratives": len(narratives.for_event(e.event_id)),
        })
    return {"events": out, "model": MODEL}


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    try:
        e = store().get(event_id)
    except KeyError:
        raise HTTPException(404, f"unknown event {event_id}")
    return {
        "event_id": e.event_id,
        "source": e.source,
        "label": e.label,
        "meta": e.meta,
        "edr_summary": e.edr_summary,
        "narrative_vehicle_ref": e.narrative_vehicle_ref,
        "info": get_window_info(event_id),
        "detections": detect_events(event_id),
        "stats": compute_stats(event_id),
        "narratives": narratives.for_event(event_id),
    }


@app.get("/api/events/{event_id}/plot.png")
def event_plot(event_id: str, t_start: float | None = None,
               t_end: float | None = None, annotate: bool = True):
    try:
        annotations = None
        if annotate:
            det = detect_events(event_id)
            seen = set()
            annotations = []
            for d in det["detections"][:8]:
                t = d.get("peak_t", d.get("t", d.get("t_start")))
                if t is not None and t not in seen:
                    seen.add(t)
                    annotations.append({"t": t, "label": d["type"]})
        meta, png = render_plot(event_id, t_start=t_start, t_end=t_end,
                                annotations=annotations)
        if not png:
            raise HTTPException(400, str(meta))
        return Response(png, media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})
    except KeyError:
        raise HTTPException(404, f"unknown event {event_id}")


def _sse(gen):
    def stream():
        try:
            for ev in gen:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/analyze/{event_id}")
def analyze(event_id: str, arm: str = "agent"):
    if event_id not in store().ids():
        raise HTTPException(404, f"unknown event {event_id}")
    if arm == "baseline":
        return _sse(run_baseline(event_id))
    return _sse(run_grounded_analysis(event_id))


class CheckBody(BaseModel):
    narrative_id: str | None = None
    text: str | None = None


@app.post("/api/check/{event_id}")
def check(event_id: str, body: CheckBody):
    if event_id not in store().ids():
        raise HTTPException(404, f"unknown event {event_id}")
    if body.narrative_id:
        text = narratives.get(body.narrative_id)["text"]
    elif body.text:
        text = body.text
    else:
        raise HTTPException(422, "narrative_id or text required")
    return _sse(run_consistency_check(event_id, text))


@app.get("/api/narratives")
def list_narratives(event_id: str | None = None):
    ns = narratives.for_event(event_id) if event_id else narratives.load_all()
    return {"narratives": ns}


@app.get("/api/results")
def results():
    summary = ROOT / "eval" / "results" / "summary.json"
    if not summary.exists():
        return {"available": False}
    return {"available": True,
            "summary": json.loads(summary.read_text(encoding="utf-8"))}


# ---- static SPA (must come last) ----
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
