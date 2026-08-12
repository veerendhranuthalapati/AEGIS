"""Risk engine: combines all detection signals into a single 0..100 score.

The composite is configurable through settings thresholds. Every decision
carries a human-readable explanation derived from the contributing signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.security.base import Finding

settings = get_settings()

# Weight of each signal family. Sums to 1.0.
W_FINDINGS = 0.40
W_ML = 0.25
W_BEHAVIOR = 0.15
W_SENSITIVITY = 0.10
W_HISTORY = 0.10


@dataclass
class RiskInput:
    findings: list[Finding] = field(default_factory=list)
    ml_anomaly_score: float = 0.0  # 0..1
    ml_threat_probability: float = 0.0  # 0..1
    behavior: dict = field(default_factory=dict)
    data_sensitivity: float = 0.0  # 0..1
    attack_history: float = 0.0  # 0..1
    policy_violations: int = 0

    @property
    def has_signals(self) -> bool:
        return bool(
            self.findings
            or self.ml_anomaly_score > 0
            or self.ml_threat_probability > 0
            or self.behavior
            or self.data_sensitivity > 0
            or self.attack_history > 0
            or self.policy_violations > 0
        )


@dataclass
class RiskAssessment:
    score: float
    level: str  # LOW | MEDIUM | HIGH | CRITICAL
    reasons: list[str] = field(default_factory=list)
    finding_dicts: list[dict] = field(default_factory=list)
    signal_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "level": self.level,
            "reasons": self.reasons,
            "findings": self.finding_dicts,
            "breakdown": self.signal_breakdown,
        }


def _finding_score(findings: list[Finding]) -> float:
    if not findings:
        return 0.0
    scores = sorted(f.score for f in findings)
    top = scores[-1]
    rest = scores[:-1]
    mean_rest = sum(rest) / len(rest) if rest else 0.0
    return min(1.0, top + 0.35 * mean_rest)


def _ml_score(anomaly: float, threat_prob: float) -> float:
    return min(1.0, 0.6 * max(0.0, min(1.0, anomaly)) + 0.4 * max(0.0, min(1.0, threat_prob)))


def _behavior_score(behavior: dict) -> float:
    score = 0.0
    rate_ratio = behavior.get("request_rate_ratio", 0.0)
    if rate_ratio >= 20:
        score += 0.6
    elif rate_ratio >= 8:
        score += 0.3
    failures = behavior.get("auth_failures_5min", 0)
    if failures >= 20:
        score += 0.5
    elif failures >= 5:
        score += 0.2
    if behavior.get("new_device"):
        score += 0.25
    if behavior.get("geo_change"):
        score += 0.2
    if behavior.get("new_session_from_new_ip"):
        score += 0.15
    if behavior.get("token_age_hours") is not None and behavior["token_age_hours"] > 72:
        score += 0.1
    return min(1.0, score)


def assess_risk(risk_input: RiskInput) -> RiskAssessment:
    reasons: list[str] = []

    f_score = _finding_score(risk_input.findings)
    if risk_input.findings:
        for f in risk_input.findings:
            reasons.append(f"{f.name} ({f.severity})")

    ml = _ml_score(risk_input.ml_anomaly_score, risk_input.ml_threat_probability)
    if ml >= 0.6:
        reasons.append(f"ML anomaly score {ml:.2f}")

    behavior = _behavior_score(risk_input.behavior)
    if behavior >= 0.4:
        parts = []
        if risk_input.behavior.get("request_rate_ratio", 0) >= 8:
            parts.append("elevated request rate")
        if risk_input.behavior.get("auth_failures_5min", 0) >= 5:
            parts.append("repeated auth failures")
        if risk_input.behavior.get("new_device"):
            parts.append("new device")
        if risk_input.behavior.get("geo_change"):
            parts.append("geo change")
        if parts:
            reasons.append("Behavioral anomaly: " + ", ".join(parts))

    if risk_input.data_sensitivity >= 0.5:
        reasons.append("Sensitive data exposure")

    if risk_input.attack_history >= 0.5:
        reasons.append("History of related attacks on this subject")

    if risk_input.policy_violations:
        reasons.append(f"{risk_input.policy_violations} policy violation(s)")

    raw = (
        W_FINDINGS * f_score
        + W_ML * ml
        + W_BEHAVIOR * behavior
        + W_SENSITIVITY * min(1.0, risk_input.data_sensitivity)
        + W_HISTORY * min(1.0, risk_input.attack_history)
    ) * 100
    raw = min(100.0, raw + min(10.0, 2.0 * risk_input.policy_violations))

    if raw <= settings.risk_low_max:
        level = "LOW"
    elif raw <= settings.risk_medium_max:
        level = "MEDIUM"
    elif raw <= settings.risk_high_max:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return RiskAssessment(
        score=round(raw, 1),
        level=level,
        reasons=reasons[:12],
        finding_dicts=[f.to_dict() for f in risk_input.findings],
        signal_breakdown={
            "findings": round(f_score, 3),
            "ml": round(ml, 3),
            "behavior": round(behavior, 3),
            "sensitivity": round(risk_input.data_sensitivity, 3),
            "history": round(risk_input.attack_history, 3),
        },
    )
