# tests/test_data_validation_split.py
"""Tests for route-only stratified split."""

import inspect

from compass.agents.data_validation.split import (
    SplitReport,
    compute_dataset_hash,
    stratified_split,
)
from compass.eval.models import Example, Expected, ModelCostQuality


def _make_example(eid: str, route: str) -> Example:
    return Example(
        id=eid,
        input=f"query for {eid}",
        expected=Expected(route=route, routes={route: ModelCostQuality(cost=0.01)}),
    )


def _make_examples(route_counts: dict[str, int]) -> list[Example]:
    examples = []
    i = 0
    for route, count in route_counts.items():
        for _ in range(count):
            examples.append(_make_example(f"ex_{i}", route))
            i += 1
    return examples


class TestComputeDatasetHash:
    def test_deterministic(self):
        examples = _make_examples({"simple": 3, "complex": 2})
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(examples)
        assert h1 == h2

    def test_order_independent(self):
        examples = _make_examples({"simple": 3, "complex": 2})
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(list(reversed(examples)))
        assert h1 == h2

    def test_returns_16_hex_chars(self):
        examples = _make_examples({"simple": 3})
        h = compute_dataset_hash(examples)
        assert len(h) == 16
        int(h, 16)  # validates hex


class TestStratifiedSplit:
    def test_basic_split(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, report = stratified_split(examples)
        assert len(dev) + len(holdout) == 20
        assert len(holdout) > 0

    def test_preserves_route_distribution(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, report = stratified_split(examples)
        dev_routes = {e.expected.route for e in dev}
        holdout_routes = {e.expected.route for e in holdout}
        assert "simple" in dev_routes
        assert "complex" in dev_routes
        assert "simple" in holdout_routes or "complex" in holdout_routes

    def test_deterministic(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev1, holdout1, _ = stratified_split(examples)
        dev2, holdout2, _ = stratified_split(examples)
        assert [e.id for e in dev1] == [e.id for e in dev2]
        assert [e.id for e in holdout1] == [e.id for e in holdout2]

    def test_singletons_go_to_dev(self):
        examples = _make_examples({"simple": 10, "rare": 1})
        dev, holdout, _ = stratified_split(examples)
        rare_in_dev = [e for e in dev if e.expected.route == "rare"]
        rare_in_holdout = [e for e in holdout if e.expected.route == "rare"]
        assert len(rare_in_dev) == 1
        assert len(rare_in_holdout) == 0

    def test_split_report_structure(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        _, _, report = stratified_split(examples)
        assert isinstance(report, SplitReport)
        assert report.dev_count + report.holdout_count == 20

    def test_no_rationale_cards_in_signature(self):
        """Split function does not accept rationale card parameters."""
        sig = inspect.signature(stratified_split)
        param_names = set(sig.parameters.keys())
        assert "card_set" not in param_names
        assert "cards" not in param_names
        assert "rationale" not in param_names

    def test_custom_dev_ratio(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, _ = stratified_split(examples, dev_ratio=0.5)
        assert len(dev) + len(holdout) == 20
        assert len(holdout) >= 8  # roughly 50%
