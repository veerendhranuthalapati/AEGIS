"""Feature engineering for ML models.

Two feature sets exist:

* ``REQUEST_FEATURES`` — computable at request time (used online).
* ``FULL_FEATURES`` — everything, including post-request outcome signals
  (used for offline training/evaluation only).

Synthetic and real telemetry are converted through the same functions so the
pipeline is consistent.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

REQUEST_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "log_request_size",
    "query_param_count",
    "path_depth",
    "path_length",
    "user_agent_length",
    "is_authenticated",
    "request_rate_per_min",
    "unique_endpoints_1h",
    "auth_failures_5min",
    "body_has_sensitive",
    "body_entropy",
    "prompt_length",
    "tool_call_count",
    "new_device",
    "account_age_days",
    "endpoint_rarity",
    "payload_max_token_like",
]

# Response-derived features only used during offline training/eval.
RESPONSE_FEATURES = ["status_code", "log_response_size"]

FULL_FEATURES = REQUEST_FEATURES + RESPONSE_FEATURES


def _entropy(text: str | None) -> float:
    if not text:
        return 0.0
    if len(text) > 20_000:
        text = text[:20_000]
    counts: dict[int, int] = {}
    for char in text:
        counts[ord(char)] = counts.get(ord(char), 0) + 1
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _token_like_ratio(text: str | None) -> float:
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    return sum(1 for w in words if len(w) >= 32) / len(words)


def features_from_dict(row: dict[str, Any]) -> np.ndarray:
    """Build a feature vector from a dict (used by dataset + inference)."""
    return np.array([float(row.get(name, 0.0) or 0.0) for name in REQUEST_FEATURES], dtype=np.float64)


def features_from_request(ctx, stats: dict) -> dict[str, float]:
    """Compute request-time features from a gateway context."""
    body_text = ctx.body_text or ""
    rate = float(stats.get("request_rate_per_min", 0.0))
    return {
        "hour_of_day": float(ctx.timestamp.hour),
        "day_of_week": float(ctx.timestamp.weekday()),
        "log_request_size": math.log1p(ctx.body_bytes),
        "query_param_count": float(len(ctx.query_params())),
        "path_depth": float(len([p for p in ctx.path.split("/") if p])),
        "path_length": float(len(ctx.path)),
        "user_agent_length": float(len(ctx.user_agent or "")),
        "is_authenticated": 1.0 if ctx.actor_id else 0.0,
        "request_rate_per_min": rate,
        "unique_endpoints_1h": float(stats.get("unique_endpoints_1h", 0)),
        "auth_failures_5min": float(stats.get("auth_failures_5min", 0)),
        "body_has_sensitive": 1.0 if ctx.extra.get("has_sensitive") else 0.0,
        "body_entropy": round(_entropy(body_text), 4),
        "prompt_length": float(len(body_text)) if ctx.extra.get("is_llm_prompt") else 0.0,
        "tool_call_count": float(ctx.extra.get("tool_call_count", 0)),
        "new_device": 1.0 if stats.get("new_device") else 0.0,
        "account_age_days": float(stats.get("account_age_days", 0)),
        "endpoint_rarity": float(stats.get("endpoint_rarity", 1.0)),
        "payload_max_token_like": round(_token_like_ratio(body_text), 4),
    }
