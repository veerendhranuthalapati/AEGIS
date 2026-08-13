"""AEGIS ML telemetry schema — feature definitions and leakage notes.

V1 online inference uses ``REQUEST_FEATURES``.
V2 evaluation extends with route/method signals computable at request time.
"""
from __future__ import annotations

from dataclasses import dataclass

FEATURE_VERSION = "2.0"
DATASET_VERSION = "v2-controlled-local"

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

# Additional request-time features for V2 evaluation (computable online).
V2_EXTRA_FEATURES = [
    "is_llm_route",
    "method_is_write",
    "requests_last_5min",
]

V2_FEATURES = REQUEST_FEATURES + V2_EXTRA_FEATURES

# Offline-only — never used for training (label leakage risk).
LEAKAGE_FEATURES = ["status_code", "log_response_size", "scenario_id"]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    description: str
    source: str
    leakage_risk: str = "none"


FEATURE_CATALOG: list[FeatureSpec] = [
    FeatureSpec("hour_of_day", "Hour of request (0–23)", "RequestContext.timestamp", "none"),
    FeatureSpec("day_of_week", "Day of week (0=Mon)", "RequestContext.timestamp", "none"),
    FeatureSpec("log_request_size", "log1p(body bytes)", "RequestContext.body_bytes", "none"),
    FeatureSpec("query_param_count", "Number of query parameters", "RequestContext.query", "none"),
    FeatureSpec("path_depth", "Path segment count", "RequestContext.path", "none"),
    FeatureSpec("path_length", "Character length of path", "RequestContext.path", "none"),
    FeatureSpec("user_agent_length", "User-Agent header length", "RequestContext.user_agent", "none"),
    FeatureSpec("is_authenticated", "1 if JWT present", "RequestContext.actor_id", "none"),
    FeatureSpec(
        "request_rate_per_min",
        "Actor/IP requests in trailing minute",
        "behavior.collect_request_stats",
        "none",
    ),
    FeatureSpec(
        "unique_endpoints_1h",
        "Distinct endpoints in trailing hour",
        "behavior.collect_request_stats",
        "none",
    ),
    FeatureSpec(
        "auth_failures_5min",
        "401 responses from IP in 5 min",
        "behavior.collect_request_stats",
        "low — correlates with brute force",
    ),
    FeatureSpec(
        "body_has_sensitive",
        "PII/secret pattern in body",
        "find_detections(body) before ML",
        "none",
    ),
    FeatureSpec("body_entropy", "Shannon entropy of body", "RequestContext.body_text", "none"),
    FeatureSpec(
        "prompt_length",
        "Body length on LLM routes",
        "RequestContext (is_llm_prompt flag)",
        "medium — flag timing skew at V1 inference",
    ),
    FeatureSpec("tool_call_count", "Tool invocations this request", "RequestContext.extra", "medium — often 0 at inspect time"),
    FeatureSpec("new_device", "First-seen device for actor", "behavior stats", "none"),
    FeatureSpec("account_age_days", "Days since user created", "behavior stats", "none"),
    FeatureSpec(
        "endpoint_rarity",
        "1/(1+endpoint_hits) for actor",
        "behavior stats",
        "none",
    ),
    FeatureSpec(
        "payload_max_token_like",
        "Ratio of long token-like words",
        "body text heuristics",
        "none",
    ),
    FeatureSpec("is_llm_route", "1 if path matches LLM routes", "path pattern", "none"),
    FeatureSpec("method_is_write", "1 if POST/PUT/PATCH/DELETE", "HTTP method", "none"),
    FeatureSpec(
        "requests_last_5min",
        "Request count in trailing 5 minutes",
        "traffic simulator / behavior",
        "none",
    ),
    FeatureSpec(
        "status_code",
        "HTTP response status",
        "response (OFFLINE ONLY)",
        "HIGH — do not train on this",
    ),
    FeatureSpec(
        "log_response_size",
        "log1p(response bytes)",
        "response (OFFLINE ONLY)",
        "HIGH — post-outcome leakage if used in training",
    ),
]


def feature_definitions_markdown() -> str:
    lines = ["| Feature | Description | Source | Leakage risk |", "|---------|-------------|--------|--------------|"]
    for spec in FEATURE_CATALOG:
        lines.append(f"| `{spec.name}` | {spec.description} | {spec.source} | {spec.leakage_risk} |")
    return "\n".join(lines)
