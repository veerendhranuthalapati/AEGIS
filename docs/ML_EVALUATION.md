# ML Evaluation

**Dataset: SYNTHETIC**

## Models

| Algorithm | Purpose | Status |
|-----------|---------|--------|
| Isolation Forest | Unsupervised anomaly detection | REAL |
| Random Forest | Supervised classification | REAL |

## Training data

Generated synthetically in `backend/app/ml/training.py`. Features include request rates, error ratios, endpoint diversity, and timing patterns. Classes are artificially separable for demonstration.

**Do not interpret reported accuracy as real-world performance.**

## Metrics

Returned by `GET /api/ml/models` after training via `POST /api/ml/train`. Example fields: accuracy, precision, recall, f1 (when computed on synthetic holdout).

## Evaluation method

1. Train with `POST /api/ml/train` (default 20,000 samples)
2. Inspect metrics in API response or ML page
3. Performance impact measured in [PERFORMANCE.md](PERFORMANCE.md) (~15ms inference overhead when model active)

## Limitations

- No production traffic dataset
- No adversarial ML robustness testing
- Model artifacts stored locally (`ML_MODEL_DIR`) or Docker volume
