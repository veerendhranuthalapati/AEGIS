"""ML inference fail-safe — unavailable ML must not reduce risk."""
from __future__ import annotations

from app.security.risk.engine import RiskInput, assess_risk


def test_ml_unavailable_excludes_ml_weight() -> None:
    with_ml = RiskInput(
        ml_anomaly_score=0.9,
        ml_threat_probability=0.9,
        ml_available=True,
    )
    without_ml = RiskInput(
        ml_anomaly_score=0.0,
        ml_threat_probability=0.0,
        ml_available=False,
    )
    score_with = assess_risk(with_ml).score
    score_without = assess_risk(without_ml).score
    assert score_with > score_without
    assert assess_risk(without_ml).signal_breakdown["ml_available"] is False


def test_ml_unavailable_not_same_as_zero_scores_with_available_flag() -> None:
    """Zero scores with available=True would incorrectly contribute ML weight."""
    fake_low = RiskInput(ml_anomaly_score=0.0, ml_threat_probability=0.0, ml_available=True)
    unavailable = RiskInput(ml_available=False)
    assert assess_risk(fake_low).signal_breakdown["ml"] == 0.0
    assert assess_risk(unavailable).signal_breakdown["ml"] is None
