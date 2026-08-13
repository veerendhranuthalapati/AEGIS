# ML V1 — Isolation Forest Train/Test Leakage Fix

**Date:** 2026-08-13  
**Status:** FIXED in `backend/app/ml/pipeline.py`

---

## The flaw

V1 training (`train_models` in `pipeline.py`) used a random 70/30 index split for Random Forest evaluation, but **Isolation Forest was fit on the full feature matrix `X`**, including rows reserved for the test split.

That means IF anomaly scores on the holdout set were computed from a model that had **already seen those rows during fit**. Offline IF metrics (precision, recall, ROC-AUC in API train response) were **optimistically biased**.

Random Forest was **not** affected — it correctly used `X_train` only.

---

## Why previous results were invalid (for IF only)

- Unsupervised IF does not use labels, but seeing test-row feature distributions during fit still leaks structural information about the evaluation set.
- Reported `isolation_forest.*` metrics from `POST /api/ml/train` could not be interpreted as honest generalization estimates.

RF metrics remained structurally valid (train/test split respected) but still reflect **synthetic data only**.

---

## Fix applied

```python
# Before (invalid):
iforest.fit(X)

# After (valid):
iforest.fit(X_train)
```

Metrics metadata now includes `"isolation_forest_trained_on": "train_split_only"`.

---

## Before / after

| Aspect | Before | After |
|--------|--------|-------|
| IF training data | Full dataset | Train split only |
| RF training data | Train split | Unchanged |
| Online inference | V1 artifacts via `/api/ml/train` | Unchanged |
| ML V2 | Offline eval only (`evaluate_ml_v2.py`) | **Still offline-only** — not wired to `/api/ml/train` or live inference |

Re-run `POST /api/ml/train` after deploy to regenerate artifacts. IF metrics may **decrease** — that is expected and honest.

---

## ML V2 status

ML V2 (`traffic_generator.py`, `v2_eval.py`) remains **evaluation-only**. It does not replace V1 online models unless explicitly integrated in a future phase.
