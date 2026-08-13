# ML V2 — Behavioral Detection Evaluation

**Evaluation type: Controlled synthetic/local telemetry evaluation.**

This document describes the scientifically stronger ML V2 pipeline added alongside the existing V1 demo. V1 is preserved unchanged. Metrics below are **not** evidence of real-world generalization.

---

## 1. V1 audit (preserved, not deleted)

| Component | Location | Notes |
|-----------|----------|-------|
| Feature extraction | `backend/app/ml/features.py` | `features_from_request()` builds 19 request-time features from gateway context + behavior stats |
| Training | `backend/app/ml/pipeline.py` | Isolation Forest + Random Forest on synthetic `dataset.py` |
| Preprocessing | Inline in pipeline | No scaler; raw numeric features |
| Labels | `dataset.py` | `is_attack` from row generator (`normal` vs `attacker` actor types) |
| Model persistence | `pipeline.save_models()` | joblib artifacts + feature list JSON |
| Inference | `backend/app/ml/inference.py` | Loads active registry version; IF + RF ensemble |
| Evaluation | V1 holdout | Random 70/30 index split (`eval_frac=0.3`); IF trained on **full** dataset including test rows |

### V1 feature definitions

See [Feature catalog](#3-feature-catalog) — V1 online inference uses `REQUEST_FEATURES` (19 columns). V1 synthetic data also emits `status_code` and `log_response_size`, stored in `FULL_FEATURES` but **not** used by the online model.

### Leakage risks identified

| Feature | Risk | V2 handling |
|---------|------|-------------|
| `status_code` | HIGH — outcome known only after response | Excluded from training (`LEAKAGE_FEATURES`) |
| `log_response_size` | HIGH — post-response signal | Excluded from training |
| `scenario_id` / direct label columns | HIGH | Never used as features |
| `auth_failures_5min` | Low — correlates with brute force but request-time observable | Kept; documented |
| `prompt_length`, `tool_call_count` | Medium — V1 inference often 0 (train/serve skew) | Documented; V2 generator sets them from simulated traffic |

### V1 limitations (unchanged)

- Artificially separable synthetic rows in `dataset.py`
- Random split only (no temporal or actor holdout)
- Isolation Forest fit on all rows before test evaluation
- Reported API metrics remain a **pipeline demonstration**, not production validation

---

## 2. V2 architecture

New modules (V1 untouched):

| Module | Purpose |
|--------|---------|
| `telemetry_schema.py` | Feature catalog, `FEATURE_VERSION=2.0`, leakage list |
| `traffic_generator.py` | Sequential actor/scenario traffic simulation |
| `baselines.py` | Rule-based baseline |
| `v2_eval.py` | Temporal + unseen-actor splits, metrics |
| `metadata.py` | Model metadata JSON schema |
| `drift.py` | Rolling feature/prediction drift checks |
| `scripts/evaluate_ml_v2.py` | Reproducible evaluation → JSON |

Run evaluation:

```bash
cd backend
python scripts/evaluate_ml_v2.py
# writes docs/benchmarks/ml_v2_eval.json
```

---

## 3. Feature catalog

`FEATURE_VERSION`: **2.0**  
Training/eval feature set: **22 columns** (`V2_FEATURES` = `REQUEST_FEATURES` + 3 extras)

| Feature | Description | Source | Leakage risk |
|---------|-------------|--------|--------------|
| `hour_of_day` | Hour of request (0–23) | Request timestamp | none |
| `day_of_week` | Day of week (0=Mon) | Request timestamp | none |
| `log_request_size` | log1p(body bytes) | Request body size | none |
| `query_param_count` | Number of query parameters | Query string | none |
| `path_depth` | Path segment count | URL path | none |
| `path_length` | Character length of path | URL path | none |
| `user_agent_length` | User-Agent header length | Headers | none |
| `is_authenticated` | 1 if JWT/actor present | Auth context | none |
| `request_rate_per_min` | Requests in trailing minute | Behavior stats | none |
| `unique_endpoints_1h` | Distinct endpoints in trailing hour | Behavior stats | none |
| `auth_failures_5min` | Failed auth count (5 min window) | Behavior stats | low |
| `body_has_sensitive` | PII/secret pattern in body | Pre-ML detection scan | none |
| `body_entropy` | Shannon entropy of body | Body text | none |
| `prompt_length` | Body length on LLM routes | LLM route flag | medium (V1 skew) |
| `tool_call_count` | Tool invocations this request | Request extra | medium (V1 skew) |
| `new_device` | First-seen device for actor | Behavior stats | none |
| `account_age_days` | Days since account created | Behavior stats | none |
| `endpoint_rarity` | 1/(1+endpoint_hits) for actor | Behavior stats | none |
| `payload_max_token_like` | Ratio of long token-like words | Body heuristics | none |
| `is_llm_route` | 1 if path matches LLM routes | Path pattern | none |
| `method_is_write` | 1 if POST/PUT/PATCH/DELETE | HTTP method | none |
| `requests_last_5min` | Request count in trailing 5 minutes | Behavior / simulator | none |

**Excluded from training:** `status_code`, `log_response_size`, `scenario`, `actor_id`, `timestamp`, raw payloads, secrets.

Telemetry schema fields captured in the generator (not all are model inputs): `timestamp`, `endpoint` (path), `method`, `actor_id`, `scenario`, plus derived behavioral counters.

---

## 4. Dataset generation

**Source:** `traffic_generator.generate_traffic_dataset()` — controlled local traffic, not production logs.

**Default size (seed=42):**

| Stat | Value |
|------|-------|
| Total rows | 4,200 |
| Actors | 105 |
| Events per actor | 40 |
| Attack ratio | 23.8% |

**Labeling:** Labels come from **scenario assignment** at actor creation (`is_attack_actor`), not from direct feature thresholds. Each scenario drives realistic request sequences (paths, rates, auth failures, LLM/tool usage).

### Legitimate scenarios

- `normal_browse`, `normal_api`, `normal_llm`, `normal_tool`

### Hard negatives (legitimate but attack-like)

- `hard_negative_high_traffic` — elevated rate, normal endpoints
- `hard_negative_many_endpoints` — high endpoint diversity
- `hard_negative_new_device` — first-seen device
- `hard_negative_unusual_hour` — off-hours access
- `hard_negative_long_prompt` — long but benign LLM prompt

### Attack scenarios

- `attack_enumeration`, `attack_brute_force`, `attack_bola`, `attack_scraping`
- `attack_injection`, `attack_llm_abuse`, `attack_tool_abuse`, `attack_exfil`

Actors are shuffled and assigned random start offsets so attacks are **not** clustered at the end of the timeline (which previously caused single-class training splits).

---

## 5. Split methodology

Implemented in `v2_eval.temporal_actor_split()`:

| Split | Fraction | Rows (default run) | Purpose |
|-------|----------|-------------------|---------|
| Train | 60% (earliest) | 2,520 | Model fitting |
| Validation | 20% | 840 | Threshold tuning (rule baseline) |
| Test | 20% (latest) | 840 | Held-out temporal evaluation |
| Unseen actors | ~15% of actors in test tail | 160 | Actor generalization probe |

**Not used:** random-only shuffled splits for primary metrics.

**Unseen-actor slice caveat:** In the default seed=42 run, the unseen-actor holdout contained **no attack rows** (160 legitimate-only requests). ROC-AUC is undefined for that slice. This is reported honestly rather than omitted.

---

## 6. Baselines and metrics

Threshold: 0.5 for ML models; rule baseline uses score ≥ 0.45.

### Test set (n=840, temporal holdout)

| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | FPR | FNR |
|-------|-----------|--------|-----|---------|--------|-----|-----|
| Rule baseline | 0.294 | 0.950 | 0.449 | 0.793 | 0.803 | 0.912 | 0.050 |
| Isolation Forest | 0.286 | 1.000 | 0.444 | 0.593 | 0.313 | 1.000 | 0.000 |
| Random Forest | **1.000** | 0.442 | **0.613** | **0.732** | 0.696 | **0.000** | 0.558 |
| Gradient Boosting | 1.000 | 0.538 | **0.699** | 0.720 | 0.699 | 0.000 | 0.463 |

*Gradient Boosting = sklearn `GradientBoostingClassifier` (XGBoost not in `requirements.txt`).*

### Confusion matrices (test)

**Rule baseline:** TP=228, FP=547, TN=53, FN=12

**Isolation Forest:** TP=240, FP=600, TN=0, FN=0

**Random Forest:** TP=106, FP=0, TN=600, FN=134

**Gradient Boosting:** TP=129, FP=0, TN=600, FN=111

### Hard negatives (Random Forest, test slice)

| Metric | Value |
|--------|-------|
| Hard-negative rows in test | 200 |
| False-positive rate | **0.0** |

The RF model at threshold 0.5 achieved **0% false-positive rate on the synthetic test slice** (200 hard-negative rows). This is **not** a production guarantee — only an observation on controlled local telemetry at one threshold.

### Inference latency

| Model | Train (ms) | Inference (ms/sample) |
|-------|------------|----------------------|
| Isolation Forest | 430 | 0.20 |
| Random Forest | 444 | 0.47 |
| Gradient Boosting | 1,920 | — |

Full JSON: [`docs/benchmarks/ml_v2_eval.json`](benchmarks/ml_v2_eval.json)

---

## 7. Model versioning

`metadata.py` defines persisted metadata:

- `model_type`, `version`, `trained_at`
- `dataset_version` (`v2-controlled-local`)
- `feature_version` (`2.0`)
- `feature_names`, `training_rows`, `split_methodology`
- `evaluation_metrics`, `algorithm_details`

V1 online inference records `model_version_id`, `model_name`, and `model_algorithm` on each `ModelPrediction` row. V2 metadata helpers are ready for future V2 artifact export; V1 `POST /api/ml/train` path is unchanged.

---

## 8. Fail-safe behavior

When ML is disabled, unloadable, or inference throws:

- `MlPrediction.available = False`
- Risk engine sets `ml_weight = 0` — ML does **not** contribute a low-risk signal
- Deterministic security rules, policy engine, and findings continue
- Metrics: `observe_ml("disabled"|"unavailable"|"error")`

**Does not fail open.** ML error ≠ benign.

Tests: `backend/tests/unit/test_ml_inference_failsafe.py`, `test_risk_engine.py`

---

## 9. Drift / monitoring

`drift.py` — process-local rolling window (500 samples):

- Feature mean shift vs baseline (|z| > 3)
- Anomaly-rate shift (> 0.15 absolute change)
- Prometheus: `observe_ml_drift()` on alert

Inference calls `record_prediction()` after each successful prediction. Not a full MLOps platform — sufficient to demonstrate drift awareness.

Tests: `backend/tests/unit/test_ml_drift.py`

---

## 10. Limitations

1. **Controlled synthetic/local telemetry** — not production or customer traffic.
2. **Labels from scenario type** — not SOC-adjudicated ground truth.
3. **Simulated behavioral stats** — rates/endpoints computed in-generator, not from live Redis/Postgres behavior store at scale.
4. **V1/V2 feature gap** — V2 eval adds `is_llm_route`, `method_is_write`, `requests_last_5min`; V1 online model still uses 19 features only.
5. **Conservative RF threshold** — FPR=0 on test reflects threshold + class separability in simulation, not guaranteed in production.
6. **Unseen-actor slice** — default run lacks attack examples in holdout; actor generalization inconclusive.
7. **No adversarial ML robustness** — evasion attacks not evaluated.
8. **XGBoost** — not installed; GradientBoosting used as substitute.

---

## 11. Synthetic vs real distinction

| Aspect | V1 | V2 |
|--------|----|----|
| Data | Row-wise synthetic (`dataset.py`) | Sequential actor traffic (`traffic_generator.py`) |
| Labels | Direct feature ranges per class | Scenario-driven behavior |
| Split | Random index | Temporal + actor holdout |
| Leakage | Response features in dataframe | Explicitly excluded |
| IF training | Full dataset | Train split only |
| Honest framing | Documented synthetic | **Controlled synthetic/local telemetry evaluation** |

**Do not cite V1 API metrics or V2 benchmark numbers as production detection rates.**

---

## 12. Future real-world dataset plan

1. **Export sanitized telemetry** from gateway audit logs: feature columns only, no raw secrets/payloads.
2. **Label pipeline:** rule-triggered incidents + analyst review queue; weak labels initially.
3. **Strict temporal splits** by deployment week; hold out new tenants/actors.
4. **Recalibrate thresholds** on validation FPR targets (e.g. FPR ≤ 1% at fixed recall).
5. **Close train/serve gap:** ensure `prompt_length`, `tool_call_count`, `requests_last_5min` populated identically online and offline.
6. **Shadow mode:** run V2 models alongside rules; compare without blocking until FPR validated.
7. **Optional:** add `xgboost` to dependencies and re-run baselines on real data.

---

## Related docs

- [ML_EVALUATION.md](ML_EVALUATION.md) — V1 API training overview
- [`backend/app/ml/telemetry_schema.py`](../backend/app/ml/telemetry_schema.py) — canonical feature catalog
- [`backend/tests/unit/test_ml_v2.py`](../backend/tests/unit/test_ml_v2.py) — V2 unit tests
