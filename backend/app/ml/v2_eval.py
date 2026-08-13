"""ML V2 evaluation — temporal splits, baselines, and metrics."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.baselines import rule_based_predict, rule_based_scores
from app.ml.pipeline import _anomaly_to_score, _isolation_forest, _random_forest
from app.ml.telemetry_schema import DATASET_VERSION, FEATURE_VERSION, V2_FEATURES


@dataclass
class SplitIndices:
    train: np.ndarray
    val: np.ndarray
    test: np.ndarray
    test_unseen_actors: np.ndarray


def temporal_actor_split(
    df: pd.DataFrame,
    *,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
    unseen_actor_frac: float = 0.15,
    seed: int = 42,
) -> SplitIndices:
    """Train on earliest period, validate next, test on latest + unseen actors."""
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    rng = np.random.default_rng(seed)
    actors = df["actor_id"].unique()
    n_unseen = max(1, int(len(actors) * unseen_actor_frac))
    unseen_actors = set(rng.choice(actors, size=n_unseen, replace=False))

    idx = np.arange(n)
    train_idx = idx[:train_end]
    val_idx = idx[train_end:val_end]
    test_idx = idx[val_end:]

    unseen_mask = df.loc[test_idx, "actor_id"].isin(unseen_actors).to_numpy()
    test_unseen_idx = test_idx[unseen_mask]

    return SplitIndices(
        train=train_idx,
        val=val_idx,
        test=test_idx,
        test_unseen_actors=test_unseen_idx,
    )


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    out: dict[str, Any] = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "false_positive_rate": fp / max(tn + fp, 1),
        "false_negative_rate": fn / max(tp + fn, 1),
        "confusion_matrix": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, scores))
    except ValueError:
        out["roc_auc"] = float("nan")
    try:
        out["pr_auc"] = float(average_precision_score(y_true, scores))
    except ValueError:
        out["pr_auc"] = float("nan")
    return out


def _positive_class_proba(model, X: np.ndarray) -> np.ndarray:
    proba = model.predict_proba(X)
    if proba.shape[1] == 1:
        return np.ones(len(X)) if model.classes_[0] == 1 else np.zeros(len(X))
    pos_idx = list(model.classes_).index(1)
    return proba[:, pos_idx]


def evaluate_v2_dataset(df: pd.DataFrame, *, seed: int = 42) -> dict[str, Any]:
    """Full V2 evaluation with temporal split and baselines."""
    splits = temporal_actor_split(df, seed=seed)
    feature_cols = [c for c in V2_FEATURES if c in df.columns]
    X = df[feature_cols].to_numpy(dtype=float)
    y = df["is_attack"].to_numpy(dtype=int)

    X_train, y_train = X[splits.train], y[splits.train]
    _, y_val = X[splits.val], y[splits.val]
    X_test, y_test = X[splits.test], y[splits.test]
    X_unseen, y_unseen = X[splits.test_unseen_actors], y[splits.test_unseen_actors]

    results: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "feature_version": FEATURE_VERSION,
        "feature_names": feature_cols,
        "n_total": len(df),
        "n_train": len(splits.train),
        "n_val": len(splits.val),
        "n_test": len(splits.test),
        "n_test_unseen_actors": len(splits.test_unseen_actors),
        "attack_ratio": float(y.mean()),
        "split_methodology": "temporal 60/20/20 + unseen-actor holdout on test tail",
        "evaluation_type": "Controlled synthetic/local telemetry evaluation",
    }

    # --- Rule baseline ---
    val_df = df.iloc[splits.val]
    test_df = df.iloc[splits.test]
    rule_scores_val = rule_based_scores(val_df)
    rule_scores_test = rule_based_scores(test_df)
    threshold = 0.45
    results["rule_baseline"] = {
        "validation": _metrics(y_val, rule_based_predict(val_df, threshold), rule_scores_val),
        "test": _metrics(y_test, rule_based_predict(test_df, threshold), rule_scores_test),
    }

    # --- Isolation Forest (train on train only) ---
    iforest = _isolation_forest()
    t0 = time.perf_counter()
    iforest.fit(X_train)
    if_train_ms = (time.perf_counter() - t0) * 1000
    if_scores_test = _anomaly_to_score(iforest.decision_function(X_test))
    if_pred_test = (if_scores_test >= 0.5).astype(int)
    t0 = time.perf_counter()
    _ = iforest.decision_function(X_test[: min(100, len(X_test))])
    if_infer_ms = (time.perf_counter() - t0) * 1000 / max(min(100, len(X_test)), 1)
    results["isolation_forest"] = {
        "test": _metrics(y_test, if_pred_test, if_scores_test),
        "train_latency_ms": round(if_train_ms, 2),
        "inference_latency_ms_per_sample": round(if_infer_ms, 4),
    }

    # --- Random Forest ---
    rfc = _random_forest()
    t0 = time.perf_counter()
    rfc.fit(X_train, y_train)
    rf_train_ms = (time.perf_counter() - t0) * 1000
    rf_scores_test = _positive_class_proba(rfc, X_test)
    rf_pred_test = (rf_scores_test >= 0.5).astype(int)
    t0 = time.perf_counter()
    _ = rfc.predict_proba(X_test[: min(100, len(X_test))])
    rf_infer_ms = (time.perf_counter() - t0) * 1000 / max(min(100, len(X_test)), 1)
    unseen_scores = _positive_class_proba(rfc, X_unseen) if len(y_unseen) > 0 else np.array([])
    unseen_pred = (unseen_scores >= 0.5).astype(int) if len(y_unseen) > 0 else np.array([])
    results["random_forest"] = {
        "test": _metrics(y_test, rf_pred_test, rf_scores_test),
        "unseen_actors_test": _metrics(y_unseen, unseen_pred, unseen_scores)
        if len(y_unseen) > 0
        else {},
        "train_latency_ms": round(rf_train_ms, 2),
        "inference_latency_ms_per_sample": round(rf_infer_ms, 4),
    }

    # --- Gradient Boosting (XGBoost substitute — xgboost not in dependencies) ---
    gbc = GradientBoostingClassifier(random_state=seed, max_depth=5, n_estimators=100)
    t0 = time.perf_counter()
    gbc.fit(X_train, y_train)
    gb_train_ms = (time.perf_counter() - t0) * 1000
    gb_scores = _positive_class_proba(gbc, X_test)
    gb_pred = (gb_scores >= 0.5).astype(int)
    results["gradient_boosting"] = {
        "note": "sklearn GradientBoostingClassifier (XGBoost not installed)",
        "test": _metrics(y_test, gb_pred, gb_scores),
        "train_latency_ms": round(gb_train_ms, 2),
    }

    # --- Hard negative analysis ---
    hard = df[df["scenario"].str.startswith("hard_negative")]
    if len(hard) > 0:
        hard_idx = hard.index.to_numpy()
        mask_test = np.isin(hard_idx, splits.test)
        hard_test = hard.iloc[np.where(mask_test)[0]] if mask_test.any() else hard.iloc[:0]
        if len(hard_test) > 0:
            hs = _positive_class_proba(rfc, hard_test[feature_cols].to_numpy(dtype=float))
            fp_rate = float((hs >= 0.5).mean())
            results["hard_negative_false_positive_rate_rf"] = fp_rate
            results["hard_negative_count_test"] = len(hard_test)

    results["limitations"] = [
        "Controlled synthetic/local telemetry — not production traffic",
        "Labels derived from scenario type, not ground-truth SOC adjudication",
        "V2 features include is_llm_route/method_is_write not in V1 online model",
        "GradientBoosting used instead of XGBoost (not in requirements)",
    ]
    return results
