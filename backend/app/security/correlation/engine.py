"""Attack correlation engine.

Deterministic, windowed correlation: recent events for the same subject
(correlation key) are grouped and scored against known multi-step attack
signatures. Matching signals produce an incident with confidence, timeline
and MITRE references.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

_SIGNAL_WEIGHTS: dict[str, float] = {
    "AUTH_FAILURE_BURST": 0.8,
    "LOGIN_ANOMALY": 0.6,
    "API_ENUMERATION": 0.7,
    "BOLA_ATTEMPT": 0.9,
    "ADMIN_PROBE": 0.7,
    "PRIVILEGE_ESCALATION": 0.9,
    "TOKEN_ANOMALY": 0.6,
    "PROMPT_INJECTION": 0.9,
    "JAILBREAK_ATTEMPT": 0.9,
    "SYSTEM_PROMPT_EXTRACTION": 0.8,
    "SENSITIVE_EXTRACTION": 0.85,
    "TOOL_ABUSE": 0.85,
    "TOOL_BLOCKED": 0.8,
    "SENSITIVE_OUTPUT": 0.7,
    "DATA_EXFILTRATION_INDICATOR": 0.9,
    "API_RATE_ABUSE": 0.7,
    "SSRF_INDICATOR": 0.8,
    "SQLI_INDICATOR": 0.8,
    "CMD_INJ_INDICATOR": 0.8,
    "PATH_TRAVERSAL": 0.7,
    "LLM_RATE_ABUSE": 0.7,
}

_ATTACK_SIGNATURES: list[dict[str, Any]] = [
    {
        "attack_type": "AI-assisted account takeover and data exfiltration",
        "signals": [
            "AUTH_FAILURE_BURST",
            "LOGIN_ANOMALY",
            "API_ENUMERATION",
            "BOLA_ATTEMPT",
            "ADMIN_PROBE",
            "PROMPT_INJECTION",
            "TOOL_ABUSE",
            "DATA_EXFILTRATION_INDICATOR",
        ],
        "min_signals": 4,
        "severity": "CRITICAL",
        "mitre": ["T1078", "T1110", "T1083", "T1041"],
    },
    {
        "attack_type": "Brute force / credential stuffing",
        "signals": [
            "AUTH_FAILURE_BURST",
            "LOGIN_ANOMALY",
            "API_ENUMERATION",
            "TOKEN_ANOMALY",
        ],
        "min_signals": 2,
        "severity": "HIGH",
        "mitre": ["T1110", "T1110.004"],
    },
    {
        "attack_type": "LLM prompt-injection campaign",
        "signals": [
            "PROMPT_INJECTION",
            "JAILBREAK_ATTEMPT",
            "SYSTEM_PROMPT_EXTRACTION",
            "SENSITIVE_EXTRACTION",
            "TOOL_ABUSE",
            "LLM_RATE_ABUSE",
        ],
        "min_signals": 3,
        "severity": "HIGH",
        "mitre": ["T1027", "T1005", "T1213"],
    },
    {
        "attack_type": "API abuse / scraping",
        "signals": [
            "API_RATE_ABUSE",
            "API_ENUMERATION",
            "ADMIN_PROBE",
            "BOLA_ATTEMPT",
        ],
        "min_signals": 2,
        "severity": "MEDIUM",
        "mitre": ["T1499", "T1083"],
    },
    {
        "attack_type": "Application-layer injection attack",
        "signals": [
            "SQLI_INDICATOR",
            "CMD_INJ_INDICATOR",
            "SSRF_INDICATOR",
            "PATH_TRAVERSAL",
        ],
        "min_signals": 2,
        "severity": "HIGH",
        "mitre": ["T1190", "T1059"],
    },
    {
        "attack_type": "Data exfiltration",
        "signals": [
            "BOLA_ATTEMPT",
            "SENSITIVE_OUTPUT",
            "DATA_EXFILTRATION_INDICATOR",
            "TOOL_ABUSE",
        ],
        "min_signals": 2,
        "severity": "HIGH",
        "mitre": ["T1041", "T1005"],
    },
]


@dataclass
class EventLike:
    event_id: str
    event_type: str
    timestamp: datetime
    severity: str
    actor_id: str | None
    source_ip: str | None
    endpoint: str | None
    correlation_key: str | None
    mitre: list[str] = field(default_factory=list)


@dataclass
class IncidentSuggestion:
    title: str
    attack_type: str
    severity: str
    confidence: float
    description: str
    timeline: list[dict]
    mitre: list[str]
    related_event_ids: list[str]
    attacker_key: str | None


def correlate(events: list[EventLike]) -> list[IncidentSuggestion]:
    """Correlate a window of events into incident suggestions."""
    if not events:
        return []
    suggestions: list[IncidentSuggestion] = []
    used: set[str] = set()

    for signature in _ATTACK_SIGNATURES:
        signature_set = set(signature["signals"])
        matched = [
            event
            for event in events
            if event.event_type in signature_set and event.event_id not in used
        ]
        # Deduplicate by event_id so replayed/duplicate events cannot inflate incidents.
        seen_ids: set[str] = set()
        deduped_matched: list[EventLike] = []
        for event in matched:
            if event.event_id in seen_ids:
                continue
            seen_ids.add(event.event_id)
            deduped_matched.append(event)
        matched = deduped_matched
        matched_types = {event.event_type for event in matched}
        overlap = len(matched_types)
        if overlap < signature["min_signals"]:
            continue

        for event in matched:
            used.add(event.event_id)

        score = 0.0
        for event_type in matched_types:
            score += _SIGNAL_WEIGHTS.get(event_type, 0.5)
        confidence = min(99.0, score / max(len(signature_set), 1) * 100)

        timeline = sorted(
            [
                {
                    "time": event.timestamp.isoformat(),
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                    "endpoint": event.endpoint,
                }
                for event in matched
            ],
            key=lambda item: str(item["time"]),
        )

        severity = signature["severity"]
        top = max((SEVERITY_ORDER.get(e.severity, 0) for e in matched), default=0)
        if top > SEVERITY_ORDER.get(severity, 0):
            severity = [k for k, v in SEVERITY_ORDER.items() if v == top][0]

        attackers = {e.correlation_key for e in matched if e.correlation_key}
        attacker_key = max(attackers, key=lambda k: len(k)) if attackers else None

        mitre: list[str] = []
        for event in matched:
            for technique in event.mitre or []:
                if technique not in mitre:
                    mitre.append(technique)
        for technique in signature["mitre"]:
            if technique not in mitre:
                mitre.append(technique)

        suggestions.append(
            IncidentSuggestion(
                title=f"{signature['attack_type']} ({attacker_key or 'unknown'})",
                attack_type=signature["attack_type"],
                severity=severity,
                confidence=round(confidence, 1),
                description=(
                    f"Correlated {overlap} signal types "
                    f"({', '.join(sorted(matched_types))}) from subject "
                    f"{attacker_key or 'unknown'} within the correlation window."
                ),
                timeline=timeline,
                mitre=mitre,
                related_event_ids=list(dict.fromkeys(event.event_id for event in matched)),
                attacker_key=attacker_key,
            )
        )

    return suggestions
