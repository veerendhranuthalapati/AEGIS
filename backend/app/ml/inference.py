"""ML inference service.

Loads the active model artifacts once and caches them. Predictions are
recorded so model behavior is auditable and measurable.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.metrics import observe_ml
from app.ml.features import REQUEST_FEATURES, features_from_request
from app.ml.registry import get_latest_active
from app.models import ModelPrediction

logger = structlog.get_logger("aegis.ml_inference")


@dataclass
class MlPrediction:
    anomaly_score: float
    is_anomaly: bool
    threat_probability: float
    features: dict
    latency_ms: float
    model_name: str | None = None
    model_version_id: str | None = None
    model_algorithm: str | None = None
    available: bool = False


class MlInferenceService:
    def __init__(self, settings=None) -> None:
        self._settings = settings or get_settings()
        self._models: dict | None = None
        self._lock = asyncio.Lock()
        self._load_failed = False

    async def load_active(self, session: AsyncSession) -> bool:
        if self._models is not None:
            return True
        async with self._lock:
            if self._models is not None:
                return True
            version = await get_latest_active(session)
            if version is None or not version.artifact_path:
                logger.warning("ml.no_active_model")
                self._load_failed = True
                return False
            try:
                from app.ml.pipeline import load_models

                iforest, rfc = load_models(
                    Path(version.artifact_path), version.version
                )
                self._models = {
                    "iforest": iforest,
                    "rfc": rfc,
                    "version_id": version.id,
                    "name": version.name,
                    "algorithm": version.algorithm,
                    "feature_names": version.feature_names or REQUEST_FEATURES,
                }
                self._load_failed = False
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("ml.load_failed", error=str(exc))
                self._load_failed = True
                return False

    async def predict(
        self, session: AsyncSession, ctx, stats: dict
    ) -> MlPrediction:
        if not self._settings.ml_enabled:
            observe_ml("disabled", 0.0)
            return MlPrediction(0.0, False, 0.0, {}, 0.0)

        loaded = await self.load_active(session)
        if not loaded or self._models is None:
            observe_ml("unavailable", 0.0)
            return MlPrediction(0.0, False, 0.0, {}, 0.0)

        models = self._models
        feature_dict = features_from_request(ctx, stats)
        features_vector = np.array(
            [feature_dict[name] for name in models["feature_names"]],
            dtype=np.float64,
        ).reshape(1, -1)

        start = time.perf_counter()
        iforest = models["iforest"]
        rfc = models["rfc"]
        raw = float(iforest.decision_function(features_vector)[0])
        anomaly = 1.0 / (1.0 + np.exp(-(-raw + 0.5) / 0.25))
        threat = float(rfc.predict_proba(features_vector)[0, 1])
        latency_ms = (time.perf_counter() - start) * 1000

        is_anomaly = bool(
            anomaly
            >= max(0.0, min(1.0, self._settings.ml_anomaly_threshold))
        ) or bool(threat >= 0.5)

        prediction = MlPrediction(
            anomaly_score=round(float(anomaly), 4),
            is_anomaly=is_anomaly,
            threat_probability=round(threat, 4),
            features={k: round(v, 4) for k, v in feature_dict.items()},
            latency_ms=round(latency_ms, 3),
            model_name=models["name"],
            model_version_id=models["version_id"],
            model_algorithm=models["algorithm"],
            available=True,
        )
        observe_ml("available", latency_ms)

        record = ModelPrediction(
            request_id=ctx.request_id,
            model_version_id=models["version_id"],
            model_name=models["name"],
            model_algorithm=models["algorithm"],
            anomaly_score=prediction.anomaly_score,
            is_anomaly=prediction.is_anomaly,
            threat_probability=prediction.threat_probability,
            features=prediction.features,
            latency_ms=prediction.latency_ms,
        )
        session.add(record)
        return prediction
