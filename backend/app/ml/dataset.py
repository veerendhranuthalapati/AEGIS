"""Synthetic labeled dataset generator.

This dataset is SYNTHETIC and clearly documented as such. It is used to
demonstrate and test the ML pipeline end-to-end. Real-world retraining is a
documented future improvement; the pipeline accepts any DataFrame with the
same feature columns and an optional ``is_attack`` label.
"""
from __future__ import annotations

import random

import pandas as pd


def _random_normal_row(rng: random.Random, actor_type: str) -> dict:
    if actor_type == "normal":
        auth = 1
        rate = rng.uniform(0.5, 6)
        endpoints = int(rng.uniform(1, 6))
        failures = 0
        new_device = 0
        rarity = 1.0 / rng.uniform(1, 200)
        prompt_len = rng.uniform(10, 200)
    else:  # attacker
        auth = 0 if rng.random() < 0.7 else 1
        rate = rng.uniform(20, 120)
        endpoints = int(rng.uniform(8, 40))
        failures = int(rng.uniform(0, 60))
        new_device = 1 if rng.random() < 0.6 else 0
        rarity = rng.uniform(0.001, 0.2)
        prompt_len = rng.uniform(10, 600)

    return {
        "hour_of_day": float(rng.uniform(0, 23)),
        "day_of_week": float(rng.uniform(0, 6)),
        "log_request_size": rng.uniform(4, 14),
        "query_param_count": float(rng.uniform(0, 12)),
        "path_depth": float(rng.uniform(1, 8)),
        "path_length": float(rng.uniform(10, 100)),
        "user_agent_length": float(rng.uniform(20, 200)),
        "is_authenticated": float(auth),
        "request_rate_per_min": rate,
        "unique_endpoints_1h": float(endpoints),
        "auth_failures_5min": float(failures),
        "body_has_sensitive": 1.0 if rng.random() < 0.05 else 0.0,
        "body_entropy": rng.uniform(2.0, 7.5),
        "prompt_length": prompt_len,
        "tool_call_count": float(rng.uniform(0, 3)),
        "new_device": float(new_device),
        "account_age_days": rng.uniform(1, 500),
        "endpoint_rarity": rarity,
        "payload_max_token_like": rng.uniform(0, 0.3),
        "status_code": 200 if actor_type == "normal" else float(rng.choice([401, 403, 404, 500, 200])),
        "log_response_size": rng.uniform(3, 12),
    }


def generate_synthetic_dataset(
    size: int, seed: int = 42, attack_ratio: float = 0.25
) -> pd.DataFrame:
    """Generate a labeled synthetic dataset.

    Columns are the full feature set plus ``is_attack`` (1/0). Normal rows
    model a regular user; attack rows model enumeration, injection, SSRF,
    brute force, prompt injection and data-exfiltration behavior.
    """
    rng = random.Random(seed)
    rows: list[dict] = []
    n_attack = int(size * attack_ratio)
    for _ in range(size):
        actor_type = "attacker" if len(rows) < n_attack else "normal"
        row = _random_normal_row(rng, actor_type)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["is_attack"] = 0
    df.loc[: n_attack - 1, "is_attack"] = 1
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    df["is_attack"] = df["is_attack"].astype(int)
    return df
