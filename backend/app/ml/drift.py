"""Basic ML drift monitoring — feature and prediction distribution shifts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.metrics import observe_ml_drift


@dataclass
class DriftSnapshot:
    feature_means: dict[str, float] = field(default_factory=dict)
    feature_stds: dict[str, float] = field(default_factory=dict)
    anomaly_rate: float = 0.0
    threat_mean: float = 0.0
    sample_count: int = 0


class DriftMonitor:
    """Process-local baseline vs rolling window comparison."""

    def __init__(self, feature_names: list[str]) -> None:
        self._feature_names = feature_names
        self._baseline: DriftSnapshot | None = None
        self._window: list[dict[str, float]] = []
        self._predictions: list[tuple[float, float, bool]] = []
        self._window_size = 500

    def record_prediction(
        self,
        features: dict[str, float],
        anomaly_score: float,
        threat_probability: float,
        is_anomaly: bool,
    ) -> None:
        self._window.append(features)
        if len(self._window) > self._window_size:
            self._window.pop(0)
        self._predictions.append((anomaly_score, threat_probability, is_anomaly))
        if len(self._predictions) > self._window_size:
            self._predictions.pop(0)

    def set_baseline_from_window(self) -> None:
        if not self._window:
            return
        means = {}
        stds = {}
        for name in self._feature_names:
            vals = [row.get(name, 0.0) for row in self._window]
            means[name] = float(np.mean(vals))
            stds[name] = float(np.std(vals))
        preds = self._predictions
        self._baseline = DriftSnapshot(
            feature_means=means,
            feature_stds=stds,
            anomaly_rate=float(np.mean([p[2] for p in preds])) if preds else 0.0,
            threat_mean=float(np.mean([p[1] for p in preds])) if preds else 0.0,
            sample_count=len(self._window),
        )

    def check_drift(self) -> dict[str, Any]:
        if self._baseline is None or not self._window:
            return {"drift_detected": False, "reason": "no_baseline"}
        alerts: list[str] = []
        for name in self._feature_names:
            vals = [row.get(name, 0.0) for row in self._window[-100:]]
            if not vals:
                continue
            current_mean = float(np.mean(vals))
            base_mean = self._baseline.feature_means.get(name, 0.0)
            base_std = max(self._baseline.feature_stds.get(name, 1.0), 1e-6)
            z = abs(current_mean - base_mean) / base_std
            if z > 3.0:
                alerts.append(f"feature_shift:{name}:z={z:.2f}")

        preds = self._predictions[-100:]
        if preds:
            current_anomaly_rate = float(np.mean([p[2] for p in preds]))
            if abs(current_anomaly_rate - self._baseline.anomaly_rate) > 0.15:
                alerts.append(
                    f"anomaly_rate_shift:{current_anomaly_rate:.3f} vs {self._baseline.anomaly_rate:.3f}"
                )

        drift = len(alerts) > 0
        if drift:
            observe_ml_drift(len(alerts))
        return {
            "drift_detected": drift,
            "alerts": alerts,
            "window_size": len(self._window),
        }


_shared_monitor: DriftMonitor | None = None


def get_drift_monitor(feature_names: list[str] | None = None) -> DriftMonitor:
    global _shared_monitor
    if _shared_monitor is None:
        from app.ml.features import REQUEST_FEATURES

        _shared_monitor = DriftMonitor(feature_names or REQUEST_FEATURES)
    return _shared_monitor
