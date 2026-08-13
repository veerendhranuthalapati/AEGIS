"""Prometheus metrics registry.

Single source of truth for AEGIS observability. All instrumentation helpers
live here so names and labels stay consistent across the gateway, ML, LLM,
events, incidents, tools and the background worker.

No sensitive data (bodies, tokens, keys, PII) is ever stored as a label or
observation value.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- Gateway traffic ----------------------------------------------------- #
REQUESTS_TOTAL = Counter(
    "aegis_gateway_requests_total",
    "Requests processed by the gateway",
    ["decision", "endpoint_group"],
)
REQUESTS_LATENCY = Histogram(
    "aegis_gateway_request_latency_seconds",
    "Total gateway request latency (entry to response)",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
COMPONENT_LATENCY = Histogram(
    "aegis_gateway_component_latency_seconds",
    "Per-component processing latency",
    ["component"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
BLOCKED_TOTAL = Counter(
    "aegis_blocked_requests_total", "Requests blocked by the gateway"
)

# --- Security events & incidents ----------------------------------------- #
EVENTS_TOTAL = Counter(
    "aegis_security_events_total",
    "Security events emitted",
    ["event_type", "severity"],
)
INCIDENTS_TOTAL = Counter(
    "aegis_incidents_total", "Incidents created", ["severity"]
)
INCIDENTS_OPEN = Gauge("aegis_incidents_open", "Currently open incidents")
FALSE_POSITIVE_RATE = Gauge(
    "aegis_false_positive_rate", "Reported false-positive rate (0..1)"
)

# --- ML inference -------------------------------------------------------- #
ML_PREDICTIONS_TOTAL = Counter(
    "aegis_ml_predictions_total",
    "ML prediction attempts by status (available|unavailable|disabled)",
    ["status"],
)
ML_LATENCY = Histogram(
    "aegis_ml_inference_latency_seconds",
    "ML inference latency",
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)
ML_DRIFT_ALERTS = Counter(
    "aegis_ml_drift_alerts_total",
    "ML drift monitoring alerts raised",
)

# --- LLM security analyzer ----------------------------------------------- #
LLM_REQUESTS_TOTAL = Counter(
    "aegis_llm_requests_total",
    "LLM analyzer requests",
    ["used_llm", "outcome"],
)
LLM_LATENCY = Histogram(
    "aegis_llm_latency_seconds",
    "External LLM call latency (external calls only)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 15.0, 30.0),
)
LLM_TOKENS = Histogram(
    "aegis_llm_tokens",
    "LLM token usage by kind (prompt|completion)",
    ["kind"],
    buckets=(0, 16, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
)
LLM_COST = Gauge(
    "aegis_llm_est_cost_usd",
    "Estimated cumulative external LLM spend (USD)",
)

# --- Tools / approvals --------------------------------------------------- #
TOOL_INVOCATIONS_TOTAL = Counter(
    "aegis_tool_invocations_total",
    "Tool invocation decisions (ALLOW|WARN|REQUIRE_APPROVAL|BLOCK)",
    ["decision"],
)
BLOCKED_TOOL_INVOCATIONS = Counter(
    "aegis_blocked_tool_invocations", "Tool invocations blocked by policy"
)
APPROVAL_REQUESTS = Counter(
    "aegis_approval_requests", "Approval requests raised", ["status"]
)

# --- Background worker --------------------------------------------------- #
EVENT_PROCESSING_LATENCY = Histogram(
    "aegis_event_processing_seconds",
    "Worker batch processing latency",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
CORRELATION_LATENCY = Histogram(
    "aegis_correlation_latency_seconds",
    "Incident correlation engine latency",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
EVENTS_PROCESSED = Counter(
    "aegis_events_processed_total", "Security events processed by the worker"
)


# --- Helpers ------------------------------------------------------------- #
def observe_request(decision: str, endpoint_group: str, latency_ms: float) -> None:
    REQUESTS_TOTAL.labels(decision=decision, endpoint_group=endpoint_group).inc()
    REQUESTS_LATENCY.observe(latency_ms / 1000.0)
    if decision == "BLOCK":
        BLOCKED_TOTAL.inc()


def observe_component(component: str, latency_ms: float) -> None:
    COMPONENT_LATENCY.labels(component=component).observe(latency_ms / 1000.0)


def observe_ml(status: str, latency_ms: float) -> None:
    ML_PREDICTIONS_TOTAL.labels(status=status).inc()
    if status == "available":
        ML_LATENCY.observe(latency_ms / 1000.0)


def observe_ml_drift(alert_count: int) -> None:
    if alert_count > 0:
        ML_DRIFT_ALERTS.inc(alert_count)


def observe_llm(
    used_llm: bool,
    outcome: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    LLM_REQUESTS_TOTAL.labels(used_llm=str(used_llm), outcome=outcome).inc()
    if used_llm:
        LLM_LATENCY.observe(latency_ms / 1000.0)
    if prompt_tokens:
        LLM_TOKENS.labels(kind="prompt").observe(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS.labels(kind="completion").observe(completion_tokens)


_llm_cost_total_usd = 0.0


def observe_llm_cost(usd: float) -> None:
    """Accumulate estimated external LLM spend and publish the running total."""
    global _llm_cost_total_usd
    _llm_cost_total_usd += usd
    LLM_COST.set(_llm_cost_total_usd)


def observe_tool(decision: str) -> None:
    TOOL_INVOCATIONS_TOTAL.labels(decision=decision).inc()
    if decision == "BLOCK":
        BLOCKED_TOOL_INVOCATIONS.inc()


def observe_approval(status: str) -> None:
    APPROVAL_REQUESTS.labels(status=status).inc()


def observe_security_event(event_type: str, severity: str) -> None:
    EVENTS_TOTAL.labels(event_type=event_type, severity=severity).inc()


def observe_incident(severity: str, delta_open: int) -> None:
    """Record incident lifecycle: +1 on create, -1 on resolve/close."""
    INCIDENTS_TOTAL.labels(severity=severity).inc()
    if delta_open:
        INCIDENTS_OPEN.inc(delta_open)


def observe_worker(correlation_ms: float, batch_ms: float, processed: int) -> None:
    CORRELATION_LATENCY.observe(correlation_ms / 1000.0)
    EVENT_PROCESSING_LATENCY.observe(batch_ms / 1000.0)
    if processed:
        EVENTS_PROCESSED.inc(processed)
