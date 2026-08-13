"""Controlled local traffic generator for ML V2 evaluation.

Generates sequential request telemetry per actor/scenario. Labels come from
the scenario type (attack vs legitimate), not from direct feature assignment.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.ml.telemetry_schema import V2_FEATURES


@dataclass
class ActorState:
    actor_id: str
    account_age_days: float
    is_attack_actor: bool
    scenario: str
    device_seen: bool = False
    request_times: list[datetime] = field(default_factory=list)
    endpoints_1h: list[str] = field(default_factory=list)
    auth_failures: int = 0
    tool_calls: int = 0


ATTACK_SCENARIOS = (
    "attack_enumeration",
    "attack_brute_force",
    "attack_bola",
    "attack_scraping",
    "attack_injection",
    "attack_llm_abuse",
    "attack_tool_abuse",
    "attack_exfil",
)

LEGIT_SCENARIOS = (
    "normal_browse",
    "normal_api",
    "normal_llm",
    "normal_tool",
)

HARD_NEGATIVE_SCENARIOS = (
    "hard_negative_high_traffic",
    "hard_negative_many_endpoints",
    "hard_negative_new_device",
    "hard_negative_unusual_hour",
    "hard_negative_long_prompt",
)


def _entropy_approx(size: int, sensitive: bool) -> float:
    base = random.uniform(2.5, 5.0)
    if sensitive:
        base += random.uniform(0.5, 1.5)
    return min(7.5, base + size * 0.001)


def _emit_request(
    actor: ActorState,
    ts: datetime,
    *,
    path: str,
    method: str,
    body_bytes: int,
    query_params: int,
    is_llm: bool,
    prompt_len: int,
    sensitive_body: bool,
    endpoint_rarity: float,
) -> dict:
    actor.request_times.append(ts)
    actor.endpoints_1h.append(path)
    cutoff_1h = ts - timedelta(hours=1)
    actor.endpoints_1h = [e for e, t in zip(actor.endpoints_1h, actor.request_times) if t >= cutoff_1h]
    cutoff_1m = ts - timedelta(minutes=1)
    cutoff_5m = ts - timedelta(minutes=5)
    times_1m = [t for t in actor.request_times if t >= cutoff_1m]
    times_5m = [t for t in actor.request_times if t >= cutoff_5m]
    rate_per_min = float(len(times_1m))
    unique_ep = float(len(set(actor.endpoints_1h)))

    row = {
        "timestamp": ts.isoformat(),
        "actor_id": actor.actor_id,
        "scenario": actor.scenario,
        "is_attack": int(actor.is_attack_actor),
        "hour_of_day": float(ts.hour),
        "day_of_week": float(ts.weekday()),
        "log_request_size": math.log1p(body_bytes),
        "query_param_count": float(query_params),
        "path_depth": float(len([p for p in path.split("/") if p])),
        "path_length": float(len(path)),
        "user_agent_length": random.uniform(40, 180),
        "is_authenticated": 1.0,
        "request_rate_per_min": rate_per_min,
        "unique_endpoints_1h": unique_ep,
        "auth_failures_5min": float(actor.auth_failures),
        "body_has_sensitive": 1.0 if sensitive_body else 0.0,
        "body_entropy": _entropy_approx(body_bytes, sensitive_body),
        "prompt_length": float(prompt_len) if is_llm else 0.0,
        "tool_call_count": float(actor.tool_calls),
        "new_device": 0.0 if actor.device_seen else 1.0,
        "account_age_days": actor.account_age_days,
        "endpoint_rarity": endpoint_rarity,
        "payload_max_token_like": random.uniform(0, 0.15),
        "is_llm_route": 1.0 if is_llm else 0.0,
        "method_is_write": 1.0 if method in ("POST", "PUT", "PATCH", "DELETE") else 0.0,
        "requests_last_5min": float(len(times_5m)),
    }
    actor.device_seen = True
    return row


def _simulate_actor(rng: random.Random, actor: ActorState, start: datetime, n_events: int) -> list[dict]:
    rows: list[dict] = []
    ts = start
    scenario = actor.scenario

    for i in range(n_events):
        ts += timedelta(seconds=rng.uniform(0.5, 8.0))
        path = "/api/public/products"
        method = "GET"
        body_bytes = int(rng.uniform(100, 800))
        query_params = 0
        is_llm = False
        prompt_len = 0
        sensitive = False
        rarity = 1.0 / rng.uniform(5, 200)

        if scenario == "normal_browse":
            path = rng.choice(["/api/public/products", "/api/users/1", "/api/orders/101"])
        elif scenario == "normal_api":
            path = rng.choice(["/api/users/1", "/api/orders/101", "/api/payments/summary"])
            method = rng.choice(["GET", "GET", "POST"])
            body_bytes = int(rng.uniform(200, 1500))
        elif scenario == "normal_llm":
            path = "/ai/chat"
            method = "POST"
            is_llm = True
            prompt_len = int(rng.uniform(20, 300))
            body_bytes = prompt_len + 50
        elif scenario == "normal_tool":
            path = "/api/tools/execute"
            method = "POST"
            actor.tool_calls += 1
            body_bytes = 400
        elif scenario == "hard_negative_high_traffic":
            ts += timedelta(seconds=0.2)
            path = rng.choice(["/api/public/products", "/api/users/1"])
        elif scenario == "hard_negative_many_endpoints":
            path = f"/api/users/{rng.randint(1, 4)}"
        elif scenario == "hard_negative_new_device":
            if i == 0:
                actor.device_seen = False
            path = "/api/public/products"
        elif scenario == "hard_negative_unusual_hour":
            ts = ts.replace(hour=rng.choice([2, 3, 4]))
            path = "/api/public/products"
        elif scenario == "hard_negative_long_prompt":
            path = "/ai/chat"
            method = "POST"
            is_llm = True
            prompt_len = int(rng.uniform(800, 2000))
            body_bytes = prompt_len
        elif scenario == "attack_enumeration":
            path = f"/api/users/{rng.randint(1, 50)}"
            rarity = rng.uniform(0.01, 0.1)
        elif scenario == "attack_brute_force":
            path = "/api/auth/login"
            method = "POST"
            actor.auth_failures = min(60, actor.auth_failures + int(rng.uniform(1, 5)))
            body_bytes = 120
        elif scenario == "attack_bola":
            path = f"/api/users/{rng.randint(2, 10)}"
            rarity = rng.uniform(0.05, 0.2)
        elif scenario == "attack_scraping":
            ts += timedelta(seconds=0.1)
            path = rng.choice([f"/api/orders/{oid}" for oid in range(100, 130)])
            rarity = rng.uniform(0.001, 0.05)
        elif scenario == "attack_injection":
            path = "/search"
            query_params = 3
            body_bytes = 500
            sensitive = rng.random() < 0.4
        elif scenario == "attack_llm_abuse":
            path = "/ai/chat"
            method = "POST"
            is_llm = True
            prompt_len = int(rng.uniform(100, 800))
            body_bytes = prompt_len
            sensitive = rng.random() < 0.3
        elif scenario == "attack_tool_abuse":
            path = "/api/tools/execute"
            method = "POST"
            actor.tool_calls += int(rng.uniform(1, 3))
            body_bytes = 600
        elif scenario == "attack_exfil":
            path = rng.choice(["/api/users/2", "/api/customers", "/ai/chat"])
            is_llm = path == "/ai/chat"
            if is_llm:
                method = "POST"
                prompt_len = int(rng.uniform(50, 400))
            sensitive = True

        rows.append(
            _emit_request(
                actor,
                ts,
                path=path,
                method=method,
                body_bytes=body_bytes,
                query_params=query_params,
                is_llm=is_llm,
                prompt_len=prompt_len,
                sensitive_body=sensitive,
                endpoint_rarity=rarity,
            )
        )
    return rows


def generate_traffic_dataset(
    *,
    events_per_actor: int = 40,
    n_legit_actors: int = 60,
    n_attack_actors: int = 25,
    n_hard_negative_actors: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate temporally ordered telemetry from simulated AEGIS traffic."""
    rng = random.Random(seed)
    base_start = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    all_rows: list[dict] = []
    actor_idx = 0
    actor_jobs: list[tuple[tuple[str, ...], bool]] = [
        (LEGIT_SCENARIOS, False),
        (HARD_NEGATIVE_SCENARIOS, False),
        (ATTACK_SCENARIOS, True),
    ]
    pending: list[tuple[str, bool]] = []
    for scenarios, attack in actor_jobs:
        for _ in range(
            n_legit_actors if scenarios == LEGIT_SCENARIOS
            else n_hard_negative_actors if scenarios == HARD_NEGATIVE_SCENARIOS
            else n_attack_actors
        ):
            pending.append((rng.choice(scenarios), attack))
    rng.shuffle(pending)

    for scenario, attack in pending:
        actor = ActorState(
            actor_id=f"actor_{actor_idx:04d}",
            account_age_days=rng.uniform(10, 800),
            is_attack_actor=attack,
            scenario=scenario,
        )
        actor_idx += 1
        offset = timedelta(hours=rng.uniform(0, 400), minutes=rng.uniform(0, 59))
        rows = _simulate_actor(rng, actor, base_start + offset, events_per_actor)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in V2_FEATURES:
        if col not in df.columns:
            df[col] = 0.0
    return df
