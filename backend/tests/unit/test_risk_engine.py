"""Risk aggregation engine tests."""
from app.security.base import Finding
from app.security.risk.engine import RiskInput, assess_risk


def _finding(rule_id: str, severity: str, score: float) -> Finding:
    return Finding(rule_id=rule_id, name=rule_id, severity=severity, score=score)


def test_clean_input_is_low_zero():
    result = assess_risk(RiskInput())
    assert result.level == "LOW"
    assert result.score == 0.0


def test_single_high_finding_scoring():
    result = assess_risk(RiskInput(findings=[_finding("API-006", "HIGH", 0.7)]))
    # 0.4 * 0.7 * 100 = 28 -> MEDIUM
    assert result.level == "MEDIUM"
    assert result.score == 28.0


def test_critical_finding_is_medium_score():
    result = assess_risk(RiskInput(findings=[_finding("API-006", "CRITICAL", 1.0)]))
    assert result.score == 40.0
    assert result.level == "MEDIUM"


def test_multiple_signals_reach_critical():
    result = assess_risk(
        RiskInput(
            findings=[_finding("API-006", "HIGH", 0.7), _finding("API-007", "HIGH", 0.7)],
            ml_anomaly_score=0.9,
            ml_threat_probability=0.8,
            ml_available=True,
            behavior={"request_rate_ratio": 25.0, "auth_failures_5min": 20},
            data_sensitivity=0.8,
        )
    )
    assert result.level == "CRITICAL"
    assert result.score >= 75


def test_reasons_populated():
    result = assess_risk(RiskInput(findings=[_finding("API-006", "HIGH", 0.7)]))
    assert any("API-006" in r for r in result.reasons)


def test_behavior_score_components():
    result = assess_risk(
        RiskInput(behavior={"request_rate_ratio": 30.0, "auth_failures_5min": 30})
    )
    assert result.score > 0


def test_signal_breakdown_present():
    result = assess_risk(RiskInput(findings=[_finding("A", "HIGH", 0.7)]))
    assert "findings" in result.signal_breakdown
    assert result.signal_breakdown["findings"] == 0.7
