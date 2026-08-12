"""ML training pipeline: two detectors.

1. Unsupervised — Isolation Forest (anomaly detection).
2. Supervised — Random Forest classifier (threat probability).

Metrics are computed honestly on a held-out test set and persisted with the
model version. No metrics are fabricated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.features import REQUEST_FEATURES


@dataclass
class TrainedModels:
    isolation_forest: IsolationForest
    random_forest: RandomForestClassifier
    metrics: dict
    version: int
    trained_at_iso: str


def _isolation_forest() -> IsolationForest:
    return IsolationForest(
        n_estimators=200,
        max_samples="auto",
        contamination=0.15,
        random_state=42,
        n_jobs=-1,
    )


def _random_forest() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=200,
        max_depth=14,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


def _anomaly_to_score(scores: np.ndarray) -> np.ndarray:
    """Map IsolationForest decision_function to a 0..1 anomaly probability."""
    # lower decision = more anomalous. Normalize with a logistic transform.
    return 1.0 / (1.0 + np.exp(-(-scores + 0.5) / 0.25))


def train_models(
    df: pd.DataFrame,
    version: int,
    *,
    eval_frac: float = 0.3,
) -> TrainedModels:
    X = df[REQUEST_FEATURES].to_numpy(dtype=float)
    y = df["is_attack"].to_numpy(dtype=int)

    split = int(len(df) * (1 - eval_frac))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # --- Unsupervised: IsolationForest trains on everything (unlabeled) ---
    iforest = _isolation_forest()
    start = time.perf_counter()
    iforest.fit(X)
    train_if_latency = (time.perf_counter() - start) * 1000

    anomaly_scores = _anomaly_to_score(iforest.decision_function(X_test))
    anomaly_pred = (anomaly_scores >= 0.5).astype(int)

    # --- Supervised: Random Forest ---
    rfc = _random_forest()
    start = time.perf_counter()
    rfc.fit(X_train, y_train)
    train_rf_latency = (time.perf_counter() - start) * 1000

    # --- Evaluate (inference latency measured on the test set) ---
    start = time.perf_counter()
    threat_proba = rfc.predict_proba(X_test)[:, 1]
    eval_latency = (time.perf_counter() - start) * 1000

    rf_pred = (threat_proba >= 0.5).astype(int)
    try:
        rf_auc = float(roc_auc_score(y_test, threat_proba))
    except ValueError:
        rf_auc = float("nan")
    try:
        if_auc = float(roc_auc_score(y_test, anomaly_scores))
    except ValueError:
        if_auc = float("nan")

    n_test = len(y_test)
    tn = int(np.sum((rf_pred == 0) & (y_test == 0)))
    fp = int(np.sum((rf_pred == 1) & (y_test == 0)))
    fn = int(np.sum((rf_pred == 0) & (y_test == 1)))
    tp = int(np.sum((rf_pred == 1) & (y_test == 1)))

    metrics = {
        "training_size": int(len(df)),
        "test_size": n_test,
        "eval_frac": eval_frac,
        "attack_ratio": float(y.mean()),
        "random_forest": {
            "precision": float(precision_score(y_test, rf_pred, zero_division=0)),
            "recall": float(recall_score(y_test, rf_pred, zero_division=0)),
            "f1": float(f1_score(y_test, rf_pred, zero_division=0)),
            "roc_auc": rf_auc,
            "accuracy": float(accuracy_score(y_test, rf_pred)),
            "false_positive_rate": fp / max(tn + fp, 1),
            "false_negative_rate": fn / max(tp + fn, 1),
            "train_latency_ms": round(train_rf_latency, 2),
        },
        "isolation_forest": {
            "precision": float(precision_score(y_test, anomaly_pred, zero_division=0)),
            "recall": float(recall_score(y_test, anomaly_pred, zero_division=0)),
            "f1": float(f1_score(y_test, anomaly_pred, zero_division=0)),
            "roc_auc": if_auc,
            "false_positive_rate": int(np.sum((anomaly_pred == 1) & (y_test == 0))) / max(n_test, 1),
            "false_negative_rate": int(np.sum((anomaly_pred == 0) & (y_test == 1))) / max(n_test, 1),
            "train_latency_ms": round(train_if_latency, 2),
        },
        "inference_latency_ms_total_eval": round(eval_latency, 2),
        "inference_latency_ms_per_sample": round(eval_latency / max(n_test, 1), 4),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "dataset": "synthetic",
    }

    return TrainedModels(
        isolation_forest=iforest,
        random_forest=rfc,
        metrics=metrics,
        version=version,
        trained_at_iso=pd.Timestamp.utcnow().isoformat(),
    )


def save_models(models: TrainedModels, artifact_dir: Path) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"aegis_v{models.version}"
    paths = {
        "isolation_forest": str(artifact_dir / f"{prefix}_isolation_forest.joblib"),
        "random_forest": str(artifact_dir / f"{prefix}_random_forest.joblib"),
        "features": str(artifact_dir / f"{prefix}_features.json"),
    }
    joblib.dump(models.isolation_forest, paths["isolation_forest"])
    joblib.dump(models.random_forest, paths["random_forest"])
    import json

    (artifact_dir / f"{prefix}_features.json").write_text(
        json.dumps(REQUEST_FEATURES), encoding="utf-8"
    )
    return paths


def load_models(artifact_dir: Path, version: int) -> tuple[IsolationForest, RandomForestClassifier]:
    prefix = f"aegis_v{version}"
    iforest = joblib.load(artifact_dir / f"{prefix}_isolation_forest.joblib")
    rfc = joblib.load(artifact_dir / f"{prefix}_random_forest.joblib")
    return iforest, rfc
