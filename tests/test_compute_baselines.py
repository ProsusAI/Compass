"""Tests for baseline computation in holdout eval."""

from odysseus.mcp.final_report_tools import _compute_baselines

ROUTES = {
    "haiku": {"cost": 0.1, "quality_score": 0.6},
    "sonnet": {"cost": 0.5, "quality_score": 0.8},
    "opus": {"cost": 1.0, "quality_score": 0.95},
}


def _make_example(eid: str, expected_route: str, routes: dict) -> dict:
    return {"id": eid, "input": f"request {eid}", "expected": {"route": expected_route, "routes": routes}}


def _make_result(eid: str, predicted_route: str) -> dict:
    return {"example_id": eid, "output": {"route": predicted_route}, "error": None}


class TestComputeBaselines:
    def test_identifies_cheapest_and_capable(self) -> None:
        examples = [_make_example(f"e{i}", "sonnet", ROUTES) for i in range(10)]
        results = [_make_result(f"e{i}", "sonnet") for i in range(10)]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        strategies = {b["strategy"]: b for b in baselines["baselines"]}
        assert strategies["always_cheapest"]["route"] == "haiku"
        assert strategies["always_capable"]["route"] == "opus"

    def test_optimized_uses_actual_results(self) -> None:
        examples = [
            _make_example("e0", "haiku", ROUTES),
            _make_example("e1", "opus", ROUTES),
        ]
        results = [
            _make_result("e0", "haiku"),
            _make_result("e1", "sonnet"),
        ]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        opt = baselines["optimized"]
        assert opt["cost"] == round((0.1 + 0.5) / 2, 4)
        assert opt["quality_score"] == round((0.6 + 0.8) / 2, 4)

    def test_empty_examples_returns_none(self) -> None:
        assert _compute_baselines([], []) is None

    def test_skips_errored_results(self) -> None:
        examples = [_make_example("e0", "sonnet", ROUTES)]
        results = [{"example_id": "e0", "output": None, "error": "timeout"}]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        assert baselines["optimized"]["cost"] == 0.0
