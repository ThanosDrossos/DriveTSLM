"""Anthropic tool definitions + dispatcher for the telemetry tools."""

from __future__ import annotations

from . import tools

RANGE_PROPS = {
    "t_start": {"type": "number", "description": "start of the time range in seconds (omit for window start)"},
    "t_end": {"type": "number", "description": "end of the time range in seconds (omit for window end)"},
}
CHANNELS_PROP = {
    "channels": {
        "type": "array", "items": {"type": "string"},
        "description": "channel names to include (omit for all); see get_window_info",
    }
}

TOOL_SPECS = [
    {
        "name": "get_window_info",
        "description": ("Channels, units, sampling rates, time range and source notes for an "
                        "event. For CISS events also returns the EDR summary values "
                        "(max delta-V, airbag/belt) and vehicle info. Call this first."),
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "slice_window",
        "description": ("Downsampled raw samples [t, value] for selected channels in a time "
                        "range. Downsampling keeps the sample with the largest deviation per "
                        "bucket, so spikes survive. Budgeted to ~200 numbers per call: narrow "
                        "the range or channel list for more detail."),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                **RANGE_PROPS, **CHANNELS_PROP,
                "max_points_per_channel": {"type": "integer", "minimum": 5, "maximum": 100},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "compute_stats",
        "description": ("Per-channel statistics over a time range: baseline (median), peak "
                        "deviation with timestamp, RMS, max rate of change (jerk for accel), "
                        "integrated delta-V estimate for accel axes (device frame!), integrated "
                        "rotation for gyro axes, first/last/min/max for speed-like channels, "
                        "transitions for the brake channel, crash-pulse maxima for CISS delta-V."),
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, **RANGE_PROPS, **CHANNELS_PROP},
            "required": ["event_id"],
        },
    },
    {
        "name": "detect_events",
        "description": ("Threshold-based candidate segments across all channels: impact spikes, "
                        "sustained accel/decel, high rotation rate, large net rotation, GPS/EDR "
                        "speed drops, brake applications, CISS crash-pulse impact. Every "
                        "detection states its criterion. Thresholds are documented and fixed."),
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "render_plot",
        "description": ("Render channels over a time range as a PNG (returned to you as an "
                        "image). Optional annotations draw labeled vertical lines at given "
                        "times. Use to visually inspect shapes after locating events."),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                **RANGE_PROPS, **CHANNELS_PROP,
                "annotations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"t": {"type": "number"}, "label": {"type": "string"}},
                        "required": ["t"],
                    },
                    "description": "vertical marker lines, e.g. [{\"t\": 8.1, \"label\": \"impact\"}]",
                },
            },
            "required": ["event_id"],
        },
    },
]


def run_tool(name: str, args: dict) -> tuple[dict, bytes | None]:
    """Dispatch one tool call. Returns (json_result, png_bytes_or_None).
    Errors are returned as {"error": ...} so the agent can adapt."""
    try:
        if name == "get_window_info":
            return tools.get_window_info(**args), None
        if name == "slice_window":
            return tools.slice_window(**args), None
        if name == "compute_stats":
            return tools.compute_stats(**args), None
        if name == "detect_events":
            return tools.detect_events(**args), None
        if name == "render_plot":
            meta, png = tools.render_plot(**args)
            return meta, (png or None)
        return {"error": f"unknown tool {name!r}"}, None
    except (KeyError, ValueError, TypeError) as exc:
        return {"error": str(exc)}, None
