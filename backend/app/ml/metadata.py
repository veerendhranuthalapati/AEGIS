"""Model metadata persistence for ML V2."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ModelMetadata:
    model_type: str
    version: int
    trained_at: str
    dataset_version: str
    feature_version: str
    feature_names: list[str]
    training_rows: int
    split_methodology: str
    evaluation_metrics: dict[str, Any]
    algorithm_details: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelMetadata":
        return cls(**data)


def write_metadata(path: Path, metadata: ModelMetadata) -> None:
    path.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")


def read_metadata(path: Path) -> ModelMetadata | None:
    if not path.exists():
        return None
    return ModelMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_metadata(
    *,
    version: int,
    feature_names: list[str],
    training_rows: int,
    evaluation_metrics: dict[str, Any],
) -> ModelMetadata:
    from app.ml.telemetry_schema import DATASET_VERSION, FEATURE_VERSION

    return ModelMetadata(
        model_type="isolation_forest+random_forest",
        version=version,
        trained_at=datetime.now(timezone.utc).isoformat(),
        dataset_version=DATASET_VERSION,
        feature_version=FEATURE_VERSION,
        feature_names=feature_names,
        training_rows=training_rows,
        split_methodology="temporal 60/20/20 + unseen-actor holdout",
        evaluation_metrics=evaluation_metrics,
        algorithm_details={
            "isolation_forest": "sklearn IsolationForest n_estimators=200 contamination=0.15",
            "random_forest": "sklearn RandomForestClassifier n_estimators=200 max_depth=14",
        },
    )
