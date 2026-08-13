# ML Evaluation (V1)

**Dataset: SYNTHETIC**

This page describes the **original V1 ML demo** exposed via `POST /api/ml/train` and the dashboard. For the scientifically stronger V2 pipeline (temporal splits, baselines, hard negatives, drift), see **[ML_V2_EVALUATION.md](ML_V2_EVALUATION.md)**.

## Models

| Algorithm | Purpose | Status |
|-----------|---------|--------|
| Isolation Forest | Unsupervised anomaly detection | REAL |
| Random Forest | Supervised classification | REAL |

## Training data

Generated synthetically in `backend/app/ml/dataset.py` (not `training.py`). Features include request rates, endpoint diversity, auth failures, timing, and body heuristics. Classes are artificially separable for demonstration.

Response-derived columns (`status_code`, `log_response_size`) exist in the dataframe but are **not** used by online inference (`REQUEST_FEATURES` only).

**Do not interpret reported accuracy as real-world performance.**

## Metrics

Returned by `GET /api/ml/models` after training via `POST /api/ml/train`. Example fields: accuracy, precision, recall, f1, ROC-AUC (when computed on synthetic holdout).

Evaluation uses a random 70/30 index split in `backend/app/ml/pipeline.py`. Isolation Forest is fit on the full dataset before test scoring — a known methodological limitation documented in V2.

## Evaluation method

1. Train with `POST /api/ml/train` (default 20,000 samples)
2. Inspect metrics in API response or ML page
3. Reproduce V2 benchmarks: `cd backend && python scripts/evaluate_ml_v2.py`
4. Performance impact measured in [PERFORMANCE.md](PERFORMANCE.md) (~15ms inference overhead when model active)

## Limitations

- No production traffic dataset
- Random split only (V2 adds temporal + actor holdout)
- Train/serve skew on some features at inference time
- No adversarial ML robustness testing
- Model artifacts stored locally (`ML_MODEL_DIR`) or Docker volume

See [ML_V2_EVALUATION.md](ML_V2_EVALUATION.md) for leakage audit, fail-safe behavior, drift monitoring, and controlled local telemetry evaluation.
