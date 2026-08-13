"""Gateway service: synchronous request inspection, forwarding, response
security, and event production.

Flow:
  1. build context
  2. deterministic rules
  3. behavioral stats
  4. ML inference
  5. LLM scanning (prompt routes)
  6. risk aggregation
  7. policy evaluation
  8. decision (allow / warn / review / block)
  9. forward to upstream
  10. response inspection + redaction
  11. persist telemetry + security events
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.redact import redact_text
from app.gateway.models import RequestContext, UpstreamResponse
from app.metrics import observe_component
from app.ml.inference import MlInferenceService, MlPrediction
from app.models import ApiRequest
from app.policies.engine import PolicyEngine
from app.security.api.rules import ApiRulesEngine
from app.security.base import Finding
from app.security.llm.output import scan_output
from app.security.llm.scanner import LlmScanner
from app.security.risk.engine import RiskAssessment, RiskInput, assess_risk
from app.services.behavior import collect_request_stats
from app.services.ratelimit import check_rate_limit

logger = structlog.get_logger("aegis.gateway")

EVENT_TYPE_BY_RULE: dict[str, str] = {
    "API-001": "OVERSIZED_REQUEST",
    "API-002": "MALFORMED_REQUEST",
    "API-003": "HTTP_SMUGGLING",
    "API-004": "METHOD_ANOMALY",
    "API-005": "PATH_TRAVERSAL",
    "API-006": "SQLI_INDICATOR",
    "API-007": "CMD_INJ_INDICATOR",
    "API-008": "SSRF_INDICATOR",
    "API-009": "XXE_INDICATOR",
    "API-010": "HEADER_SPOOFING",
    "API-011": "SCANNER_UA",
    "API-012": "PARAMETER_POLLUTION",
    "API-013": "API_RATE_ABUSE",
    "API-014": "AUTH_FAILURE_BURST",
    "API-015": "API_ENUMERATION",
    "API-016": "BOLA_ATTEMPT",
    "LLM-001": "PROMPT_INJECTION",
    "LLM-002": "SYSTEM_PROMPT_EXTRACTION",
    "LLM-003": "JAILBREAK_ATTEMPT",
    "LLM-004": "INSTRUCTION_OVERRIDE",
    "LLM-005": "SENSITIVE_EXTRACTION",
    "LLM-006": "TOOL_MANIPULATION",
    "LLM-007": "SUSPICIOUS_FETCH",
    "LLM-008": "OBFUSCATION_INSTRUCTION",
    "LLM-009": "OBFUSCATED_PAYLOAD",
}

_SEVERITY_FOR_EVENT = {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH", "CRITICAL": "CRITICAL"}

LLM_PATHS = ("/ai/", "/llm/", "/chat", "/completions", "/embeddings")
ADMIN_PATHS = ("/admin",)
# Resource paths where the id in the path is the actor's subject id, so the
# gateway can verify ownership directly. Other resource paths (orders,
# customers, payments) cannot be ownership-verified without upstream data;
# they are left to upstream authorization to avoid false-positive blocks.
SUBJECT_ID_RESOURCE_PATHS = ("/api/users",)
# Paths where a subject-scoped id may appear in query parameters.
_BOLA_QUERY_RESOURCE_PATHS = ("/api/users", "/api/orders")
_BOLA_QUERY_KEYS = ("user_id", "id", "owner_id", "subject_id", "resource_id")

# Global collection endpoints that should only be accessible to privileged
# subjects (admin/operator). The gateway cannot verify per-object ownership
# for these, so non-privileged access is blocked pre-forward.
PRIVILEGED_ONLY_COLLECTIONS = ("/api/customers", "/api/payments")

# Resource paths where a returned object carries an owner field that can be
# compared against the authenticated subject's identity post-forward.
RESOURCE_OWNER_KEYS = {"/api/orders": "user_id"}


@dataclass
class GatewayResult:
    decision: str  # ALLOW | WARN | REQUIRE_REVIEW | BLOCK
    risk: RiskAssessment
    findings: list[Finding] = field(default_factory=list)
    policy_results: list = field(default_factory=list)
    ml_prediction: MlPrediction | None = None
    http_status: int = 200
    reason: str | None = None
    response_actions: list = field(default_factory=list)
    correlation_key: str | None = None
    approved_forward: bool = False
    redacted_response: bool = False
    rate_limited: bool = False


def normalize_endpoint(path: str) -> str:
    """Replace numeric ids so stats group by route, not by object id."""
    parts = path.split("/")
    out: list[str] = []
    for part in parts:
        if part.isdigit() or (part.startswith(":") and part[1:].isdigit()):
            out.append(":id")
        else:
            out.append(part)
    return "/".join(out) or "/"


def is_llm_path(path: str) -> bool:
    return any(seg in path for seg in LLM_PATHS)


def uses_llm_provider(path: str, method: str) -> bool:
    """POST chat/completion routes invoke the configured LLM provider."""
    if method != "POST":
        return False
    return path.endswith("/ai/chat") or path.endswith("/llm/completions") or "/ai/chat" in path


_shared_client: httpx.AsyncClient | None = None
_shared_client_lock = asyncio.Lock()


async def _shared_http_client(base_url: str, timeout: float) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        async with _shared_client_lock:
            if _shared_client is None:
                _shared_client = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=timeout,
                    follow_redirects=False,
                )
    return _shared_client


class GatewayService:
    def __init__(
        self,
        session: AsyncSession,
        settings=None,
        ml_service: MlInferenceService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._rules = ApiRulesEngine(max_request_bytes=self._settings.max_request_body_bytes)
        self._ml = ml_service or MlInferenceService(settings)
        self._client: httpx.AsyncClient | None = None
        self._policy_engine = PolicyEngine(session)

    async def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = await _shared_http_client(
                self._settings.upstream_base_url,
                self._settings.upstream_timeout_seconds,
            )
        return self._client

    # ------------------------------------------------------------------ #
    async def inspect_and_decide(self, ctx: RequestContext) -> GatewayResult:
        _t0 = time.perf_counter()
        stats = await collect_request_stats(
            self._session,
            actor_id=ctx.actor_id,
            source_ip=ctx.source_ip,
            current_endpoint=ctx.endpoint,
        )
        observe_component("stats", (time.perf_counter() - _t0) * 1000)

        # Rate limit check
        _t1 = time.perf_counter()
        if await self._rate_limit(ctx, stats) is False:
            observe_component("rate_limit", (time.perf_counter() - _t1) * 1000)
            return GatewayResult(
                decision="BLOCK",
                risk=RiskAssessment(score=70.0, level="HIGH", reasons=["Rate limit exceeded"]),
                http_status=429,
                reason="Rate limit exceeded",
                rate_limited=True,
            )
        observe_component("rate_limit", (time.perf_counter() - _t1) * 1000)

        findings: list[Finding] = []

        # --- 1. deterministic rules ---
        _t2 = time.perf_counter()
        rules_findings = self._rules.inspect(ctx, stats)
        findings += rules_findings
        observe_component("rules", (time.perf_counter() - _t2) * 1000)

        # --- 2. route-aware identity checks ---
        _t3 = time.perf_counter()
        findings += self._route_checks(ctx)
        observe_component("route_checks", (time.perf_counter() - _t3) * 1000)

        # --- 3. ML anomaly detection ---
        _t4 = time.perf_counter()
        ml_prediction = await self._ml.predict(self._session, ctx, stats)
        observe_component("ml", (time.perf_counter() - _t4) * 1000)
        if ml_prediction.available and (ml_prediction.is_anomaly):
            findings.append(
                Finding(
                    rule_id="ML-001",
                    name="Machine-learning anomaly",
                    severity="MEDIUM",
                    score=0.6,
                    reasons=[f"Anomaly score {ml_prediction.anomaly_score}"],
                    mitre=["T1499"],
                    source="ml",
                    details={
                        "anomaly_score": ml_prediction.anomaly_score,
                        "threat_probability": ml_prediction.threat_probability,
                    },
                )
            )

        # --- 4. LLM scanning for prompt routes ---
        _t5 = time.perf_counter()
        llm_findings: list[Finding] = []
        if is_llm_path(ctx.path):
            llm_findings = LlmScanner().scan(ctx.body_text)
            findings += llm_findings
            ctx.extra["is_llm_prompt"] = True
            # optional external analyzer on higher risk
            if ml_prediction.threat_probability >= 0.7 and llm_findings:
                from app.security.llm.analyzer import get_shared_analyzer

                analyzer = get_shared_analyzer()
                result = await analyzer.analyze(
                    ctx.body_text, actor_key=ctx.actor_id or ctx.source_ip
                )
                if result.label != "benign":
                    findings.append(
                        Finding(
                            rule_id="LLM-100",
                            name=f"LLM analyzer: {result.label}",
                            severity="HIGH" if result.confidence >= 0.7 else "MEDIUM",
                            score=0.7 if result.confidence >= 0.7 else 0.4,
                            reasons=[result.reason],
                            mitre=["T1027"],
                            source="llm",
                            details={"label": result.label, "confidence": result.confidence},
                        )
                    )
        observe_component("llm", (time.perf_counter() - _t5) * 1000)

        # --- 5. risk aggregation ---
        _t6 = time.perf_counter()
        behavior_signals = {
            "request_rate_ratio": stats.get("request_rate_ratio", 0.0),
            "auth_failures_5min": stats.get("auth_failures_5min", 0),
            "new_device": stats.get("new_device", False),
            "geo_change": stats.get("geo_change", False),
        }
        attack_history = 0.0
        if ctx.actor_id:
            from app.models import Incident

            _hist = await self._session.execute(
                select(Incident.id).where(
                    Incident.attacker_key == (ctx.actor_id or ctx.source_ip)
                ).limit(1)
            )
            if _hist.first() is not None:
                attack_history = 0.5

        risk_input = RiskInput(
            findings=findings,
            ml_anomaly_score=ml_prediction.anomaly_score if ml_prediction else 0.0,
            ml_threat_probability=ml_prediction.threat_probability if ml_prediction else 0.0,
            ml_available=bool(ml_prediction and ml_prediction.available),
            behavior=behavior_signals,
            data_sensitivity=float(ctx.extra.get("sensitivity_score", 0.0)),
            attack_history=attack_history,
        )
        risk = assess_risk(risk_input)
        observe_component("risk", (time.perf_counter() - _t6) * 1000)

        # --- 6. policy evaluation ---
        _t7 = time.perf_counter()
        policy_context = {
            "actor": {
                "id": ctx.actor_id,
                "username": ctx.actor_username,
                "role": ctx.actor_role,
                "permissions": ctx.actor_permissions or [],
            },
            "source_ip": ctx.source_ip,
            "endpoint": ctx.endpoint,
            "path": ctx.path,
            "method": ctx.method,
            "risk_score": risk.score,
            "risk_level": risk.level,
            "request_id": ctx.request_id,
            "auth_method": ctx.auth_method,
        }
        policy_action, policy_results, _ = await self._policy_engine.evaluate_all(policy_context)
        observe_component("policy", (time.perf_counter() - _t7) * 1000)

        # --- 7. decision resolution (fail closed) ---
        _HARD_BLOCK_RULE_IDS = {
            "API-005",  # path traversal
            "API-006",  # SQL injection
            "API-007",  # command injection
            "API-008",  # SSRF
            "API-009",  # XXE
            "API-016",  # BOLA/IDOR
            "API-017",  # admin probing
        }
        deterministic_attack = any(f.rule_id in _HARD_BLOCK_RULE_IDS for f in findings)
        llm_high = is_llm_path(ctx.path) and any(
            f.severity == "HIGH" and f.source == "llm" for f in findings
        )
        if (
            policy_action == "BLOCK"
            or risk.level == "CRITICAL"
            or deterministic_attack
        ):
            decision = "BLOCK"
        elif policy_action == "REQUIRE_REVIEW" or risk.level == "HIGH" or llm_high:
            decision = "REQUIRE_REVIEW"
        elif policy_action == "WARN" or risk.level == "MEDIUM":
            decision = "WARN"
        else:
            decision = "ALLOW"

        response_actions: list = []
        for pr in policy_results:
            if pr.matched:
                response_actions.extend(pr.response_actions)

        observe_component("inspect", (time.perf_counter() - _t0) * 1000)
        return GatewayResult(
            decision=decision,
            risk=risk,
            findings=findings,
            policy_results=[r.to_dict() for r in policy_results],
            ml_prediction=ml_prediction,
            http_status=403 if decision == "BLOCK" else (202 if decision == "REQUIRE_REVIEW" else 200),
            response_actions=response_actions,
            correlation_key=ctx.actor_id or ctx.source_ip or ctx.request_id,
        )

    # ------------------------------------------------------------------ #
    def _route_checks(self, ctx: RequestContext) -> list[Finding]:
        """Route-aware checks: admin probing and BOLA resource ownership."""
        findings: list[Finding] = []

        if any(ctx.path.startswith(admin) for admin in ADMIN_PATHS):
            if ctx.actor_role not in ("admin", "operator"):
                findings.append(
                    Finding(
                        rule_id="API-017",
                        name="Admin endpoint probing",
                        severity="HIGH",
                        score=0.7,
                        reasons=["Non-privileged subject accessed admin path"],
                        mitre=["T1078", "T1083"],
                        details={"path": ctx.path},
                    )
                )

        privileged = ctx.actor_role in ("admin", "operator")

        for collection in PRIVILEGED_ONLY_COLLECTIONS:
            if ctx.path.startswith(collection) and not privileged:
                findings.append(
                    Finding(
                        rule_id="API-016",
                        name="BOLA/IDOR access attempt",
                        severity="HIGH",
                        score=0.9,
                        reasons=[
                            f"Non-privileged subject accessed collection endpoint {collection}"
                        ],
                        mitre=["T1078", "T1530"],
                        details={"resource": collection},
                    )
                )
                break

        def _bola(resource: str, resource_id: str) -> bool:
            owned_by_actor = (
                ctx.actor_subject_id is not None
                and resource_id.isdigit()
                and int(resource_id) == ctx.actor_subject_id
            )
            if (
                ctx.actor_id
                and resource_id.isdigit()
                and not owned_by_actor
                and not privileged
            ):
                findings.append(
                    Finding(
                        rule_id="API-016",
                        name="BOLA/IDOR access attempt",
                        severity="HIGH",
                        score=0.9,
                        reasons=[
                            f"Subject {ctx.actor_id} accessed resource {resource}/{resource_id} "
                            "owned by another subject"
                        ],
                        mitre=["T1078", "T1083"],
                        details={"resource": resource, "resource_id": resource_id},
                    )
                )
                return True
            return False

        for resource in SUBJECT_ID_RESOURCE_PATHS:
            if ctx.path.startswith(resource):
                parts = ctx.path.split("/")
                # /api/users/{id} or /api/users/{id}/...
                if len(parts) >= 4:
                    _bola(resource, parts[3])
                # /api/users?user_id=3 or /api/users?...&id=3
                if ctx.query_string:
                    params = urllib.parse.parse_qs(ctx.query_string)
                    for key in _BOLA_QUERY_KEYS:
                        for raw in params.get(key, []):
                            if _bola(resource, raw):
                                break

        for resource in _BOLA_QUERY_RESOURCE_PATHS:
            if resource in SUBJECT_ID_RESOURCE_PATHS:
                continue
            if ctx.path.startswith(resource) and ctx.query_string:
                params = urllib.parse.parse_qs(ctx.query_string)
                for key in _BOLA_QUERY_KEYS:
                    for raw in params.get(key, []):
                        if _bola(resource, raw):
                            break
        return findings

    # ------------------------------------------------------------------ #
    def ownership_violation(
        self, ctx: RequestContext, upstream: UpstreamResponse
    ) -> Finding | None:
        """Post-forward ownership verification for owner-keyed resource paths.

        Returns a BOLA finding when a non-privileged subject receives a
        resource owned by a different subject.
        """
        privileged = ctx.actor_role in ("admin", "operator")
        if privileged or ctx.actor_id is None or ctx.actor_subject_id is None:
            return None
        if upstream is None or upstream.body_json is None:
            return None
        if not isinstance(upstream.body_json, dict):
            return None
        for prefix, owner_key in RESOURCE_OWNER_KEYS.items():
            if not ctx.path.startswith(prefix):
                continue
            raw_owner = upstream.body_json.get(owner_key)
            if raw_owner is None:
                return None
            try:
                owner = int(raw_owner)
            except (TypeError, ValueError):
                return None
            if owner != ctx.actor_subject_id:
                return Finding(
                    rule_id="API-016",
                    name="BOLA/IDOR access attempt",
                    severity="HIGH",
                    score=0.9,
                    reasons=[
                        f"Subject {ctx.actor_id} accessed {ctx.path} owned by "
                        f"another subject (owner {owner})"
                    ],
                    mitre=["T1078", "T1530"],
                    details={
                        "resource": ctx.path,
                        "owner_key": owner_key,
                        "resource_id": str(raw_owner),
                    },
                )
            return None
        return None

    # ------------------------------------------------------------------ #
    async def _rate_limit(self, ctx: RequestContext, stats: dict) -> bool:
        limit = (
            self._settings.gateway_rate_limit_auth_per_min
            if ctx.actor_id
            else self._settings.gateway_rate_limit_anon_per_min
        )
        key = f"gw:{ctx.actor_id or ctx.source_ip}:{ctx.endpoint}"
        allowed, _, _ = await check_rate_limit(
            self._session, key=key, limit=limit, window_seconds=60
        )
        return allowed

    # ------------------------------------------------------------------ #
    async def forward(self, ctx: RequestContext) -> UpstreamResponse:
        client = await self._http_client()
        url = ctx.path + (f"?{ctx.query_string}" if ctx.query_string else "")
        headers = {
            k: v
            for k, v in ctx.headers.items()
            if k
            not in {
                "host",
                "content-length",
                "transfer-encoding",
                "connection",
                "x-aegis-decision",
            }
        }
        start = time.perf_counter()
        content = ctx.body_text.encode("utf-8") if ctx.body_text is not None else None
        resp = await client.request(
            ctx.method,
            url,
            headers=headers,
            content=content,
        )
        latency = (time.perf_counter() - start) * 1000
        observe_component("forward", latency)
        body = resp.content.decode("utf-8", errors="replace")
        body_json: Any = None
        try:
            body_json = json.loads(body) if body else None
        except (json.JSONDecodeError, ValueError):
            body_json = None
        return UpstreamResponse(
            status_code=resp.status_code,
            body_text=body,
            body_json=body_json,
            headers=dict(resp.headers),
            bytes_size=len(resp.content),
            latency_ms=latency,
        )

    # ------------------------------------------------------------------ #
    async def invoke_llm(self, ctx: RequestContext) -> UpstreamResponse:
        """Call the configured LLM provider after input security passes."""
        from app.llm.base import LLMProviderError
        from app.llm.factory import get_llm_provider
        from app.llm.prompt import parse_chat_request
        from app.llm.tool_calls import inspect_llm_tool_calls

        provider = get_llm_provider()
        chat_req = parse_chat_request(
            ctx.body_text,
            ctx.body_json,
            default_model=self._settings.llm_model or "mock-llm",
            max_tokens=self._settings.llm_max_output_tokens,
        )
        start = time.perf_counter()
        try:
            completion = await provider.chat_completion(
                chat_req,
                actor_key=ctx.actor_id or ctx.source_ip,
            )
        except LLMProviderError as exc:
            latency = (time.perf_counter() - start) * 1000
            observe_component("forward", latency)
            status = 503 if exc.code in ("missing_key", "provider_error", "timeout") else 429
            if exc.code == "malformed_response":
                status = 502
            body = json.dumps(
                {
                    "error": exc.code,
                    "message": str(exc),
                    "provider": provider.name,
                    "note": "Deterministic AEGIS security remains active; LLM unavailable.",
                }
            )
            return UpstreamResponse(
                status_code=status,
                body_text=body,
                body_json=json.loads(body),
                headers={"content-type": "application/json"},
                bytes_size=len(body),
                latency_ms=latency,
            )

        payload = completion.to_gateway_json()
        ctx.extra["tool_call_count"] = len(completion.tool_calls)

        if completion.tool_calls:
            inspections = await inspect_llm_tool_calls(
                self._session,
                ctx,
                completion.tool_calls,
                max_depth=self._settings.llm_max_tool_call_depth,
            )
            blocked = [i for i in inspections if i.blocked]
            payload["aegis_tool_inspection"] = [
                {
                    "tool": i.tool_name,
                    "decision": i.decision,
                    "risk_score": i.risk_score,
                    "reasons": i.reasons[:5],
                }
                for i in inspections
            ]
            if blocked:
                payload["aegis_tool_blocked"] = True
                payload["choices"][0]["message"]["content"] = (
                    "Tool execution blocked by AEGIS security policy."
                )
                payload["choices"][0]["message"].pop("tool_calls", None)

        body_text = json.dumps(payload)
        latency = (time.perf_counter() - start) * 1000
        observe_component("forward", latency)
        return UpstreamResponse(
            status_code=200,
            body_text=body_text,
            body_json=payload,
            headers={"content-type": "application/json"},
            bytes_size=len(body_text.encode("utf-8")),
            latency_ms=latency,
        )

    # ------------------------------------------------------------------ #
    def inspect_response(self, ctx: RequestContext, upstream: UpstreamResponse) -> UpstreamResponse:
        """Inspect and optionally redact upstream response content."""
        if upstream.body_text is None:
            return upstream
        if self._settings.max_response_body_bytes and upstream.bytes_size > self._settings.max_response_body_bytes:
            logger.warning(
                "gateway.oversized_response",
                request_id=ctx.request_id,
                size=upstream.bytes_size,
            )
        scan = scan_output(upstream.body_text)
        if scan.redacted_text != upstream.body_text:
            redacted = upstream
            redacted.body_text = scan.redacted_text
            if scan.detections and upstream.body_json is not None:
                redacted.body_json = None
            redacted.headers = {**upstream.headers, "x-aegis-redacted": "true"}
            redacted.bytes_size = len(scan.redacted_text)
            ctx.extra["response_sensitivity"] = scan.sensitivity_score
            ctx.extra["response_redacted"] = True
            return redacted
        ctx.extra["response_sensitivity"] = scan.sensitivity_score
        ctx.extra["response_redacted"] = False
        return upstream

    # ------------------------------------------------------------------ #
    async def persist(
        self,
        ctx: RequestContext,
        result: GatewayResult,
        upstream: UpstreamResponse | None,
    ) -> None:
        _t0 = time.perf_counter()
        record = ApiRequest(
            request_id=ctx.request_id,
            actor_id=ctx.actor_id,
            session_id=ctx.session_id,
            source_ip=ctx.source_ip,
            method=ctx.method,
            path=ctx.path,
            endpoint=ctx.endpoint,
            query_string=redact_text(ctx.query_string)[0] if ctx.query_string else None,
            status_code=upstream.status_code if upstream else result.http_status,
            request_size=ctx.body_bytes,
            response_size=upstream.bytes_size if upstream else 0,
            latency_ms=upstream.latency_ms if upstream else 0.0,
            user_agent=ctx.user_agent,
            device_id=ctx.device_id,
            auth_method=ctx.auth_method,
            upstream=self._settings.upstream_base_url if upstream else None,
            decision=result.decision,
            risk_score=result.risk.score,
            reasons=result.risk.reasons[:20],
            tool_call_count=int(ctx.extra.get("tool_call_count", 0)),
            country=ctx.country,
        )
        self._session.add(record)
        await self._session.flush()

        # Emit security events for significant findings
        from app.services.events import create_security_event

        for finding in result.findings:
            if finding.severity not in ("MEDIUM", "HIGH", "CRITICAL"):
                continue
            event_type = EVENT_TYPE_BY_RULE.get(finding.rule_id, "DETECTION")
            await create_security_event(
                self._session,
                event_type=event_type,
                severity=finding.severity,
                actor_id=ctx.actor_id,
                source_ip=ctx.source_ip,
                endpoint=ctx.endpoint,
                method=ctx.method,
                risk_score=result.risk.score,
                decision=result.decision,
                reasons=finding.reasons,
                details=finding.details,
                detection_source=finding.source,
                model_version=(
                    self._settings.ml_model_dir if finding.source == "ml" else None
                ),
                policy_version=None,
                correlation_key=result.correlation_key,
                mitre_techniques=finding.mitre,
            )

        if result.decision == "BLOCK":
            await create_security_event(
                self._session,
                event_type="POLICY_BLOCK",
                severity="HIGH",
                actor_id=ctx.actor_id,
                source_ip=ctx.source_ip,
                endpoint=ctx.endpoint,
                method=ctx.method,
                risk_score=result.risk.score,
                decision="BLOCK",
                reasons=result.risk.reasons[:20],
                detection_source="policy",
                correlation_key=result.correlation_key,
                mitre_techniques=["T1499"],
            )
        await self._session.commit()
        observe_component("persist", (time.perf_counter() - _t0) * 1000)

    async def close(self) -> None:
        # The HTTP client is shared process-wide so connections are reused
        # across requests; it is closed only at process shutdown.
        return None
