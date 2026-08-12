# Attack Lab

## Purpose

Automated adversarial scenarios against a running AEGIS gateway + mock upstream.

## Run

```powershell
# Ensure backend (:8000) and mock-api (:8100) are running
cd attack_lab\scripts
..\..\backend\.venv\Scripts\python.exe run_all.py
```

Exit code 0 = all scenarios PASS.

**CI:** GitHub Actions job `attack-lab` runs `run_all.py` and `bypass_tests/run_bypass.py` against PostgreSQL + mock-api + seeded AEGIS gateway (no AWS, no external LLM).

**Latest verification (2026-08-13):** 16/16 PASS on direct dev stack and Docker Compose backend. Evidence: `docs/verification/attack_lab_results.json`.

## Scenarios (16)

Includes: legitimate traffic, API enumeration, BOLA, SQLi, SSRF, command injection, path traversal, admin probing, prompt injection, jailbreak, output redaction, unauthorized tool, cross-subject tool, payment approval, brute-force rate limit, incident correlation.

## Strict validation

`run_all.py` requires expected HTTP status codes and decision types — a `401` on brute-force does **not** count as rate-limit success.

## Results

Output written to `attack_lab_results.json` (gitignored, regenerated each run).

## Bypass suite

Additional tests in `attack_lab/bypass_tests/run_bypass.py` for regression of known bypass classes.
