# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Data validation — format detection, field mapping, quality checks."""

from __future__ import annotations

from compass.agents.data_validation.checks import (
    DataQualityReport,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
    run_all_checks,
)
from compass.agents.data_validation.detect import (
    DetectionResult,
    detect_and_parse,
)
from compass.agents.data_validation.split import (
    SplitReport,
    compute_dataset_hash,
    stratified_split,
)
from compass.agents.data_validation.transform import (
    AddIdsResult,
    TransformResult,
    add_ids_to_dataset,
    transform_dataset,
)

__all__ = [
    "AddIdsResult",
    "DataQualityReport",
    "DetectionResult",
    "LabelDistribution",
    "QueryLengthDistribution",
    "SchemaFinding",
    "SplitReport",
    "TierDistribution",
    "TierVolume",
    "TransformResult",
    "VolumeAssessment",
    "add_ids_to_dataset",
    "check_label_distribution",
    "check_query_length_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
    "compute_dataset_hash",
    "detect_and_parse",
    "run_all_checks",
    "stratified_split",
    "transform_dataset",
]
