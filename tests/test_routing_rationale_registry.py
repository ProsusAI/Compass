"""Tests for routing rationale registry (THP-82, Tasks 5-7)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from odysseus.agents.routing_rationale_models import VocabularyEntry, VocabularyRegistry
from odysseus.agents.routing_rationale_registry import (
    RegistryMergeError,
    compute_dataset_hash,
    create_seed_registry,
    load_registry,
    merge_registry,
    prune_registry,
    resolve_registry,
    save_registry,
)
from odysseus.eval.models import Example, Expected, ModelCostQuality

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_example(id: str, input: str, route: str, split: str = "dev") -> Example:
    return Example(
        id=id,
        input=input,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split=split,  # type: ignore[arg-type]
    )


def make_vocab_entry(name: str, example_ids: list[str] | None = None) -> VocabularyEntry:
    return VocabularyEntry(
        name=name,
        definition=f"Definition for {name}",
        example_ids=example_ids or [],
    )


def make_registry(
    intent_patterns: list[str] | None = None,
    complexity_structures: list[str] | None = None,
    ambiguity_tags: list[str] | None = None,
    intent_example_ids: dict[str, list[str]] | None = None,
    complexity_example_ids: dict[str, list[str]] | None = None,
    ambiguity_example_ids: dict[str, list[str]] | None = None,
) -> VocabularyRegistry:
    intent_example_ids = intent_example_ids or {}
    complexity_example_ids = complexity_example_ids or {}
    ambiguity_example_ids = ambiguity_example_ids or {}
    return VocabularyRegistry(
        intent_pattern=[make_vocab_entry(n, intent_example_ids.get(n)) for n in (intent_patterns or [])],
        complexity_structure=[
            make_vocab_entry(n, complexity_example_ids.get(n)) for n in (complexity_structures or [])
        ],
        ambiguity_tags=[make_vocab_entry(n, ambiguity_example_ids.get(n)) for n in (ambiguity_tags or [])],
    )


# ---------------------------------------------------------------------------
# Task 5: compute_dataset_hash
# ---------------------------------------------------------------------------


class TestComputeDatasetHash:
    def test_returns_16_hex_chars(self):
        examples = [make_example("e1", "hello", "fast")]
        h = compute_dataset_hash(examples)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        examples = [make_example("e1", "hello", "fast")]
        assert compute_dataset_hash(examples) == compute_dataset_hash(examples)

    def test_order_independent(self):
        e1 = make_example("e1", "hello", "fast")
        e2 = make_example("e2", "world", "slow")
        assert compute_dataset_hash([e1, e2]) == compute_dataset_hash([e2, e1])

    def test_different_content_produces_different_hash(self):
        examples_a = [make_example("e1", "hello", "fast")]
        examples_b = [make_example("e1", "hello", "slow")]  # different route
        assert compute_dataset_hash(examples_a) != compute_dataset_hash(examples_b)

    def test_different_input_produces_different_hash(self):
        examples_a = [make_example("e1", "hello", "fast")]
        examples_b = [make_example("e1", "world", "fast")]
        assert compute_dataset_hash(examples_a) != compute_dataset_hash(examples_b)

    def test_different_id_produces_different_hash(self):
        examples_a = [make_example("e1", "hello", "fast")]
        examples_b = [make_example("e2", "hello", "fast")]
        assert compute_dataset_hash(examples_a) != compute_dataset_hash(examples_b)

    def test_empty_list(self):
        h = compute_dataset_hash([])
        assert len(h) == 16

    def test_multiple_examples_stable(self):
        examples = [
            make_example("e1", "hello", "fast"),
            make_example("e2", "world", "slow"),
            make_example("e3", "foo", "fast"),
        ]
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(list(reversed(examples)))
        assert h1 == h2


# ---------------------------------------------------------------------------
# Task 5: create_seed_registry
# ---------------------------------------------------------------------------


class TestCreateSeedRegistry:
    def test_returns_vocabulary_registry(self):
        registry = create_seed_registry()
        assert isinstance(registry, VocabularyRegistry)

    def test_intent_pattern_is_empty(self):
        registry = create_seed_registry()
        assert registry.intent_pattern == []

    def test_complexity_structure_is_empty(self):
        registry = create_seed_registry()
        assert registry.complexity_structure == []

    def test_has_exactly_four_ambiguity_tags(self):
        registry = create_seed_registry()
        assert len(registry.ambiguity_tags) == 4

    def test_ambiguity_tag_names(self):
        registry = create_seed_registry()
        names = {e.name for e in registry.ambiguity_tags}
        assert names == {"AMBIGUOUS_COMPLEXITY", "AMBIGUOUS_DOMAIN", "POTENTIAL_MISLABEL", "BOUNDARY_CASE"}

    def test_ambiguity_tags_have_non_empty_definitions(self):
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.definition.strip(), f"Entry {entry.name!r} has empty definition"

    def test_ambiguity_tags_have_empty_example_ids(self):
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.example_ids == [], f"Entry {entry.name!r} should have empty example_ids"

    def test_ambiguity_tags_have_no_justification(self):
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.justification is None, f"Entry {entry.name!r} should have no justification"


# ---------------------------------------------------------------------------
# Task 6: save_registry / load_registry
# ---------------------------------------------------------------------------


class TestSaveLoadRegistry:
    def test_round_trip_empty_registry(self):
        registry = make_registry()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
        assert loaded == registry

    def test_round_trip_with_entries(self):
        registry = make_registry(
            intent_patterns=["data-analysis", "code-generation"],
            complexity_structures=["single-step", "multi-step"],
            ambiguity_tags=["AMBIGUOUS_COMPLEXITY", "BOUNDARY_CASE"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reg.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
        assert loaded == registry

    def test_round_trip_preserves_example_ids(self):
        registry = make_registry(
            intent_patterns=["data-analysis"],
            intent_example_ids={"data-analysis": ["e1", "e2", "e3"]},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reg.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
        assert loaded.intent_pattern[0].example_ids == ["e1", "e2", "e3"]

    def test_round_trip_preserves_justification(self):
        entry = VocabularyEntry(
            name="data-analysis",
            definition="Queries about data",
            example_ids=["e1"],
            justification="Added in run 3",
        )
        registry = VocabularyRegistry(
            intent_pattern=[entry],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reg.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
        assert loaded.intent_pattern[0].justification == "Added in run 3"

    def test_save_creates_parent_dirs(self):
        registry = make_registry()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deep" / "registry.yaml"
            save_registry(registry, path)
            assert path.exists()

    def test_save_produces_yaml_file(self):
        registry = make_registry()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reg.yaml"
            save_registry(registry, path)
            content = path.read_text()
        # YAML files should not look like JSON
        assert "{" not in content or "intent_pattern" in content

    def test_load_seed_registry_round_trip(self):
        registry = create_seed_registry()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
        assert loaded == registry


# ---------------------------------------------------------------------------
# Task 6: resolve_registry
# ---------------------------------------------------------------------------


class TestResolveRegistry:
    def test_returns_none_for_fresh_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"
            registry_dir.mkdir()
            result = resolve_registry("abc123", registry_dir, inherit_from=None)
        assert result is None

    def test_finds_registry_by_hash(self):
        registry = make_registry(intent_patterns=["data-analysis"])
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"
            registry_dir.mkdir()
            save_registry(registry, registry_dir / "abc123.yaml")
            result = resolve_registry("abc123", registry_dir, inherit_from=None)
        assert result is not None
        assert result == registry

    def test_returns_inherit_when_no_hash_match(self):
        fallback = make_registry(intent_patterns=["code-generation"])
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"
            registry_dir.mkdir()
            inherit_path = Path(tmp) / "fallback.yaml"
            save_registry(fallback, inherit_path)
            result = resolve_registry("nonexistent", registry_dir, inherit_from=inherit_path)
        assert result is not None
        assert result == fallback

    def test_hash_takes_priority_over_inherit(self):
        primary = make_registry(intent_patterns=["data-analysis"])
        fallback = make_registry(intent_patterns=["code-generation"])
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"
            registry_dir.mkdir()
            save_registry(primary, registry_dir / "myhash.yaml")
            inherit_path = Path(tmp) / "fallback.yaml"
            save_registry(fallback, inherit_path)
            result = resolve_registry("myhash", registry_dir, inherit_from=inherit_path)
        assert result is not None
        assert result.intent_pattern[0].name == "data-analysis"

    def test_returns_none_when_no_hash_and_no_inherit(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"
            registry_dir.mkdir()
            result = resolve_registry("unknown", registry_dir)
        assert result is None

    def test_nonexistent_registry_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp) / "registries"  # does not exist
            result = resolve_registry("abc123", registry_dir)
        assert result is None


# ---------------------------------------------------------------------------
# Task 7: merge_registry
# ---------------------------------------------------------------------------


class TestMergeRegistry:
    def test_appending_new_entries_succeeds(self):
        existing = make_registry(intent_patterns=["data-analysis"])
        proposed = make_registry(intent_patterns=["data-analysis", "code-generation"])
        result = merge_registry(existing, proposed)
        names = [e.name for e in result.intent_pattern]
        assert "data-analysis" in names
        assert "code-generation" in names

    def test_returns_proposed_when_valid(self):
        existing = make_registry(intent_patterns=["data-analysis"])
        proposed = make_registry(intent_patterns=["data-analysis", "code-generation"])
        result = merge_registry(existing, proposed)
        assert result is proposed

    def test_removing_existing_entry_raises(self):
        existing = make_registry(intent_patterns=["data-analysis", "code-generation"])
        proposed = make_registry(intent_patterns=["data-analysis"])  # code-generation removed
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)

    def test_renaming_existing_entry_raises(self):
        existing = make_registry(intent_patterns=["data-analysis"])
        proposed = make_registry(intent_patterns=["data-query"])  # renamed
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)

    def test_removing_complexity_raises(self):
        existing = make_registry(complexity_structures=["single-step", "multi-step"])
        proposed = make_registry(complexity_structures=["single-step"])
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)

    def test_removing_ambiguity_tag_raises(self):
        existing = make_registry(ambiguity_tags=["AMBIGUOUS_COMPLEXITY", "BOUNDARY_CASE"])
        proposed = make_registry(ambiguity_tags=["AMBIGUOUS_COMPLEXITY"])
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)

    def test_identical_registries_succeeds(self):
        existing = make_registry(
            intent_patterns=["data-analysis"],
            complexity_structures=["single-step"],
            ambiguity_tags=["BOUNDARY_CASE"],
        )
        proposed = make_registry(
            intent_patterns=["data-analysis"],
            complexity_structures=["single-step"],
            ambiguity_tags=["BOUNDARY_CASE"],
        )
        result = merge_registry(existing, proposed)
        assert result is proposed

    def test_merge_error_message_contains_info(self):
        existing = make_registry(intent_patterns=["data-analysis"])
        proposed = make_registry(intent_patterns=["code-generation"])
        with pytest.raises(RegistryMergeError, match="data-analysis"):
            merge_registry(existing, proposed)

    def test_appending_to_all_vocabularies(self):
        existing = make_registry(
            intent_patterns=["data-analysis"],
            complexity_structures=["single-step"],
            ambiguity_tags=["BOUNDARY_CASE"],
        )
        proposed = make_registry(
            intent_patterns=["data-analysis", "code-generation"],
            complexity_structures=["single-step", "multi-step"],
            ambiguity_tags=["BOUNDARY_CASE", "AMBIGUOUS_DOMAIN"],
        )
        result = merge_registry(existing, proposed)
        assert len(result.intent_pattern) == 2
        assert len(result.complexity_structure) == 2
        assert len(result.ambiguity_tags) == 2


# ---------------------------------------------------------------------------
# Task 7: prune_registry
# ---------------------------------------------------------------------------


class TestPruneRegistry:
    def _make_entry_with_ids(self, name: str, example_ids: list[str]) -> VocabularyEntry:
        return VocabularyEntry(
            name=name,
            definition=f"Definition for {name}",
            example_ids=example_ids,
        )

    def test_entries_above_threshold_are_kept(self):
        # dataset_size=100, threshold=max(3, ceil(0.05*100))=5
        # entry with 6 ids should be kept
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry_with_ids("data-analysis", ["e1", "e2", "e3", "e4", "e5", "e6"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=100)
        assert len(pruned.intent_pattern) == 1
        assert "data-analysis" not in removed.get("intent_pattern", [])

    def test_entries_below_threshold_are_removed(self):
        # dataset_size=100, threshold=5; entry with 2 ids should be pruned
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry_with_ids("data-analysis", ["e1", "e2"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=100)
        assert len(pruned.intent_pattern) == 0
        assert "data-analysis" in removed.get("intent_pattern", [])

    def test_entries_at_threshold_are_kept(self):
        # threshold = max(3, ceil(0.05 * 100)) = 5; entry with exactly 5 ids should be kept
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry_with_ids("data-analysis", ["e1", "e2", "e3", "e4", "e5"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=100)
        assert len(pruned.intent_pattern) == 1

    def test_removed_dict_categorized_by_vocabulary(self):
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry_with_ids("data-analysis", ["e1"])],
            complexity_structure=[self._make_entry_with_ids("single-step", ["e2"])],
            ambiguity_tags=[self._make_entry_with_ids("BOUNDARY_CASE", ["e3"])],
        )
        # dataset_size=100, threshold=5; all have 1 example_id, all pruned
        _, removed = prune_registry(registry, dataset_size=100)
        assert "data-analysis" in removed.get("intent_pattern", [])
        assert "single-step" in removed.get("complexity_structure", [])
        assert "BOUNDARY_CASE" in removed.get("ambiguity_tags", [])

    def test_small_dataset_uses_minimum_threshold_of_3(self):
        # dataset_size=10, threshold=max(3, ceil(0.05*10))=max(3,1)=3
        # entry with 2 ids → pruned; entry with 3 ids → kept
        registry = VocabularyRegistry(
            intent_pattern=[
                self._make_entry_with_ids("data-analysis", ["e1", "e2"]),
                self._make_entry_with_ids("code-generation", ["e1", "e2", "e3"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=10)
        kept_names = [e.name for e in pruned.intent_pattern]
        assert "data-analysis" not in kept_names
        assert "code-generation" in kept_names

    def test_empty_registry_no_error(self):
        registry = make_registry()
        pruned, removed = prune_registry(registry, dataset_size=100)
        assert pruned.intent_pattern == []
        assert pruned.complexity_structure == []
        assert pruned.ambiguity_tags == []
        assert removed == {}

    def test_removed_is_empty_when_nothing_pruned(self):
        # All entries well above threshold
        ids = [f"e{i}" for i in range(20)]
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry_with_ids("data-analysis", ids)],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        _, removed = prune_registry(registry, dataset_size=100)
        assert removed == {}

    def test_prune_mixed_keeps_above_removes_below(self):
        # threshold = max(3, ceil(0.05*60)) = max(3,3) = 3
        registry = VocabularyRegistry(
            intent_pattern=[
                self._make_entry_with_ids("data-analysis", ["e1", "e2", "e3"]),  # at threshold, kept
                self._make_entry_with_ids("code-generation", ["e1", "e2"]),  # below, pruned
                self._make_entry_with_ids("debugging", ["e1", "e2", "e3", "e4"]),  # above, kept
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=60)
        kept = [e.name for e in pruned.intent_pattern]
        assert "data-analysis" in kept
        assert "debugging" in kept
        assert "code-generation" not in kept
        assert "code-generation" in removed.get("intent_pattern", [])
