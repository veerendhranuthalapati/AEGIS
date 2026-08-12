"""Deterministic API security rules.

These rules produce ``Finding`` objects from request metadata, headers and
body. They are the first, fast layer of the detection pipeline. Statistical
and ML layers run afterwards — this engine is intentionally not the only
source of truth.
"""
from __future__ import annotations

import ipaddress
import re

from app.gateway.models import RequestContext
from app.security.api.decode import inspection_variants
from app.security.base import Finding, SEVERITY_WEIGHT

_SQLI_PATTERNS = [
    re.compile(r"\bunion\s+(all\s+)?select\b", re.IGNORECASE),
    re.compile(r"\bor\s+['\"]?\s*1\s*=\s*1\b", re.IGNORECASE),
    re.compile(r"['\"]\s*or\s*['\"]\s*=\s*['\"]", re.IGNORECASE),
    re.compile(r"\bsleep\s*\(\s*\d+\s*\)", re.IGNORECASE),
    re.compile(r"\bpg_sleep\s*\(", re.IGNORECASE),
    re.compile(r"\bbenchmark\s*\(", re.IGNORECASE),
    re.compile(r"\bxp_cmdshell\b", re.IGNORECASE),
    re.compile(r"\binformation_schema\b", re.IGNORECASE),
    re.compile(r";\s*drop\s+table\b", re.IGNORECASE),
    re.compile(r"\b(or|and)\s+\d+\s*=\s*\d+\b", re.IGNORECASE),
    re.compile(r"'\s*(or|and)\s+['\"0-9]", re.IGNORECASE),
]

_CMD_INJ_PATTERNS = [
    re.compile(r"(^|[;&|])\s*(id|whoami|pwd)\b", re.IGNORECASE),
    re.compile(r"(^|[;&|])\s*(cat|more|type)\s+(/etc/passwd|/etc/shadow|/etc/hosts)", re.IGNORECASE),
    re.compile(r"\b(?:wget|curl)\s+https?://", re.IGNORECASE),
    re.compile(r"\b(?:cmd\.exe|powershell|powershell\.exe|/bin/sh|/bin/bash)\b", re.IGNORECASE),
    re.compile(r"\$\([^)]+\)|\`[^\`]+\`", re.IGNORECASE),
    re.compile(r"base64\s*-d\b", re.IGNORECASE),
    re.compile(r"%0a|%0d|%00", re.IGNORECASE),
    # Shell substitution that replaces whitespace (${IFS} cat /etc/passwd) or
    # injects an interpreter through env vars, followed by a command word.
    re.compile(
        r"\$\{(?:IFS|BASH_ENV|ENV|PS4|LD_PRELOAD|LD_LIBRARY_PATH|PATH|HOME|SHELL)\}"
        r"\s*(?:[;&|]|\s)*(?:cat|sh|bash|python|perl|nc|ncat|wget|curl|id|whoami|rm|ls|chmod|touch)\b",
        re.IGNORECASE,
    ),
]

_SSRF_HOSTS = re.compile(
    r"(?:\b(?:localhost|0\.0\.0\.0)\b"
    r"|\b127\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    r"|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    r"|\b192\.168\.\d{1,3}\.\d{1,3}\b"
    r"|\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"
    r"|\b169\.254\.\d{1,3}\.\d{1,3}\b"
    r"|169\.254\.169\.254)"
)

_SSRF_SCHEMES = re.compile(r"\b(?:file|gopher|dict):", re.IGNORECASE)

# DNS-rebinding / spoofing domains that resolve to loopback or link-local.
_SSRF_REBINDING = re.compile(
    r"\b\d{1,3}(?:\.\d{1,3}){1,3}\.(?:sslip\.io|sslip\.com|xip\.io|nip\.io)"
    r"\b", re.IGNORECASE,
)

# Decimal (2130706433) and hex (0x7f000001 / 0x7F.0.0.1) integer IP forms.
_NUMERIC_IP = re.compile(r"\b(?:0[xX][0-9a-fA-F]{1,8}|\d{9,10})\b")

_URL_FIELD_HINTS = ("url", "uri", "link", "href", "redirect", "callback", "webhook", "image", "target", "host", "endpoint", "avatar", "icon", "src")

_TRAVERSAL = re.compile(r"(?:\.\./|\.\.%2f|%2e%2e|\.\.\\|%2e%2e%2f|%252e%252e)", re.IGNORECASE)

_KNOWN_SCANNERS = (
    "sqlmap",
    "nikto",
    "nuclei",
    "nmap",
    "masscan",
    "zap",
    "wpscan",
    "gobuster",
    "dirb",
    "dirbuster",
    "nessus",
    "acunetix",
    "nessus",
    "python-requests",
    "go-http-client",
    "scrapy",
)

_INTERNAL_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "127.0.0.0/8")

_METHODS_STRICT = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _is_private_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(net) for net in _INTERNAL_NETWORKS)


def _normalize_numeric_ips(text: str) -> str:
    """Rewrite decimal/hex integer IP forms (2130706433, 0x7f000001) to dotted quads."""

    def _convert(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            value = int(raw, 0)
        except ValueError:
            return raw
        if not 0 <= value <= 0xFFFFFFFF:
            return raw
        quad = ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))
        return quad

    return _NUMERIC_IP.sub(_convert, text)


class ApiRulesEngine:
    """Deterministic API security rule set."""

    def __init__(self, max_request_bytes: int = 5_000_000) -> None:
        self._max_request_bytes = max_request_bytes

    def inspect(self, ctx: RequestContext, stats: dict | None = None) -> list[Finding]:
        stats = stats or {}
        findings: list[Finding] = []

        # Scan raw + normalized inspection variants so encoding evasions cannot
        # hide payloads from deterministic rules. Original request bytes are
        # not modified — decoding is for inspection only.
        body_to_scan = " ".join(
            inspection_variants(
                ctx.body_text,
                ctx.query_string,
                ctx.path,
            )
        )

        findings += self._check_oversized(ctx)
        findings += self._check_malformed(ctx)
        findings += self._check_smuggling(ctx)
        findings += self._check_method(ctx)
        findings += self._check_traversal(ctx, body_to_scan)
        findings += self._check_sqli(ctx, body_to_scan)
        findings += self._check_command_injection(ctx, body_to_scan)
        findings += self._check_ssrf(ctx)
        findings += self._check_xml_xxe(ctx)
        findings += self._check_header_spoofing(ctx)
        findings += self._check_user_agent(ctx)
        findings += self._check_param_pollution(ctx)
        findings += self._check_rate_abuse(ctx, stats)
        findings += self._check_auth_burst(ctx, stats)
        findings += self._check_enumeration(ctx, stats)
        findings += self._check_bola(ctx, stats)
        return findings

    def _finding(
        self,
        rule_id: str,
        name: str,
        severity: str,
        reasons: list[str],
        mitre: list[str],
        details: dict | None = None,
    ) -> Finding:
        return Finding(
            rule_id=rule_id,
            name=name,
            severity=severity,
            score=SEVERITY_WEIGHT[severity],
            reasons=reasons,
            mitre=mitre,
            source="rules",
            details=details,
        )

    def _check_oversized(self, ctx: RequestContext) -> list[Finding]:
        if ctx.body_bytes > self._max_request_bytes:
            return [
                self._finding(
                    "API-001",
                    "Oversized request body",
                    "MEDIUM",
                    [f"Request body is {ctx.body_bytes} bytes"],
                    ["T1499"],
                    {"bytes": ctx.body_bytes},
                )
            ]
        return []

    def _check_malformed(self, ctx: RequestContext) -> list[Finding]:
        content_type = ctx.headers.get("content-type", "")
        if "json" in content_type and ctx.body_text:
            if ctx.body_json is None:
                return [
                    self._finding(
                        "API-002",
                        "Malformed JSON body",
                        "LOW",
                        ["Body declared as JSON but failed to parse"],
                        ["T1190"],
                    )
                ]
        if ctx.body_text and "\x00" in ctx.body_text:
            return [
                self._finding(
                    "API-002",
                    "Null byte in request body",
                    "MEDIUM",
                    ["Raw null byte detected in request body"],
                    ["T1027"],
                )
            ]
        return []

    def _check_smuggling(self, ctx: RequestContext) -> list[Finding]:
        has_cl = "content-length" in ctx.headers
        has_te = ctx.headers.get("transfer-encoding", "").lower() == "chunked"
        if has_cl and has_te:
            return [
                self._finding(
                    "API-003",
                    "HTTP smuggling indicators",
                    "HIGH",
                    ["Both Content-Length and Transfer-Encoding present"],
                    ["T1071"],
                )
            ]
        if has_cl:
            try:
                declared = int(ctx.headers["content-length"])
                if declared < 0:
                    return [self._finding("API-003", "Negative Content-Length", "HIGH", ["Invalid Content-Length header"], ["T1071"])]
                if declared > self._max_request_bytes * 4:
                    return [self._finding("API-003", "Absurd Content-Length", "MEDIUM", ["Content-Length exceeds limits"], ["T1499"])]
            except ValueError:
                return [
                    self._finding(
                        "API-003",
                        "Invalid Content-Length",
                        "MEDIUM",
                        ["Content-Length is not a valid integer"],
                        ["T1071"],
                    )
                ]
        return []

    def _check_method(self, ctx: RequestContext) -> list[Finding]:
        if ctx.method not in _METHODS_STRICT:
            return [
                self._finding(
                    "API-004",
                    f"Unsupported HTTP method {ctx.method}",
                    "LOW",
                    [f"Method '{ctx.method}' is unusual"],
                    ["T1071"],
                )
            ]
        if ctx.method == "TRACE":
            return [
                self._finding(
                    "API-004",
                    "TRACE method enabled",
                    "MEDIUM",
                    ["TRACE can leak headers via XST attacks"],
                    ["T1071"],
                )
            ]
        return []

    def _check_traversal(self, ctx: RequestContext, body: str) -> list[Finding]:
        if _TRAVERSAL.search(body):
            return [
                self._finding(
                    "API-005",
                    "Path traversal indicators",
                    "HIGH",
                    ["Path traversal sequences detected (../ or encodings)"],
                    ["T1190"],
                )
            ]
        return []

    def _check_sqli(self, ctx: RequestContext, body: str) -> list[Finding]:
        for pattern in _SQLI_PATTERNS:
            if pattern.search(body):
                return [
                    self._finding(
                        "API-006",
                        "SQL injection indicators",
                        "HIGH",
                        [f"SQL injection pattern matched: {pattern.pattern[:60]}"],
                        ["T1190"],
                    )
                ]
        return []

    def _check_command_injection(self, ctx: RequestContext, body: str) -> list[Finding]:
        for pattern in _CMD_INJ_PATTERNS:
            if pattern.search(body):
                return [
                    self._finding(
                        "API-007",
                        "Command injection indicators",
                        "HIGH",
                        [f"Command injection pattern matched: {pattern.pattern[:60]}"],
                        ["T1059"],
                    )
                ]
        return []

    def _check_ssrf(self, ctx: RequestContext) -> list[Finding]:
        haystack = " ".join(
            inspection_variants(ctx.query_string, ctx.body_text, ctx.path, max_rounds=2)
        )
        normalized = _normalize_numeric_ips(haystack)
        matches = (
            _SSRF_HOSTS.findall(haystack)
            + _SSRF_SCHEMES.findall(haystack)
            + _SSRF_REBINDING.findall(haystack)
            + _SSRF_HOSTS.findall(normalized)
        )
        if matches:
            return [
                self._finding(
                    "API-008",
                    "SSRF indicators",
                    "HIGH",
                    [f"SSRF target detected: {m}" for m in list(dict.fromkeys(matches))],
                    ["T1190"],
                    {"matches": list(dict.fromkeys(matches))},
                )
            ]
        return []

    def _check_xml_xxe(self, ctx: RequestContext) -> list[Finding]:
        content_type = ctx.headers.get("content-type", "")
        body = ctx.body_text or ""
        if "xml" in content_type and re.search(
            r"<!DOCTYPE|<!ENTITY|\[\s*<!ENTITY", body, re.IGNORECASE
        ):
            return [
                self._finding(
                    "API-009",
                    "XXE indicators",
                    "HIGH",
                    ["XML external entity declaration in body"],
                    ["T1190"],
                )
            ]
        return []

    def _check_header_spoofing(self, ctx: RequestContext) -> list[Finding]:
        fwd = ctx.headers.get("x-forwarded-for", "")
        if fwd and _is_private_ip(fwd.split(",")[0].strip()):
            return [
                self._finding(
                    "API-010",
                    "Spoofed internal source IP",
                    "MEDIUM",
                    ["X-Forwarded-For claims a private/internal address"],
                    ["T1078"],
                )
            ]
        return []

    def _check_user_agent(self, ctx: RequestContext) -> list[Finding]:
        ua = (ctx.user_agent or "").lower()
        if not ua:
            return []
        hit = next((s for s in _KNOWN_SCANNERS if s in ua), None)
        if hit:
            return [
                self._finding(
                    "API-011",
                    "Known scanner/bot user-agent",
                    "MEDIUM",
                    [f"User-Agent matches known tool: {hit}"],
                    ["T1595"],
                )
            ]
        return []

    def _check_param_pollution(self, ctx: RequestContext) -> list[Finding]:
        query = ctx.query_params()
        if not query:
            return []
        if ctx.body_json and isinstance(ctx.body_json, dict):
            dupes = set(query.keys()) & set(ctx.body_json.keys())
            conflicts = [
                key for key in dupes if str(query[key]) != str(ctx.body_json[key])
            ]
            if conflicts:
                return [
                    self._finding(
                        "API-012",
                        "HTTP parameter pollution",
                        "MEDIUM",
                        [f"Conflicting parameter values: {conflicts}"],
                        ["T1190"],
                    )
                ]
        return []

    def _check_rate_abuse(self, ctx: RequestContext, stats: dict) -> list[Finding]:
        rate = stats.get("request_rate_per_min", 0.0)
        baseline = stats.get("baseline_rate_per_min", 1.0)
        ratio = rate / max(baseline, 1.0)
        if ratio >= 20:
            return [
                self._finding(
                    "API-013",
                    "Excessive request rate",
                    "HIGH",
                    [f"{rate:.1f} requests/min vs baseline {baseline:.1f} ({ratio:.0f}x)"],
                    ["T1499"],
                    {"rate": rate, "baseline": baseline, "ratio": ratio},
                )
            ]
        if ratio >= 8:
            return [
                self._finding(
                    "API-013",
                    "Elevated request rate",
                    "MEDIUM",
                    [f"{rate:.1f} requests/min vs baseline {baseline:.1f} ({ratio:.0f}x)"],
                    ["T1499"],
                )
            ]
        return []

    def _check_auth_burst(self, ctx: RequestContext, stats: dict) -> list[Finding]:
        failures = stats.get("auth_failures_5min", 0)
        if failures >= 20:
            return [
                self._finding(
                    "API-014",
                    "Authentication failure burst",
                    "HIGH",
                    [f"{failures} failed authentications in 5 minutes"],
                    ["T1110"],
                    {"failures": failures},
                )
            ]
        if failures >= 5:
            return [
                self._finding(
                    "API-014",
                    "Repeated authentication failures",
                    "MEDIUM",
                    [f"{failures} failed authentications in 5 minutes"],
                    ["T1110"],
                )
            ]
        return []

    def _check_enumeration(self, ctx: RequestContext, stats: dict) -> list[Finding]:
        not_found = stats.get("not_found_5min", 0)
        distinct = stats.get("distinct_endpoints_5min", 0)
        if not_found >= 30:
            return [
                self._finding(
                    "API-015",
                    "API endpoint enumeration",
                    "HIGH",
                    [f"{not_found} not-found responses in 5 minutes"],
                    ["T1083"],
                )
            ]
        if distinct >= 30 and distinct >= 0:
            return [
                self._finding(
                    "API-015",
                    "High endpoint discovery activity",
                    "LOW",
                    [f"{distinct} distinct endpoints probed in 5 minutes"],
                    ["T1595"],
                )
            ]
        return []

    def _check_bola(self, ctx: RequestContext, stats: dict) -> list[Finding]:
        if stats.get("bola_attempt"):
            return [
                self._finding(
                    "API-016",
                    "BOLA/IDOR access attempt",
                    "HIGH",
                    ["Attempted access to a resource owned by another subject"],
                    ["T1078", "T1083"],
                )
            ]
        return []
