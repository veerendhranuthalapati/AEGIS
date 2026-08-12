"""AEGIS performance load-test harness.

Compares latency and throughput across deployment tiers:

  1. upstream    - direct calls to the upstream API (no AEGIS protection)
  2. aegis       - through the AEGIS gateway (no active ML model)
  3. aegis_ml    - through the AEGIS gateway with an active ML model
  4. aegis_llm   - LLM prompt route through the gateway (LLM scanner runs)
  5. concurrent  - N concurrent workers through the gateway (with ML)

Requests rotate across the seed users (admin, operator, alice, bob, mallory)
and, optionally, additional synthetic load-test users so a single actor does
not trip AEGIS's behavioral rate-abuse defenses (API-013) during the
steady-state (ALLOW path) benchmarks. Sustained burst traffic from a small
set of actors is expected to engage those defenses — see docs/PERFORMANCE.md.

Usage:
    python scripts/loadtest.py [--requests 150] [--concurrency 20]
        [--gateway http://127.0.0.1:8000] [--upstream http://127.0.0.1:8100]
        [--spawn-users 20] [--pace 0.005] [--train-ml] [--json out.json]

Exit code 0 on success.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

SEED_USERS = [
    ("admin", "Admin@1234"),
    ("operator", "Operator@1234"),
    ("alice", "Alice@1234"),
    ("bob", "Bob@1234"),
    ("mallory", "Mallory@1234"),
]

LOADTEST_PASSWORD = "Loadtest@1234"


async def _login(client: httpx.AsyncClient, base: str, username: str, password: str) -> str:
    resp = await client.post(
        f"{base}/api/auth/login",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _spawn_users(client: httpx.AsyncClient, base: str, admin_token: str, n: int) -> int:
    created = 0
    for i in range(1, n + 1):
        body = {
            "username": f"loadtest_u{i}",
            "email": f"loadtest_u{i}@loadtest.local",
            "password": LOADTEST_PASSWORD,
            "role_name": "user",
            "subject_id": 1000 + i,
            "full_name": f"Load Test User {i}",
        }
        resp = await client.post(
            f"{base}/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=body,
        )
        if resp.status_code in (201, 200):
            created += 1
        elif resp.status_code != 409:  # 409 = already exists
            print(f"  warn: spawn user {i} failed: {resp.status_code} {resp.text[:120]}")
    return created


async def train_ml(client: httpx.AsyncClient, base: str, token: str, size: int) -> None:
    resp = await client.post(
        f"{base}/api/ml/train",
        headers={"Authorization": f"Bearer {token}"},
        json={"size": size},
    )
    resp.raise_for_status()
    print(f"  ML model trained: {resp.json().get('name')} v{resp.json().get('version')}")


def _tokens_for(tokens: list[str], i: int) -> str:
    return tokens[i % len(tokens)]


async def bench_serial(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    tokens: list[str] | None,
    json_body: dict | None,
    n: int,
    pace: float,
) -> tuple[list[float], int, float]:
    latencies: list[float] = []
    errors = 0
    start = time.perf_counter()
    for i in range(n):
        headers = {"Authorization": f"Bearer {_tokens_for(tokens, i)}"} if tokens else None
        t0 = time.perf_counter()
        try:
            resp = await client.request(method, url, headers=headers, json=json_body)
            ok = resp.status_code == 200
        except Exception:
            ok = False
        elapsed = (time.perf_counter() - t0) * 1000
        if ok:
            latencies.append(elapsed)
        else:
            errors += 1
        if pace:
            await asyncio.sleep(pace)
    duration = time.perf_counter() - start
    return latencies, errors, duration


async def bench_concurrent(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    tokens: list[str],
    json_body: dict | None,
    n: int,
    workers: int,
) -> tuple[list[float], int, float]:
    sem = asyncio.Semaphore(workers)
    latencies: list[float] = []
    errors = 0

    async def _one(idx: int) -> None:
        nonlocal errors
        headers = {"Authorization": f"Bearer {_tokens_for(tokens, idx)}"}
        async with sem:
            t0 = time.perf_counter()
            try:
                resp = await client.request(method, url, headers=headers, json=json_body)
                ok = resp.status_code == 200
            except Exception:
                ok = False
            elapsed = (time.perf_counter() - t0) * 1000
        if ok:
            latencies.append(elapsed)
        else:
            errors += 1

    start = time.perf_counter()
    await asyncio.gather(*(_one(i) for i in range(n)))
    duration = time.perf_counter() - start
    return latencies, errors, duration


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _stats(latencies: list[float], errors: int, n: int, duration: float) -> dict:
    ok = len(latencies)
    return {
        "requests": n,
        "success": ok,
        "errors": errors,
        "success_rate_pct": round(100.0 * ok / n, 2) if n else 0.0,
        "mean_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "p50_ms": round(_percentile(latencies, 50), 2),
        "p90_ms": round(_percentile(latencies, 90), 2),
        "p95_ms": round(_percentile(latencies, 95), 2),
        "p99_ms": round(_percentile(latencies, 99), 2),
        "max_ms": round(max(latencies), 2) if latencies else None,
        "req_per_s": round(ok / duration, 2) if duration else 0.0,
    }


async def run(args: argparse.Namespace) -> list[dict]:
    gateway = args.gateway.rstrip("/")
    upstream = args.upstream.rstrip("/")
    tokens: list[str] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # admin token for user-spawning and optional ML training
        admin_token = await _login(client, gateway, "admin", args.admin_password)

        if args.train_ml:
            print("Training ML model (admin)...")
            await train_ml(client, gateway, admin_token, args.ml_train_size)
            # give the in-process ML cache a moment to load the artifact
            await asyncio.sleep(2)

        for username, password in SEED_USERS:
            try:
                tokens.append(await _login(client, gateway, username, password))
            except Exception as exc:  # noqa: BLE001
                print(f"  warn: login {username} failed: {exc}")

        if args.spawn_users:
            print(f"Spawning {args.spawn_users} load-test users...")
            created = await _spawn_users(client, gateway, admin_token, args.spawn_users)
            for i in range(1, args.spawn_users + 1):
                try:
                    tokens.append(
                        await _login(client, gateway, f"loadtest_u{i}", LOADTEST_PASSWORD)
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"  warn: login loadtest_u{i} failed: {exc}")
            print(f"  spawned {created}, total actors {len(tokens)}")

        if not tokens:
            print("ERROR: no usable actors; aborting.")
            sys.exit(2)

        results: list[dict] = []

        # warmup (not counted) lets caches/JIT settle
        print("Warming up...")
        for _ in range(10):
            headers = {"Authorization": f"Bearer {_tokens_for(tokens, _)}"}
            try:
                await client.get(f"{gateway}/api/gateway/api/public/products", headers=headers)
            except Exception:
                pass

        print("Bench 1/5  upstream baseline (no AEGIS) ...")
        lat, err, dur = await bench_serial(
            client, "GET", f"{upstream}/api/public/products", None, None, args.requests, args.pace
        )
        results.append({"tier": "upstream", **(_stats(lat, err, args.requests, dur))})

        print("Bench 2/5  through AEGIS (ML unavailable) ...")
        lat, err, dur = await bench_serial(
            client,
            "GET",
            f"{gateway}/api/gateway/api/public/products",
            tokens,
            None,
            args.requests,
            args.pace,
        )
        results.append({"tier": "aegis", **(_stats(lat, err, args.requests, dur))})

        print("Bench 3/5  through AEGIS + ML ...")
        lat, err, dur = await bench_serial(
            client,
            "GET",
            f"{gateway}/api/gateway/api/public/products",
            tokens,
            None,
            args.requests,
            args.pace,
        )
        results.append({"tier": "aegis_ml", **(_stats(lat, err, args.requests, dur))})

        print("Bench 4/5  AEGIS LLM prompt route ...")
        body = {"prompt": "What is the weather in Berlin today?"}
        lat, err, dur = await bench_serial(
            client,
            "POST",
            f"{gateway}/api/gateway/ai/chat",
            tokens,
            body,
            args.requests,
            args.pace,
        )
        results.append({"tier": "aegis_llm", **(_stats(lat, err, args.requests, dur))})

        print(f"Bench 5/5  concurrent ({args.concurrency} workers) ...")
        lat, err, dur = await bench_concurrent(
            client,
            "GET",
            f"{gateway}/api/gateway/api/public/products",
            tokens,
            None,
            args.requests,
            args.concurrency,
        )
        results.append({"tier": "aegis_concurrent", **(_stats(lat, err, args.requests, dur))})

    return results


def _print_table(results: list[dict]) -> None:
    header = (
        f"{'tier':<18} {'success':>8} {'mean':>8} {'p50':>8} {'p90':>8} "
        f"{'p95':>8} {'p99':>8} {'max':>8} {'rps':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['tier']:<18} {r['success_rate_pct']:>7.1f}% {r['mean_ms']:>8.2f} "
            f"{r['p50_ms']:>8.2f} {r['p90_ms']:>8.2f} {r['p95_ms']:>8.2f} "
            f"{r['p99_ms']:>8.2f} {r['max_ms']:>8.2f} {r['req_per_s']:>8.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AEGIS load-test harness")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--gateway", default="http://127.0.0.1:8000")
    parser.add_argument("--upstream", default="http://127.0.0.1:8100")
    parser.add_argument("--admin-password", default="Admin@1234")
    parser.add_argument("--spawn-users", type=int, default=0)
    parser.add_argument("--pace", type=float, default=0.005)
    parser.add_argument("--ml-train-size", type=int, default=5000)
    parser.add_argument("--train-ml", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    results = asyncio.run(run(args))
    _print_table(results)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gateway": args.gateway,
            "upstream": args.upstream,
            "requests": args.requests,
            "concurrency": args.concurrency,
            "spawn_users": args.spawn_users,
            "pace": args.pace,
            "results": results,
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")

    bad = any(r["errors"] for r in results)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
