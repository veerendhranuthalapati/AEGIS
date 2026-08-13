"""ML drift monitoring tests."""
from __future__ import annotations

from app.ml.drift import DriftMonitor


def test_drift_monitor_detects_feature_shift() -> None:
    monitor = DriftMonitor(["request_rate_per_min", "unique_endpoints_1h"])
    for _ in range(50):
        monitor.record_prediction(
            {"request_rate_per_min": 2.0, "unique_endpoints_1h": 3.0},
            0.1,
            0.1,
            False,
        )
    monitor.set_baseline_from_window()
    for _ in range(50):
        monitor.record_prediction(
            {"request_rate_per_min": 50.0, "unique_endpoints_1h": 30.0},
            0.8,
            0.8,
            True,
        )
    report = monitor.check_drift()
    assert report["drift_detected"] is True
    assert report["alerts"]
