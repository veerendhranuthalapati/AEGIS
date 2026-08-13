"""Rule-based anomaly baseline for ML V2 comparison."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rule_based_scores(df: pd.DataFrame) -> np.ndarray:
    """Heuristic scores 0..1 — mirrors operational intuition, not ML."""
    score = np.zeros(len(df), dtype=float)
    rate = df.get("request_rate_per_min", 0).to_numpy(dtype=float)
    endpoints = df.get("unique_endpoints_1h", 0).to_numpy(dtype=float)
    failures = df.get("auth_failures_5min", 0).to_numpy(dtype=float)
    rarity = df.get("endpoint_rarity", 1).to_numpy(dtype=float)
    tool_calls = df.get("tool_call_count", 0).to_numpy(dtype=float)
    prompt_len = df.get("prompt_length", 0).to_numpy(dtype=float)
    sensitive = df.get("body_has_sensitive", 0).to_numpy(dtype=float)

    score += np.clip(rate / 30.0, 0, 0.4)
    score += np.clip(endpoints / 25.0, 0, 0.25)
    score += np.clip(failures / 20.0, 0, 0.35)
    score += np.clip((0.2 - rarity) / 0.2, 0, 0.2)
    score += np.clip(tool_calls / 5.0, 0, 0.15)
    score += np.clip(prompt_len / 1500.0, 0, 0.1)
    score += sensitive * 0.15
    return np.clip(score, 0, 1)


def rule_based_predict(df: pd.DataFrame, threshold: float = 0.45) -> np.ndarray:
    return (rule_based_scores(df) >= threshold).astype(int)
