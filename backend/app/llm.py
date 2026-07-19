"""Anthropic client, model config, and token/cost accounting."""

from __future__ import annotations

import os

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# USD per MTok (input, output). Cache reads bill ~0.1x input, writes ~1.25x.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}


def get_client():
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return anthropic.Anthropic()


class UsageTotal:
    """Accumulates usage across the calls of one run."""

    def __init__(self, model: str):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.n_calls = 0

    def add(self, usage) -> None:
        self.n_calls += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    @property
    def cost_usd(self) -> float:
        p_in, p_out = PRICES_PER_MTOK.get(self.model, (5.0, 25.0))
        return (
            self.input_tokens * p_in
            + self.output_tokens * p_out
            + self.cache_read_tokens * 0.1 * p_in
            + self.cache_creation_tokens * 1.25 * p_in
        ) / 1e6

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "n_api_calls": self.n_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd_estimate": round(self.cost_usd, 4),
        }
