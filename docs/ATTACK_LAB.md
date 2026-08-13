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

**Latest verification (2026-08-13):** Strict assertions added in `scenario_expectations.py`. Live re-run against Docker stack: **NOT VERIFIED** (Docker daemon unavailable on audit host). Prior 16/16 results used permissive criteria — see `AUDIT_REMEDIATION_REPORT.md`.

## Scenarios (16)

Includes: legitimate traffic, API enumeration, BOLA, SQLi, SSRF, command injection, path traversal, admin probing, prompt injection, jailbreak, output redaction, unauthorized tool, cross-subject tool, payment approval, brute-force rate limit, incident correlation.

## Strict validation

`run_all.py` uses `scenario_expectations.py` to require, per scenario:

- Expected HTTP status code(s)
- Expected security `decision` (e.g. `BLOCK`, `REQUIRE_REVIEW`)
- Expected `rule_id`(s) or reason substrings — **wrong-reason blocks fail** (e.g. SQLi payload blocked by auth failure)
- Brute force: ≥10 failed logins (401) then rate limit (429)

Infrastructure failures (connection errors, 5xx without security decision) do **not** count as PASS.

## Results

Output written to `attack_lab_results.json` (gitignored, regenerated each run).

## Bypass suite

Additional tests in `attack_lab/bypass_tests/run_bypass.py` for regression of known bypass classes.
