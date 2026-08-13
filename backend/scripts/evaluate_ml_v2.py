#!/usr/bin/env python3
"""Run ML V2 evaluation and write JSON results.

Usage:
    python scripts/evaluate_ml_v2.py
    python scripts/evaluate_ml_v2.py --output ../docs/benchmarks/ml_v2_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ml.traffic_generator import generate_traffic_dataset
from app.ml.v2_eval import evaluate_v2_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate AEGIS ML V2 pipeline")
    parser.add_argument(
        "--output",
        default=str(ROOT.parent / "docs" / "benchmarks" / "ml_v2_eval.json"),
        help="Path for JSON metrics output",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("Generating controlled local traffic dataset...")
    df = generate_traffic_dataset(seed=args.seed)
    print(f"  rows={len(df)} actors={df['actor_id'].nunique()} attack_ratio={df['is_attack'].mean():.3f}")

    print("Running V2 evaluation (temporal split + baselines)...")
    results = evaluate_v2_dataset(df, seed=args.seed)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out}")

    rf = results.get("random_forest", {}).get("test", {})
    rule = results.get("rule_baseline", {}).get("test", {})
    print("\n--- Test set summary ---")
    print(f"Rule baseline F1:        {rule.get('f1', 'n/a')}")
    print(f"Random Forest F1:        {rf.get('f1', 'n/a')}")
    print(f"Random Forest ROC-AUC:   {rf.get('roc_auc', 'n/a')}")
    print(f"Random Forest FPR:       {rf.get('false_positive_rate', 'n/a')}")
    if "hard_negative_false_positive_rate_rf" in results:
        print(f"Hard-negative FPR (RF):  {results['hard_negative_false_positive_rate_rf']}")


if __name__ == "__main__":
    main()
