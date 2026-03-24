"""Registry management for the routing rationale schema (THP-82, Tasks 5-7).

Provides content hashing, seed initialization, persistence, and merge/prune
operations for VocabularyRegistry instances.
"""

from __future__ import annotations

import hashlib
from math import ceil
from pathlib import Path

import yaml

from odysseus.agents.routing_rationale_models import VocabularyEntry, VocabularyRegistry
from odysseus.eval.models import Example

# ---------------------------------------------------------------------------
# Task 5: Content hashing
# ---------------------------------------------------------------------------


def compute_dataset_hash(examples: list[Example]) -> str:
    """Compute a deterministic SHA-256 hash over (id, input, expected.route) tuples.

    The hash is order-independent (tuples are sorted before hashing) and
    truncated to 16 hex characters.
    """
    tuples = sorted((ex.id, ex.input, ex.expected.route) for ex in examples)
    payload = "\n".join(f"{id_}\t{inp}\t{route}" for id_, inp, route in tuples)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Task 5: Seed registry
# ---------------------------------------------------------------------------


def create_seed_registry() -> VocabularyRegistry:
    """Create an empty seed registry with the four canonical ambiguity tags.

    intent_pattern and complexity_structure are empty lists. ambiguity_tags
    has 4 pre-seeded entries: AMBIGUOUS_COMPLEXITY, AMBIGUOUS_DOMAIN,
    POTENTIAL_MISLABEL, BOUNDARY_CASE — each with a definition, empty
    example_ids, and no justification.
    """
    seed_tags = [
        VocabularyEntry(
            name="AMBIGUOUS_COMPLEXITY",
            definition=(
                "The routing complexity of this example is unclear — it could plausibly "
                "require simple or multi-step reasoning, making the correct tier uncertain."
            ),
            example_ids=[],
            justification=None,
        ),
        VocabularyEntry(
            name="AMBIGUOUS_DOMAIN",
            definition=(
                "The domain or task type of this example spans multiple categories, "
                "making it unclear which intent pattern best describes the query."
            ),
            example_ids=[],
            justification=None,
        ),
        VocabularyEntry(
            name="POTENTIAL_MISLABEL",
            definition=(
                "This example may have been assigned the wrong route — the ground-truth "
                "label appears inconsistent with the query content or context."
            ),
            example_ids=[],
            justification=None,
        ),
        VocabularyEntry(
            name="BOUNDARY_CASE",
            definition=(
                "This example sits at the boundary between two routing tiers and could "
                "reasonably be assigned to either, requiring careful human review."
            ),
            example_ids=[],
            justification=None,
        ),
    ]
    return VocabularyRegistry(
        intent_pattern=[],
        complexity_structure=[],
        ambiguity_tags=seed_tags,
    )


# ---------------------------------------------------------------------------
# Task 6: Persistence
# ---------------------------------------------------------------------------


def save_registry(registry: VocabularyRegistry, path: Path) -> None:
    """Serialize registry to YAML at path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = registry.model_dump()
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_registry(path: Path) -> VocabularyRegistry:
    """Load a VocabularyRegistry from a YAML file."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return VocabularyRegistry(**data)


def resolve_registry(
    dataset_hash: str,
    registry_dir: Path,
    inherit_from: Path | None = None,
) -> VocabularyRegistry | None:
    """Look up the registry for a dataset hash, with optional fallback.

    Resolution order:
    1. registry_dir/<hash>.yaml — registry saved for this exact dataset version.
    2. inherit_from — a previously-built registry to inherit vocabulary from.
    3. None — indicates a fresh start (no prior registry).
    """
    if registry_dir.exists():
        hash_path = registry_dir / f"{dataset_hash}.yaml"
        if hash_path.exists():
            return load_registry(hash_path)

    if inherit_from is not None and inherit_from.exists():
        return load_registry(inherit_from)

    return None


# ---------------------------------------------------------------------------
# Task 7: Merge and prune
# ---------------------------------------------------------------------------


class RegistryMergeError(Exception):
    """Raised when a proposed registry illegally removes or renames existing entries."""


def merge_registry(
    existing: VocabularyRegistry,
    proposed: VocabularyRegistry,
) -> VocabularyRegistry:
    """Validate that proposed does not remove any entries from existing.

    Returns proposed unchanged if all existing entries are still present.
    Raises RegistryMergeError if any existing entry is missing from proposed.
    """
    violations: list[str] = []

    for vocab_name in ("intent_pattern", "complexity_structure", "ambiguity_tags"):
        existing_names: set[str] = {e.name for e in getattr(existing, vocab_name)}
        proposed_names: set[str] = {e.name for e in getattr(proposed, vocab_name)}
        removed = existing_names - proposed_names
        if removed:
            for name in sorted(removed):
                violations.append(f"{vocab_name}: {name!r} was removed")

    if violations:
        detail = "; ".join(violations)
        raise RegistryMergeError(f"Proposed registry illegally removes existing entries — {detail}")

    return proposed


def prune_registry(
    registry: VocabularyRegistry,
    dataset_size: int,
) -> tuple[VocabularyRegistry, dict[str, list[str]]]:
    """Remove vocabulary entries whose example_ids count falls below the threshold.

    Threshold: max(3, ceil(0.05 * dataset_size))

    Returns:
        (pruned_registry, removed) where removed maps vocabulary name →
        list of entry names that were pruned.
    """
    threshold = max(3, ceil(0.05 * dataset_size))
    removed: dict[str, list[str]] = {}

    def _filter(entries: list[VocabularyEntry], vocab_name: str) -> list[VocabularyEntry]:
        kept = []
        pruned_names: list[str] = []
        for entry in entries:
            if len(entry.example_ids) >= threshold:
                kept.append(entry)
            else:
                pruned_names.append(entry.name)
        if pruned_names:
            removed[vocab_name] = pruned_names
        return kept

    pruned_registry = VocabularyRegistry(
        intent_pattern=_filter(registry.intent_pattern, "intent_pattern"),
        complexity_structure=_filter(registry.complexity_structure, "complexity_structure"),
        ambiguity_tags=_filter(registry.ambiguity_tags, "ambiguity_tags"),
    )
    return pruned_registry, removed
