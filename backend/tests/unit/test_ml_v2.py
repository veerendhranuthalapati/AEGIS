"""ML V2 traffic generator and evaluation tests."""
from __future__ import annotations

from app.ml.baselines import rule_based_predict
from app.ml.traffic_generator import generate_traffic_dataset
from app.ml.v2_eval import evaluate_v2_dataset, temporal_actor_split


def test_traffic_generator_produces_labeled_rows() -> None:
    df = generate_traffic_dataset(
        events_per_actor=10,
        n_legit_actors=5,
        n_attack_actors=3,
        n_hard_negative_actors=2,
        seed=1,
    )
    assert len(df) == 100
    assert "is_attack" in df.columns
    assert "actor_id" in df.columns
    assert "timestamp" in df.columns
    assert df["is_attack"].sum() > 0
    assert (df["is_attack"] == 0).sum() > 0


def test_temporal_split_no_overlap() -> None:
    df = generate_traffic_dataset(seed=2)
    splits = temporal_actor_split(df)
    assert len(splits.train) + len(splits.val) + len(splits.test) == len(df)
    assert splits.train.max() < splits.val.min()
    assert splits.val.max() < splits.test.min()


def test_hard_negatives_mostly_benign_labels() -> None:
    df = generate_traffic_dataset(seed=3)
    hard = df[df["scenario"].str.startswith("hard_negative")]
    assert len(hard) > 0
    assert hard["is_attack"].mean() == 0.0


def test_v2_evaluation_runs() -> None:
    df = generate_traffic_dataset(
        events_per_actor=8,
        n_legit_actors=8,
        n_attack_actors=4,
        n_hard_negative_actors=4,
        seed=4,
    )
    results = evaluate_v2_dataset(df, seed=4)
    assert results["evaluation_type"] == "Controlled synthetic/local telemetry evaluation"
    assert "random_forest" in results
    assert "rule_baseline" in results
    assert "isolation_forest" in results
    rf = results["random_forest"]["test"]
    assert "f1" in rf
    assert "roc_auc" in rf
    assert "pr_auc" in rf
    assert "confusion_matrix" in rf


def test_rule_baseline_detects_some_attacks() -> None:
    df = generate_traffic_dataset(seed=5)
    preds = rule_based_predict(df)
    assert preds.sum() > 0
