"""Tests for odysseus.agents.routing_rationale_checks (THP-82)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteDefinition,
    RouteExclusion,
    RoutingContext,
    RoutingDimension,
    VocabularyEntry,
    VocabularyRegistry,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_registry(
    intent_patterns: list[str] | None = None,
    complexity_structures: list[str] | None = None,
    ambiguity_tags: list[str] | None = None,
    example_ids_per_entry: int = 4,
) -> VocabularyRegistry:
    """Build a VocabularyRegistry from simple name lists."""
    ip_names = intent_patterns or ["data-analysis"]
    cs_names = complexity_structures or ["multi-step-reasoning"]
    at_names = ambiguity_tags or ["AMBIGUOUS_SCOPE"]
    eids = [f"ex-{i:03d}" for i in range(example_ids_per_entry)]

    return VocabularyRegistry(
        intent_pattern=[VocabularyEntry(name=n, definition=f"Def for {n}", example_ids=eids) for n in ip_names],
        complexity_structure=[VocabularyEntry(name=n, definition=f"Def for {n}", example_ids=eids) for n in cs_names],
        ambiguity_tags=[VocabularyEntry(name=n, definition=f"Def for {n}", example_ids=eids) for n in at_names],
    )


def _make_card(
    example_id: str = "ex-001",
    assigned_route: str = "claude-sonnet",
    intent_pattern: str = "data-analysis",
    complexity_structure: str = "multi-step-reasoning",
    route_exclusions: list[RouteExclusion] | None = None,
    ambiguity_tags: list[str] | None = None,
) -> RationaleCard:
    if route_exclusions is None:
        route_exclusions = [
            RouteExclusion(route="claude-haiku", reason="Requires nuanced reasoning"),
            RouteExclusion(route="claude-opus", reason="Overkill for this task"),
        ]
    return RationaleCard(
        example_id=example_id,
        assigned_route=assigned_route,
        intent_pattern=intent_pattern,
        complexity_structure=complexity_structure,
        route_exclusions=route_exclusions,
        ambiguity_tags=ambiguity_tags or ["AMBIGUOUS_SCOPE"],
    )


def _make_card_set(
    cards: dict[str, RationaleCard] | None = None,
    registry: VocabularyRegistry | None = None,
) -> RationaleCardSet:
    if cards is None:
        cards = {"ex-001": _make_card()}
    if registry is None:
        registry = _make_registry(example_ids_per_entry=4)
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc123",
        registry=registry,
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )


AVAILABLE_ROUTES = {"claude-haiku", "claude-sonnet", "claude-opus"}

_TEST_ROUTING_CONTEXT = RoutingContext(
    domain="LLM tier routing. Queries span general knowledge.",
    routes=[
        RouteDefinition(name="haiku", description="Fast model"),
        RouteDefinition(name="sonnet", description="Balanced model"),
        RouteDefinition(name="opus", description="Capable model"),
    ],
    routing_dimensions=[
        RoutingDimension(name="cost", direction="lower_is_better", description="Cost"),
    ],
)


# A judge_fn that never finds overlap (for non-overlap tests)
async def _no_overlap_judge(a: str, b: str) -> bool:
    return False


# A judge_fn that always finds overlap
async def _always_overlap_judge(a: str, b: str) -> bool:
    return True


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from odysseus.agents.routing_rationale_checks import (  # noqa: E402
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
    validate_rationale_card_set,
)

# ---------------------------------------------------------------------------
# RationaleCheckResult model
# ---------------------------------------------------------------------------


class TestRationaleCheckResult:
    def test_valid_result(self) -> None:
        r = RationaleCheckResult(
            passed=True,
            check_name="check_required_fields",
            severity="critical",
            details="All fields present",
            affected_ids=[],
        )
        assert r.passed is True
        assert r.check_name == "check_required_fields"
        assert r.severity == "critical"
        assert r.details == "All fields present"
        assert r.affected_ids == []

    def test_failed_result_with_affected_ids(self) -> None:
        r = RationaleCheckResult(
            passed=False,
            check_name="check_vocabulary_membership",
            severity="critical",
            details="Unknown intent_pattern",
            affected_ids=["ex-001", "ex-002"],
        )
        assert r.passed is False
        assert r.affected_ids == ["ex-001", "ex-002"]

    def test_invalid_severity_rejected(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            RationaleCheckResult(  # type: ignore[call-arg]
                passed=True,
                check_name="foo",
                severity="bad-severity",
                details="",
                affected_ids=[],
            )

    def test_all_severity_literals_accepted(self) -> None:
        for sev in ("critical", "warning", "info"):
            r = RationaleCheckResult(
                passed=True,
                check_name="x",
                severity=sev,
                details="",
                affected_ids=[],  # type: ignore[arg-type]
            )
            assert r.severity == sev


# ---------------------------------------------------------------------------
# check_required_fields
# ---------------------------------------------------------------------------


class TestCheckRequiredFields:
    def test_valid_card_passes(self) -> None:
        registry = _make_registry()
        card = _make_card()
        result = check_required_fields(card, registry)
        assert result.passed is True
        assert result.severity == "critical"
        assert result.check_name == "check_required_fields"
        assert result.affected_ids == []

    def test_empty_assigned_route_fails(self) -> None:
        # Bypass pydantic validation by constructing via model_construct
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_required_fields(card, registry)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_empty_intent_pattern_fails(self) -> None:
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-002",
            assigned_route="claude-sonnet",
            intent_pattern="",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_required_fields(card, registry)
        assert result.passed is False

    def test_empty_complexity_structure_fails(self) -> None:
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-003",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_required_fields(card, registry)
        assert result.passed is False

    def test_empty_ambiguity_tags_is_allowed(self) -> None:
        """ambiguity_tags can be [] — not a missing field."""
        registry = _make_registry()
        card = _make_card(ambiguity_tags=[])
        result = check_required_fields(card, registry)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_vocabulary_membership
# ---------------------------------------------------------------------------


class TestCheckVocabularyMembership:
    def test_valid_card_passes(self) -> None:
        registry = _make_registry()
        card = _make_card()
        result = check_vocabulary_membership(card, registry)
        assert result.passed is True
        assert result.severity == "critical"

    def test_unknown_intent_pattern_fails(self) -> None:
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="unknown-pattern",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_vocabulary_membership(card, registry)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_unknown_complexity_structure_fails(self) -> None:
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="nonexistent-structure",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_vocabulary_membership(card, registry)
        assert result.passed is False

    def test_both_missing_fails(self) -> None:
        registry = _make_registry()
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="foo",
            complexity_structure="bar",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        result = check_vocabulary_membership(card, registry)
        assert result.passed is False


# ---------------------------------------------------------------------------
# check_exclusion_coverage
# ---------------------------------------------------------------------------


class TestCheckExclusionCoverage:
    def test_full_coverage_passes(self) -> None:
        card = _make_card(
            assigned_route="claude-sonnet",
            route_exclusions=[
                RouteExclusion(route="claude-haiku", reason="Too weak"),
                RouteExclusion(route="claude-opus", reason="Overkill"),
            ],
        )
        result = check_exclusion_coverage(card, AVAILABLE_ROUTES)
        assert result.passed is True
        assert result.severity == "critical"

    def test_missing_exclusion_fails(self) -> None:
        card = _make_card(
            assigned_route="claude-sonnet",
            # Only covers haiku, not opus
            route_exclusions=[
                RouteExclusion(route="claude-haiku", reason="Too weak"),
            ],
        )
        result = check_exclusion_coverage(card, AVAILABLE_ROUTES)
        assert result.passed is False
        assert card.example_id in result.affected_ids

    def test_no_exclusions_needed_when_single_route(self) -> None:
        """If assigned route is the only route, no exclusions needed."""
        card = _make_card(
            assigned_route="claude-sonnet",
            route_exclusions=[],
        )
        result = check_exclusion_coverage(card, {"claude-sonnet"})
        assert result.passed is True

    def test_empty_available_routes_passes(self) -> None:
        """Edge case: no available routes means nothing to exclude."""
        card = _make_card(assigned_route="claude-sonnet", route_exclusions=[])
        result = check_exclusion_coverage(card, set())
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_exclusion_format
# ---------------------------------------------------------------------------


class TestCheckExclusionFormat:
    def test_valid_exclusions_pass(self) -> None:
        card = _make_card()
        result = check_exclusion_format(card)
        assert result.passed is True
        assert result.severity == "critical"

    def test_empty_route_in_exclusion_fails(self) -> None:
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[
                RouteExclusion.model_construct(route="", reason="some reason"),
            ],
            ambiguity_tags=[],
        )
        result = check_exclusion_format(card)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_empty_reason_in_exclusion_fails(self) -> None:
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[
                RouteExclusion.model_construct(route="claude-haiku", reason=""),
            ],
            ambiguity_tags=[],
        )
        result = check_exclusion_format(card)
        assert result.passed is False

    def test_no_exclusions_passes(self) -> None:
        card = _make_card(route_exclusions=[])
        result = check_exclusion_format(card)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_ambiguity_tag_membership
# ---------------------------------------------------------------------------


class TestCheckAmbiguityTagMembership:
    def test_valid_tags_pass(self) -> None:
        registry = _make_registry(ambiguity_tags=["AMBIGUOUS_SCOPE"])
        card = _make_card(ambiguity_tags=["AMBIGUOUS_SCOPE"])
        result = check_ambiguity_tag_membership(card, registry)
        assert result.passed is True
        assert result.severity == "warning"

    def test_unknown_tag_fails(self) -> None:
        registry = _make_registry(ambiguity_tags=["AMBIGUOUS_SCOPE"])
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=["UNKNOWN_TAG"],
        )
        result = check_ambiguity_tag_membership(card, registry)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_empty_tags_passes(self) -> None:
        registry = _make_registry()
        card = _make_card(ambiguity_tags=[])
        result = check_ambiguity_tag_membership(card, registry)
        assert result.passed is True

    def test_empty_registry_with_tags_fails(self) -> None:
        registry = _make_registry(ambiguity_tags=[])
        # We need to bypass the VocabularyRegistry validator that enforces
        # SCREAMING_SNAKE for ambiguity_tags — but registry itself is fine
        # (empty list is OK). The card has a tag not in the empty registry.
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=["SOME_TAG"],
        )
        result = check_ambiguity_tag_membership(card, registry)
        assert result.passed is False


# ---------------------------------------------------------------------------
# check_cluster_thresholds
# ---------------------------------------------------------------------------


class TestCheckClusterThresholds:
    def test_all_entries_above_threshold_pass(self) -> None:
        # dataset_size=100, threshold = max(3, ceil(0.05*100)) = max(3,5) = 5
        # Each entry has 6 example_ids — passes
        registry = _make_registry(example_ids_per_entry=6)
        result = check_cluster_thresholds(registry, dataset_size=100)
        assert result.passed is True
        assert result.severity == "warning"

    def test_entry_below_threshold_fails(self) -> None:
        # dataset_size=100, threshold=5
        # Each entry has only 3 example_ids — fails
        registry = _make_registry(example_ids_per_entry=3)
        result = check_cluster_thresholds(registry, dataset_size=100)
        assert result.passed is False

    def test_small_dataset_uses_minimum_3(self) -> None:
        # dataset_size=10, threshold = max(3, ceil(0.05*10)) = max(3,1) = 3
        # Entry has exactly 3 example_ids — passes
        registry = _make_registry(example_ids_per_entry=3)
        result = check_cluster_thresholds(registry, dataset_size=10)
        assert result.passed is True

    def test_entry_with_2_ids_fails_min_threshold(self) -> None:
        # dataset_size=10, threshold=3
        # Entry has only 2 example_ids — fails
        registry = _make_registry(example_ids_per_entry=2)
        result = check_cluster_thresholds(registry, dataset_size=10)
        assert result.passed is False

    def test_empty_registry_passes(self) -> None:
        """Empty registry (no entries at all) has nothing to fail."""
        registry = VocabularyRegistry(intent_pattern=[], complexity_structure=[], ambiguity_tags=[])
        result = check_cluster_thresholds(registry, dataset_size=100)
        assert result.passed is True

    def test_affected_ids_contain_entry_names(self) -> None:
        registry = _make_registry(
            intent_patterns=["data-analysis", "code-generation"],
            example_ids_per_entry=1,
        )
        result = check_cluster_thresholds(registry, dataset_size=100)
        assert result.passed is False
        # Both entries fail
        assert "data-analysis" in result.affected_ids
        assert "code-generation" in result.affected_ids


# ---------------------------------------------------------------------------
# check_pruning_cleanup
# ---------------------------------------------------------------------------


class TestCheckPruningCleanup:
    def test_all_references_consistent_passes(self) -> None:
        card_set = _make_card_set()
        result = check_pruning_cleanup(card_set)
        assert result.passed is True
        assert result.severity == "critical"

    def test_card_referencing_missing_intent_pattern_fails(self) -> None:
        # Registry has "data-analysis", but card uses "code-generation"
        registry = _make_registry(intent_patterns=["data-analysis"])
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="code-generation",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)
        result = check_pruning_cleanup(card_set)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_card_referencing_missing_complexity_structure_fails(self) -> None:
        registry = _make_registry(complexity_structures=["multi-step-reasoning"])
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="unknown-structure",
            route_exclusions=[],
            ambiguity_tags=[],
        )
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)
        result = check_pruning_cleanup(card_set)
        assert result.passed is False

    def test_card_referencing_missing_ambiguity_tag_fails(self) -> None:
        registry = _make_registry(ambiguity_tags=["AMBIGUOUS_SCOPE"])
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="data-analysis",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[],
            ambiguity_tags=["DELETED_TAG"],
        )
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)
        result = check_pruning_cleanup(card_set)
        assert result.passed is False

    def test_empty_card_set_passes(self) -> None:
        card_set = _make_card_set(cards={})
        result = check_pruning_cleanup(card_set)
        assert result.passed is True


# ---------------------------------------------------------------------------
# find_orphaned_examples
# ---------------------------------------------------------------------------


class TestFindOrphanedExamples:
    def test_no_orphans_when_registry_up_to_date(self) -> None:
        # Registry entries include ex-000..ex-003; card is ex-001
        # _make_card_set() uses _make_registry(example_ids_per_entry=4) internally
        card_set = _make_card_set()
        result = find_orphaned_examples(card_set)
        assert result.passed is True
        assert result.severity == "warning"
        assert result.affected_ids == []

    def test_example_not_in_any_registry_entry_is_orphaned(self) -> None:
        # Build registry with example_ids that DON'T include the card's ID
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(
                    name="data-analysis",
                    definition="Data tasks.",
                    example_ids=["other-001"],  # does NOT include ex-001
                )
            ],
            complexity_structure=[
                VocabularyEntry(
                    name="multi-step-reasoning",
                    definition="Reasoning.",
                    example_ids=["other-001"],
                )
            ],
            ambiguity_tags=[
                VocabularyEntry(
                    name="AMBIGUOUS_SCOPE",
                    definition="Scope unclear.",
                    example_ids=["other-001"],
                )
            ],
        )
        card = _make_card(example_id="ex-001")
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)
        result = find_orphaned_examples(card_set)
        assert result.passed is False
        assert "ex-001" in result.affected_ids

    def test_empty_card_set_no_orphans(self) -> None:
        card_set = _make_card_set(cards={})
        result = find_orphaned_examples(card_set)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_registry_consistency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCheckRegistryConsistency:
    async def test_no_overlap_passes(self) -> None:
        registry = _make_registry(
            intent_patterns=["data-analysis", "code-generation"],
        )
        result = await check_registry_consistency(registry, _no_overlap_judge)
        assert result.passed is True
        assert result.severity == "warning"

    async def test_overlap_detected_fails(self) -> None:
        registry = _make_registry(
            intent_patterns=["data-analysis", "code-generation"],
        )
        result = await check_registry_consistency(registry, _always_overlap_judge)
        assert result.passed is False

    async def test_single_entry_no_pairs_to_check(self) -> None:
        """With one entry per vocabulary, no pairs exist — always passes."""
        registry = _make_registry()  # single entry per vocab
        result = await check_registry_consistency(registry, _always_overlap_judge)
        # No pairs to compare → passes regardless of judge
        assert result.passed is True

    async def test_empty_registry_passes(self) -> None:
        registry = VocabularyRegistry(intent_pattern=[], complexity_structure=[], ambiguity_tags=[])
        result = await check_registry_consistency(registry, _always_overlap_judge)
        assert result.passed is True

    async def test_affected_ids_contain_overlapping_entry_names(self) -> None:
        registry = _make_registry(
            intent_patterns=["data-analysis", "code-generation"],
        )
        result = await check_registry_consistency(registry, _always_overlap_judge)
        assert result.passed is False
        # At least one of the overlapping pair names should appear
        assert len(result.affected_ids) > 0


# ---------------------------------------------------------------------------
# validate_rationale_card_set (top-level runner)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestValidateRationaleCardSet:
    async def test_clean_card_set_all_pass(self) -> None:
        card = _make_card(
            assigned_route="sonnet",
            route_exclusions=[
                RouteExclusion(route="haiku", reason="Too weak"),
                RouteExclusion(route="opus", reason="Overkill"),
            ],
            ambiguity_tags=["AMBIGUOUS_SCOPE"],
        )
        registry = _make_registry(
            intent_patterns=["data-analysis"],
            complexity_structures=["multi-step-reasoning"],
            ambiguity_tags=["AMBIGUOUS_SCOPE"],
            example_ids_per_entry=6,
        )
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)

        results = await validate_rationale_card_set(
            card_set=card_set,
            routing_context=_TEST_ROUTING_CONTEXT,
            dataset_size=100,
            judge_fn=_no_overlap_judge,
        )

        assert isinstance(results, list)
        assert all(isinstance(r, RationaleCheckResult) for r in results)
        failed = [r for r in results if not r.passed]
        assert failed == [], f"Expected all checks to pass but got: {[r.check_name for r in failed]}"

    async def test_returns_list_of_check_results(self) -> None:
        card_set = _make_card_set()
        results = await validate_rationale_card_set(
            card_set=card_set,
            routing_context=_TEST_ROUTING_CONTEXT,
            dataset_size=20,
            judge_fn=_no_overlap_judge,
        )
        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert isinstance(r, RationaleCheckResult)

    async def test_dataset_level_checks_run_before_per_card_checks(self) -> None:
        """Dataset-level check names should appear before per-card check names."""
        card_set = _make_card_set()
        results = await validate_rationale_card_set(
            card_set=card_set,
            routing_context=_TEST_ROUTING_CONTEXT,
            dataset_size=20,
            judge_fn=_no_overlap_judge,
        )
        dataset_checks = {
            "check_cluster_thresholds",
            "check_pruning_cleanup",
            "find_orphaned_examples",
            "check_registry_consistency",
        }
        per_card_checks = {
            "check_required_fields",
            "check_vocabulary_membership",
            "check_exclusion_coverage",
            "check_exclusion_format",
            "check_ambiguity_tag_membership",
        }
        result_names = [r.check_name for r in results]
        # Find the last dataset-level check index and first per-card check index
        last_dataset_idx = max(
            (i for i, n in enumerate(result_names) if n in dataset_checks),
            default=-1,
        )
        first_per_card_idx = min(
            (i for i, n in enumerate(result_names) if n in per_card_checks),
            default=len(result_names),
        )
        assert last_dataset_idx < first_per_card_idx, "Dataset-level checks must appear before per-card checks"

    async def test_invalid_card_produces_failures(self) -> None:
        # Card references an intent_pattern not in registry
        registry = _make_registry(intent_patterns=["data-analysis"])
        card = RationaleCard.model_construct(
            example_id="ex-001",
            assigned_route="claude-sonnet",
            intent_pattern="nonexistent",
            complexity_structure="multi-step-reasoning",
            route_exclusions=[
                RouteExclusion(route="claude-haiku", reason="Too weak"),
                RouteExclusion(route="claude-opus", reason="Overkill"),
            ],
            ambiguity_tags=[],
        )
        card_set = _make_card_set(cards={"ex-001": card}, registry=registry)
        results = await validate_rationale_card_set(
            card_set=card_set,
            routing_context=_TEST_ROUTING_CONTEXT,
            dataset_size=20,
            judge_fn=_no_overlap_judge,
        )
        failed_names = {r.check_name for r in results if not r.passed}
        assert "check_vocabulary_membership" in failed_names
