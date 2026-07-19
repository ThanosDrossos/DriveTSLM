"""OpenAI-compatible client (KIT AI Toolbox), model catalog, cost accounting.

The KIT SCC AI Toolbox exposes Azure OpenAI (ChatGPT), Google (Gemini + Claude)
and KIT-hosted models behind one OpenAI-compatible endpoint. Model ids were
retrieved live from /api/v1/models; the curated list below focuses on the last
few ChatGPT and Gemini generations (probed for tool calling + vision support).

Cost figures are PUBLIC LIST PRICES of the underlying models (USD/MTok) purely
as an order-of-magnitude estimate — KIT routes billing internally. Models with
unknown public pricing show no cost.
"""

from __future__ import annotations

import os

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://ki-toolbox.scc.kit.edu/api/v1")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "azure.gpt-5-mini")

# (input, output) USD per MTok, public list prices; None = unknown (post-2025
# releases / KIT-internal). Displayed as estimates only.
PRICES_PER_MTOK: dict[str, tuple[float, float] | None] = {
    "azure.gpt-5.6-terra": None,
    "azure.gpt-5.6-sol": None,
    "azure.gpt-5.6-luna": None,
    "azure.gpt-5.5": None,
    "azure.gpt-5.4": None,
    "azure.gpt-5.1": None,
    "azure.gpt-5": (1.25, 10.0),
    "azure.gpt-5-mini": (0.25, 2.0),
    "azure.gpt-5-nano": (0.05, 0.4),
    "google.gemini-3.5-flash": None,
    "google.gemini-3.1-flash-lite": None,
    "google.gemini-2.5-pro": (1.25, 10.0),
    "google.gemini-2.5-flash": (0.30, 2.5),
    "google.gemini-2.5-flash-lite": (0.10, 0.4),
    "google.claude-opus-4.8": (5.0, 25.0),
    "google.claude-sonnet-5": (3.0, 15.0),
    "google.claude-haiku-4.5": (1.0, 5.0),
}

CURATED_MODELS: list[dict] = [
    # ChatGPT (Azure) — latest generations first
    {"id": "azure.gpt-5.6-terra", "label": "GPT-5.6 Terra", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5.6-sol", "label": "GPT-5.6 Sol", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5.6-luna", "label": "GPT-5.6 Luna", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5.5", "label": "GPT-5.5", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5.4", "label": "GPT-5.4", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5-mini", "label": "GPT-5 mini (default)", "family": "ChatGPT (Azure)"},
    {"id": "azure.gpt-5-nano", "label": "GPT-5 nano", "family": "ChatGPT (Azure)"},
    # Gemini (Google)
    {"id": "google.gemini-3.5-flash", "label": "Gemini 3.5 Flash", "family": "Gemini (Google)"},
    {"id": "google.gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite", "family": "Gemini (Google)"},
    {"id": "google.gemini-2.5-pro", "label": "Gemini 2.5 Pro", "family": "Gemini (Google)"},
    {"id": "google.gemini-2.5-flash", "label": "Gemini 2.5 Flash", "family": "Gemini (Google)"},
    # Claude (via Google route of the toolbox)
    {"id": "google.claude-sonnet-5", "label": "Claude Sonnet 5", "family": "Claude (Google)"},
    {"id": "google.claude-opus-4.8", "label": "Claude Opus 4.8", "family": "Claude (Google)"},
    {"id": "google.claude-haiku-4.5", "label": "Claude Haiku 4.5", "family": "Claude (Google)"},
]

ALLOWED_MODEL_IDS = {m["id"] for m in CURATED_MODELS}


def resolve_model(model: str | None) -> str:
    if not model:
        return DEFAULT_MODEL
    if model not in ALLOWED_MODEL_IDS and model != DEFAULT_MODEL:
        raise ValueError(f"model {model!r} not in the curated list")
    return model


def get_client():
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and fill in your "
            "KIT AI Toolbox API key."
        )
    return OpenAI(api_key=key, base_url=BASE_URL)


class UsageTotal:
    """Accumulates chat-completions usage across the calls of one run."""

    def __init__(self, model: str):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0  # not reported by chat completions
        self.n_calls = 0

    def add(self, usage) -> None:
        if usage is None:
            return
        self.n_calls += 1
        self.input_tokens += usage.prompt_tokens or 0
        self.output_tokens += usage.completion_tokens or 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            self.cache_read_tokens += getattr(details, "cached_tokens", 0) or 0

    @property
    def cost_usd(self) -> float | None:
        prices = PRICES_PER_MTOK.get(self.model)
        if prices is None:
            return None
        p_in, p_out = prices
        return (self.input_tokens * p_in + self.output_tokens * p_out) / 1e6

    def to_dict(self) -> dict:
        cost = self.cost_usd
        return {
            "model": self.model,
            "n_api_calls": self.n_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd_estimate": round(cost, 4) if cost is not None else None,
        }
