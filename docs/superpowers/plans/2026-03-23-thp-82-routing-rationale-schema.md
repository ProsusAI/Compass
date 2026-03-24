# THP-82 Routing Rationale Schema Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the routing rationale schema as Pydantic models, validation functions, vocabulary registry management, and two annotation skills.

**Architecture:** Schema-first bottom-up approach. Three Python modules (`routing_rationale_models.py`, `routing_rationale_checks.py`, `routing_rationale_registry.py`) under `odysseus/agents/`, plus two SKILL.md packages under `odysseus/skills/`. Each layer is independently testable.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-implementation.md`

**Worktree:** `~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema`

---

## Chunk 1: Pydantic Models

### Task 1: TierDisqualifier and RationaleCard models

**Files:**
- Create: `odysseus/agents/routing_rationale_models.py`
- Test: `tests/test_routing_rationale_models.py`

- [ ] **Step 1: Write failing tests for TierDisqualifier**

```python
"""Tests for odysseus.agents.routing_rationale_models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from odysseus.agents.routing_rationale_models import TierDisqualifier


class TestTierDisqualifier:
    def test_valid_construction(self) -> None:
        td = TierDisqualifier(route="0", reason="query requires joining 3 independent sources")
        assert td.route == "0"
        assert td.reason == "query requires joining 3 independent sources"

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TierDisqualifier(route="0", reason="")

    def test_whitespace_only_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TierDisqualifier(route="0", reason="   ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement TierDisqualifier**

Create `odysseus/agents/routing_rationale_models.py`:

```python
"""Routing rationale schema models for the Routing Analysis agent.

Provides typed Pydantic models for rationale cards, vocabulary entries,
and the vocabulary registry. Used by THP-82 (schema), THP-86 (serialization),
and THP-74 (routing analysis pipeline).

See: docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-implementation.md
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


# Naming convention patterns
KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SCREAMING_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


class TierDisqualifier(BaseModel):
    """Why a specific route is ruled out for an example.

    Fields:
        route: Route identifier matching Expected.route values (opaque string).
        reason: Observable query property explaining the disqualification.
    """

    route: str
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must be non-empty")
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py::TestTierDisqualifier -v`
Expected: 3 passed

- [ ] **Step 5: Write failing tests for RationaleCard**

Append to `tests/test_routing_rationale_models.py`:

```python
from odysseus.agents.routing_rationale_models import RationaleCard


class TestRationaleCard:
    def test_valid_construction(self) -> None:
        card = RationaleCard(
            example_id="ex-1",
            assigned_route="2",
            intent_pattern="data-filtering",
            complexity_structure="sequential-dependency",
            tier_disqualifiers=[
                TierDisqualifier(route="0", reason="query requires precise numerical thresholds"),
                TierDisqualifier(route="1", reason="3 sequential filtering steps"),
            ],
            ambiguity_tags=["AMBIGUOUS_COMPLEXITY"],
        )
        assert card.example_id == "ex-1"
        assert card.assigned_route == "2"
        assert len(card.tier_disqualifiers) == 2
        assert card.ambiguity_tags == ["AMBIGUOUS_COMPLEXITY"]

    def test_empty_ambiguity_tags_allowed(self) -> None:
        card = RationaleCard(
            example_id="ex-2",
            assigned_route="0",
            intent_pattern="factual-lookup",
            complexity_structure="single-hop",
            tier_disqualifiers=[
                TierDisqualifier(route="1", reason="no multi-step reasoning needed"),
                TierDisqualifier(route="2", reason="no cross-source joining needed"),
            ],
            ambiguity_tags=[],
        )
        assert card.ambiguity_tags == []

    def test_invalid_intent_pattern_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCard(
                example_id="ex-1",
                assigned_route="0",
                intent_pattern="DataFiltering",  # not kebab-case
                complexity_structure="single-hop",
                tier_disqualifiers=[],
                ambiguity_tags=[],
            )

    def test_invalid_complexity_structure_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCard(
                example_id="ex-1",
                assigned_route="0",
                intent_pattern="factual-lookup",
                complexity_structure="SINGLE_HOP",  # not kebab-case
                tier_disqualifiers=[],
                ambiguity_tags=[],
            )

    def test_invalid_ambiguity_tag_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCard(
                example_id="ex-1",
                assigned_route="0",
                intent_pattern="factual-lookup",
                complexity_structure="single-hop",
                tier_disqualifiers=[],
                ambiguity_tags=["ambiguous-complexity"],  # not SCREAMING_SNAKE
            )

    def test_empty_example_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCard(
                example_id="",
                assigned_route="0",
                intent_pattern="factual-lookup",
                complexity_structure="single-hop",
                tier_disqualifiers=[],
                ambiguity_tags=[],
            )

    def test_empty_assigned_route_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCard(
                example_id="ex-1",
                assigned_route="",
                intent_pattern="factual-lookup",
                complexity_structure="single-hop",
                tier_disqualifiers=[],
                ambiguity_tags=[],
            )
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py::TestRationaleCard -v`
Expected: FAIL — RationaleCard not defined

- [ ] **Step 7: Implement RationaleCard**

Add to `odysseus/agents/routing_rationale_models.py`:

```python
class RationaleCard(BaseModel):
    """Structured routing rationale for a single example.

    Fields:
        example_id: Foreign key to Example.id.
        assigned_route: Ground-truth route from Expected.route.
        intent_pattern: Task type (kebab-case, from vocabulary registry).
        complexity_structure: Reasoning topology (kebab-case, from vocabulary registry).
        tier_disqualifiers: Why non-assigned routes are ruled out.
        ambiguity_tags: Boundary-case labels (SCREAMING_SNAKE_CASE). Empty if clear-cut.
    """

    example_id: str
    assigned_route: str
    intent_pattern: str
    complexity_structure: str
    tier_disqualifiers: list[TierDisqualifier]
    ambiguity_tags: list[str]

    @field_validator("example_id", "assigned_route")
    @classmethod
    def string_fields_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @field_validator("intent_pattern", "complexity_structure")
    @classmethod
    def must_be_kebab_case(cls, v: str) -> str:
        if not KEBAB_CASE_RE.match(v):
            raise ValueError(f"{v!r} is not valid kebab-case (expected pattern: a-z0-9 with hyphens)")
        return v

    @field_validator("ambiguity_tags")
    @classmethod
    def tags_must_be_screaming_snake(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not SCREAMING_SNAKE_RE.match(tag):
                raise ValueError(f"{tag!r} is not valid SCREAMING_SNAKE_CASE")
        return v
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py -v`
Expected: All passed

- [ ] **Step 9: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_models.py tests/test_routing_rationale_models.py
git commit -m "feat(thp-82): add TierDisqualifier and RationaleCard models"
```

### Task 2: VocabularyEntry, VocabularyRegistry, and RationaleCardSet models

**Files:**
- Modify: `odysseus/agents/routing_rationale_models.py`
- Modify: `tests/test_routing_rationale_models.py`

- [ ] **Step 1: Write failing tests for VocabularyEntry and VocabularyRegistry**

Append to `tests/test_routing_rationale_models.py`:

```python
from odysseus.agents.routing_rationale_models import VocabularyEntry, VocabularyRegistry


class TestVocabularyEntry:
    def test_valid_entry(self) -> None:
        entry = VocabularyEntry(
            name="factual-lookup",
            definition="Query asks for a single factual answer",
            example_ids=["ex-1", "ex-5", "ex-9"],
        )
        assert entry.name == "factual-lookup"
        assert entry.justification is None

    def test_entry_with_justification(self) -> None:
        entry = VocabularyEntry(
            name="cross-source-join",
            definition="Query requires combining data from multiple sources",
            example_ids=["ex-3", "ex-7"],
            justification="Existing entries cover single-source queries only",
        )
        assert entry.justification is not None

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VocabularyEntry(name="", definition="a def", example_ids=[])

    def test_empty_definition_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VocabularyEntry(name="test", definition="", example_ids=[])


class TestVocabularyRegistry:
    def _make_entry(self, name: str, ids: list[str] | None = None) -> VocabularyEntry:
        return VocabularyEntry(
            name=name,
            definition=f"Definition for {name}",
            example_ids=ids or ["ex-1", "ex-2", "ex-3"],
        )

    def test_valid_registry(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[self._make_entry("factual-lookup")],
            complexity_structure=[self._make_entry("single-hop")],
            ambiguity_tags=[self._make_entry("AMBIGUOUS_COMPLEXITY")],
        )
        assert len(registry.intent_pattern) == 1
        assert len(registry.ambiguity_tags) == 1

    def test_empty_registry_allowed(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        assert len(registry.intent_pattern) == 0

    def test_intent_pattern_must_be_kebab_case(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            VocabularyRegistry(
                intent_pattern=[self._make_entry("FactualLookup")],
                complexity_structure=[],
                ambiguity_tags=[],
            )

    def test_complexity_structure_must_be_kebab_case(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            VocabularyRegistry(
                intent_pattern=[],
                complexity_structure=[self._make_entry("SINGLE_HOP")],
                ambiguity_tags=[],
            )

    def test_ambiguity_tags_must_be_screaming_snake(self) -> None:
        with pytest.raises(ValidationError, match="SCREAMING_SNAKE_CASE"):
            VocabularyRegistry(
                intent_pattern=[],
                complexity_structure=[],
                ambiguity_tags=[self._make_entry("ambiguous-complexity")],
            )

    def test_mixed_valid_entries(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                self._make_entry("factual-lookup"),
                self._make_entry("data-filtering"),
            ],
            complexity_structure=[self._make_entry("single-hop")],
            ambiguity_tags=[
                self._make_entry("AMBIGUOUS_COMPLEXITY"),
                self._make_entry("BOUNDARY_CASE"),
            ],
        )
        assert len(registry.intent_pattern) == 2
        assert len(registry.ambiguity_tags) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py::TestVocabularyEntry tests/test_routing_rationale_models.py::TestVocabularyRegistry -v`
Expected: FAIL — classes not defined

- [ ] **Step 3: Implement VocabularyEntry and VocabularyRegistry**

Add to `odysseus/agents/routing_rationale_models.py`:

```python
class VocabularyEntry(BaseModel):
    """A single entry in a vocabulary registry.

    Fields:
        name: Entry name (naming convention enforced at VocabularyRegistry level).
        definition: One-sentence description of the pattern.
        example_ids: IDs of examples this entry applies to.
        justification: Why existing entries are insufficient (required for new, None for seeds).
    """

    name: str
    definition: str
    example_ids: list[str]
    justification: str | None = None

    @field_validator("name", "definition")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class VocabularyRegistry(BaseModel):
    """Unified registry for all three dynamic vocabularies.

    Naming convention validation lives here because VocabularyEntry
    does not know which vocabulary it belongs to.
    """

    intent_pattern: list[VocabularyEntry]
    complexity_structure: list[VocabularyEntry]
    ambiguity_tags: list[VocabularyEntry]

    @model_validator(mode="after")
    def validate_naming_conventions(self) -> VocabularyRegistry:
        for entry in self.intent_pattern:
            if not KEBAB_CASE_RE.match(entry.name):
                raise ValueError(
                    f"intent_pattern entry {entry.name!r} is not valid kebab-case"
                )
        for entry in self.complexity_structure:
            if not KEBAB_CASE_RE.match(entry.name):
                raise ValueError(
                    f"complexity_structure entry {entry.name!r} is not valid kebab-case"
                )
        for entry in self.ambiguity_tags:
            if not SCREAMING_SNAKE_RE.match(entry.name):
                raise ValueError(
                    f"ambiguity_tags entry {entry.name!r} is not valid SCREAMING_SNAKE_CASE"
                )
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py -v`
Expected: All passed

- [ ] **Step 5: Write failing tests for RationaleCardSet**

Append to `tests/test_routing_rationale_models.py`:

```python
from datetime import datetime, timezone

from odysseus.agents.routing_rationale_models import RationaleCardSet


class TestRationaleCardSet:
    def _make_registry(self) -> VocabularyRegistry:
        return VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="Single fact", example_ids=["ex-1"])],
            complexity_structure=[VocabularyEntry(name="single-hop", definition="One step", example_ids=["ex-1"])],
            ambiguity_tags=[],
        )

    def _make_card(self, example_id: str = "ex-1") -> RationaleCard:
        return RationaleCard(
            example_id=example_id,
            assigned_route="0",
            intent_pattern="factual-lookup",
            complexity_structure="single-hop",
            tier_disqualifiers=[TierDisqualifier(route="1", reason="no multi-step needed")],
            ambiguity_tags=[],
        )

    def test_valid_card_set(self) -> None:
        card = self._make_card()
        card_set = RationaleCardSet(
            cards={"ex-1": card},
            dataset_hash="abc123def456",
            registry=self._make_registry(),
            created_at=datetime.now(tz=timezone.utc),
        )
        assert len(card_set.cards) == 1
        assert card_set.inherited_from is None

    def test_card_set_with_inheritance(self) -> None:
        card_set = RationaleCardSet(
            cards={},
            dataset_hash="abc123def456",
            registry=self._make_registry(),
            created_at=datetime.now(tz=timezone.utc),
            inherited_from="/path/to/previous/registry.yaml",
        )
        assert card_set.inherited_from == "/path/to/previous/registry.yaml"

    def test_empty_dataset_hash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCardSet(
                cards={},
                dataset_hash="",
                registry=self._make_registry(),
                created_at=datetime.now(tz=timezone.utc),
            )
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py::TestRationaleCardSet -v`
Expected: FAIL — RationaleCardSet not defined

- [ ] **Step 7: Implement RationaleCardSet**

Add to `odysseus/agents/routing_rationale_models.py`:

```python
class RationaleCardSet(BaseModel):
    """Container for all rationale cards from a single annotation run.

    Fields:
        cards: Rationale cards keyed by example_id.
        dataset_hash: Content hash identifying the source dataset.
        registry: Vocabulary registry used for this annotation.
        created_at: Timestamp of the annotation run.
        inherited_from: Path to parent registry if dataset changed.
    """

    cards: dict[str, RationaleCard]
    dataset_hash: str
    registry: VocabularyRegistry
    created_at: datetime
    inherited_from: str | None = None

    @field_validator("dataset_hash")
    @classmethod
    def hash_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("dataset_hash must be non-empty")
        return v
```

- [ ] **Step 8: Run all model tests**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_models.py -v`
Expected: All passed

- [ ] **Step 9: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_models.py tests/test_routing_rationale_models.py
git commit -m "feat(thp-82): add VocabularyEntry, VocabularyRegistry, and RationaleCardSet models"
```

---

## Chunk 2: Validation Functions

### Task 3: Per-card validation checks

**Files:**
- Create: `odysseus/agents/routing_rationale_checks.py`
- Create: `tests/test_routing_rationale_checks.py`

- [ ] **Step 1: Write failing tests for RationaleCheckResult and per-card checks**

```python
"""Tests for odysseus.agents.routing_rationale_checks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from odysseus.agents.routing_rationale_checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_disqualifier_coverage,
    check_disqualifier_format,
    check_required_fields,
    check_vocabulary_membership,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    TierDisqualifier,
    VocabularyEntry,
    VocabularyRegistry,
)


def _make_registry() -> VocabularyRegistry:
    return VocabularyRegistry(
        intent_pattern=[
            VocabularyEntry(name="factual-lookup", definition="Single fact query", example_ids=["ex-1"]),
            VocabularyEntry(name="data-filtering", definition="Apply filters to data", example_ids=["ex-2"]),
        ],
        complexity_structure=[
            VocabularyEntry(name="single-hop", definition="One retrieval step", example_ids=["ex-1"]),
            VocabularyEntry(name="sequential-dependency", definition="Chained steps", example_ids=["ex-2"]),
        ],
        ambiguity_tags=[
            VocabularyEntry(name="AMBIGUOUS_COMPLEXITY", definition="Complexity signals conflict", example_ids=["ex-1"]),
        ],
    )


def _make_card(**overrides) -> RationaleCard:
    defaults = dict(
        example_id="ex-1",
        assigned_route="2",
        intent_pattern="data-filtering",
        complexity_structure="sequential-dependency",
        tier_disqualifiers=[
            TierDisqualifier(route="0", reason="requires numerical thresholds"),
            TierDisqualifier(route="1", reason="3 sequential filtering steps"),
        ],
        ambiguity_tags=[],
    )
    defaults.update(overrides)
    return RationaleCard(**defaults)


class TestRationaleCheckResult:
    def test_valid_result(self) -> None:
        r = RationaleCheckResult(
            passed=True, check_name="test", severity="info", details="ok", affected_ids=[],
        )
        assert r.passed is True

    def test_invalid_severity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RationaleCheckResult(
                passed=True, check_name="test", severity="fatal", details="ok", affected_ids=[],
            )


class TestCheckRequiredFields:
    def test_valid_card_passes(self) -> None:
        result = check_required_fields(_make_card(), _make_registry())
        assert result.passed is True

    def test_card_with_missing_vocab_still_passes_required(self) -> None:
        # required fields checks presence, not membership
        card = _make_card(intent_pattern="unknown-pattern")
        result = check_required_fields(card, _make_registry())
        assert result.passed is True


class TestCheckVocabularyMembership:
    def test_valid_membership_passes(self) -> None:
        result = check_vocabulary_membership(_make_card(), _make_registry())
        assert result.passed is True

    def test_unknown_intent_pattern_fails(self) -> None:
        card = _make_card(intent_pattern="unknown-pattern")
        result = check_vocabulary_membership(card, _make_registry())
        assert result.passed is False
        assert "ex-1" in result.affected_ids

    def test_unknown_complexity_structure_fails(self) -> None:
        card = _make_card(complexity_structure="unknown-structure")
        result = check_vocabulary_membership(card, _make_registry())
        assert result.passed is False


class TestCheckDisqualifierCoverage:
    def test_full_coverage_passes(self) -> None:
        card = _make_card(assigned_route="2")
        result = check_disqualifier_coverage(card, {"0", "1", "2"})
        assert result.passed is True

    def test_missing_route_fails(self) -> None:
        card = _make_card(
            assigned_route="2",
            tier_disqualifiers=[TierDisqualifier(route="0", reason="reason")],
        )
        result = check_disqualifier_coverage(card, {"0", "1", "2"})
        assert result.passed is False
        assert "1" in result.details  # missing route mentioned


class TestCheckDisqualifierFormat:
    def test_valid_format_passes(self) -> None:
        result = check_disqualifier_format(_make_card())
        assert result.passed is True


class TestCheckAmbiguityTagMembership:
    def test_empty_tags_passes(self) -> None:
        result = check_ambiguity_tag_membership(_make_card(), _make_registry())
        assert result.passed is True

    def test_valid_tag_passes(self) -> None:
        card = _make_card(ambiguity_tags=["AMBIGUOUS_COMPLEXITY"])
        result = check_ambiguity_tag_membership(card, _make_registry())
        assert result.passed is True

    def test_unknown_tag_fails(self) -> None:
        card = _make_card(ambiguity_tags=["NONEXISTENT_TAG"])
        result = check_ambiguity_tag_membership(card, _make_registry())
        assert result.passed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_checks.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement RationaleCheckResult and all per-card checks**

Create `odysseus/agents/routing_rationale_checks.py`:

```python
"""Validation checks for routing rationale cards.

Provides per-card and dataset-level validation functions returning
RationaleCheckResult. Follows the same pattern as data_validation_checks.py.

See: docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-implementation.md
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    VocabularyRegistry,
)


class RationaleCheckResult(BaseModel):
    """Result of a single rationale validation check."""

    passed: bool
    check_name: str
    severity: Literal["critical", "warning", "info"]
    details: str
    affected_ids: list[str]


# ---------------------------------------------------------------------------
# Per-card checks
# ---------------------------------------------------------------------------


def check_required_fields(
    card: RationaleCard, registry: VocabularyRegistry,
) -> RationaleCheckResult:
    """Check all 4 rationale fields are present and non-empty."""
    missing = []
    if not card.intent_pattern:
        missing.append("intent_pattern")
    if not card.complexity_structure:
        missing.append("complexity_structure")
    if not card.tier_disqualifiers and card.tier_disqualifiers != []:
        missing.append("tier_disqualifiers")
    # ambiguity_tags can be empty list — only check if None somehow
    return RationaleCheckResult(
        passed=len(missing) == 0,
        check_name="required_fields",
        severity="critical",
        details=f"Missing fields: {missing}" if missing else "All required fields present",
        affected_ids=[card.example_id] if missing else [],
    )


def check_vocabulary_membership(
    card: RationaleCard, registry: VocabularyRegistry,
) -> RationaleCheckResult:
    """Check intent_pattern and complexity_structure exist in registry."""
    intent_names = {e.name for e in registry.intent_pattern}
    complexity_names = {e.name for e in registry.complexity_structure}
    problems = []
    if card.intent_pattern not in intent_names:
        problems.append(f"intent_pattern {card.intent_pattern!r} not in registry")
    if card.complexity_structure not in complexity_names:
        problems.append(f"complexity_structure {card.complexity_structure!r} not in registry")
    return RationaleCheckResult(
        passed=len(problems) == 0,
        check_name="vocabulary_membership",
        severity="critical",
        details="; ".join(problems) if problems else "All values in registry",
        affected_ids=[card.example_id] if problems else [],
    )


def check_disqualifier_coverage(
    card: RationaleCard, available_routes: set[str],
) -> RationaleCheckResult:
    """Check every non-assigned route has at least one disqualifier."""
    covered_routes = {d.route for d in card.tier_disqualifiers}
    expected_routes = available_routes - {card.assigned_route}
    missing = expected_routes - covered_routes
    return RationaleCheckResult(
        passed=len(missing) == 0,
        check_name="disqualifier_coverage",
        severity="critical",
        details=f"Missing disqualifiers for routes: {sorted(missing)}" if missing else "All non-assigned routes covered",
        affected_ids=[card.example_id] if missing else [],
    )


def check_disqualifier_format(card: RationaleCard) -> RationaleCheckResult:
    """Check each disqualifier has non-empty route and reason."""
    problems = []
    for i, d in enumerate(card.tier_disqualifiers):
        if not d.route.strip():
            problems.append(f"disqualifier[{i}]: empty route")
        if not d.reason.strip():
            problems.append(f"disqualifier[{i}]: empty reason")
    return RationaleCheckResult(
        passed=len(problems) == 0,
        check_name="disqualifier_format",
        severity="critical",
        details="; ".join(problems) if problems else "All disqualifiers well-formed",
        affected_ids=[card.example_id] if problems else [],
    )


def check_ambiguity_tag_membership(
    card: RationaleCard, registry: VocabularyRegistry,
) -> RationaleCheckResult:
    """Check all ambiguity tags on card exist in finalized registry."""
    valid_tags = {e.name for e in registry.ambiguity_tags}
    invalid = [t for t in card.ambiguity_tags if t not in valid_tags]
    return RationaleCheckResult(
        passed=len(invalid) == 0,
        check_name="ambiguity_tag_membership",
        severity="warning",
        details=f"Unknown tags: {invalid}" if invalid else "All tags valid",
        affected_ids=[card.example_id] if invalid else [],
    )
```

- [ ] **Step 4: Run per-card check tests**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_checks.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_checks.py tests/test_routing_rationale_checks.py
git commit -m "feat(thp-82): add per-card rationale validation checks"
```

### Task 4: Dataset-level validation checks and top-level runner

**Files:**
- Modify: `odysseus/agents/routing_rationale_checks.py`
- Modify: `tests/test_routing_rationale_checks.py`

- [ ] **Step 1: Write failing tests for dataset-level checks**

Append to `tests/test_routing_rationale_checks.py`:

```python
from datetime import datetime, timezone

from odysseus.agents.routing_rationale_checks import (
    check_cluster_thresholds,
    check_pruning_cleanup,
    check_registry_consistency,
    find_orphaned_examples,
    validate_rationale_card_set,
)
from odysseus.agents.routing_rationale_models import RationaleCardSet


def _make_card_set(
    registry: VocabularyRegistry | None = None,
    cards: dict[str, RationaleCard] | None = None,
) -> RationaleCardSet:
    reg = registry or _make_registry()
    if cards is None:
        cards = {"ex-1": _make_card()}
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc123",
        registry=reg,
        created_at=datetime.now(tz=timezone.utc),
    )


class TestCheckClusterThresholds:
    def test_entries_meeting_threshold_pass(self) -> None:
        # dataset_size=20 -> threshold = max(3, ceil(0.05*20)) = 3
        # Each entry has 3+ example_ids
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=["a", "b", "c"]),
            ],
            complexity_structure=[
                VocabularyEntry(name="single-hop", definition="d", example_ids=["a", "b", "c"]),
            ],
            ambiguity_tags=[],
        )
        result = check_cluster_thresholds(registry, dataset_size=20)
        assert result.passed is True

    def test_entries_below_threshold_fail(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=["a"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        result = check_cluster_thresholds(registry, dataset_size=20)
        assert result.passed is False
        assert "factual-lookup" in result.details

    def test_large_dataset_scales_threshold(self) -> None:
        # dataset_size=200 -> threshold = max(3, ceil(0.05*200)) = 10
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=[f"ex-{i}" for i in range(5)]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        result = check_cluster_thresholds(registry, dataset_size=200)
        assert result.passed is False


class TestCheckPruningCleanup:
    def test_clean_card_set_passes(self) -> None:
        result = check_pruning_cleanup(_make_card_set())
        assert result.passed is True

    def test_card_referencing_missing_intent_fails(self) -> None:
        # Card references "data-filtering" but registry only has "factual-lookup"
        registry = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1"])],
            complexity_structure=[VocabularyEntry(name="sequential-dependency", definition="d", example_ids=["ex-1"])],
            ambiguity_tags=[],
        )
        card = _make_card(intent_pattern="data-filtering")  # not in registry
        # We need to bypass RationaleCard validation for this test — but card is already valid kebab-case
        # The issue is check_pruning_cleanup checks against card_set.registry
        card_set = _make_card_set(registry=registry, cards={"ex-1": card})
        result = check_pruning_cleanup(card_set)
        assert result.passed is False


class TestFindOrphanedExamples:
    def test_no_orphans(self) -> None:
        result = find_orphaned_examples(_make_card_set())
        assert result.passed is True
        assert result.affected_ids == []

    def test_orphaned_intent_detected(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1"])],
            complexity_structure=[VocabularyEntry(name="sequential-dependency", definition="d", example_ids=["ex-1"])],
            ambiguity_tags=[],
        )
        card = _make_card(intent_pattern="data-filtering")
        card_set = _make_card_set(registry=registry, cards={"ex-1": card})
        result = find_orphaned_examples(card_set)
        assert result.passed is False
        assert "ex-1" in result.affected_ids


class TestCheckRegistryConsistency:
    @pytest.mark.asyncio
    async def test_no_overlap_passes(self) -> None:
        async def judge_no_overlap(def1: str, def2: str) -> bool:
            return False  # no overlap
        result = await check_registry_consistency(_make_registry(), judge_no_overlap)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_overlap_detected_fails(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="Single fact query", example_ids=["ex-1", "ex-2", "ex-3"]),
                VocabularyEntry(name="fact-retrieval", definition="Retrieve a single fact", example_ids=["ex-4", "ex-5", "ex-6"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )

        async def judge_overlap(def1: str, def2: str) -> bool:
            return True  # always overlap
        result = await check_registry_consistency(registry, judge_overlap)
        assert result.passed is False


class TestValidateRationaleCardSet:
    @pytest.mark.asyncio
    async def test_valid_card_set_passes(self) -> None:
        async def no_overlap(d1: str, d2: str) -> bool:
            return False
        results = await validate_rationale_card_set(
            _make_card_set(),
            available_routes={"0", "1", "2"},
            dataset_size=20,
            judge_fn=no_overlap,
        )
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_returns_multiple_results(self) -> None:
        async def no_overlap(d1: str, d2: str) -> bool:
            return False
        results = await validate_rationale_card_set(
            _make_card_set(),
            available_routes={"0", "1", "2"},
            dataset_size=20,
            judge_fn=no_overlap,
        )
        # Should have dataset-level + per-card checks
        assert len(results) > 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_checks.py::TestCheckClusterThresholds -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement dataset-level checks and top-level runner**

Add to `odysseus/agents/routing_rationale_checks.py`:

```python
import math


# ---------------------------------------------------------------------------
# Dataset-level checks
# ---------------------------------------------------------------------------


def _min_cluster_size(dataset_size: int) -> int:
    """Minimum number of examples for a vocabulary entry: max(3, ceil(0.05 * dataset_size))."""
    return max(3, math.ceil(0.05 * dataset_size))


def check_cluster_thresholds(
    registry: VocabularyRegistry, dataset_size: int,
) -> RationaleCheckResult:
    """Check every registry entry meets the minimum cluster size."""
    threshold = _min_cluster_size(dataset_size)
    below: list[str] = []
    for vocab_name in ("intent_pattern", "complexity_structure", "ambiguity_tags"):
        for entry in getattr(registry, vocab_name):
            if len(entry.example_ids) < threshold:
                below.append(f"{vocab_name}.{entry.name} ({len(entry.example_ids)}/{threshold})")
    return RationaleCheckResult(
        passed=len(below) == 0,
        check_name="cluster_thresholds",
        severity="warning",
        details=f"Below threshold: {below}" if below else f"All entries meet threshold ({threshold})",
        affected_ids=[b.split(".")[1].split(" ")[0] for b in below],
    )


def check_pruning_cleanup(card_set: RationaleCardSet) -> RationaleCheckResult:
    """Check no cards reference entries absent from the registry."""
    intent_names = {e.name for e in card_set.registry.intent_pattern}
    complexity_names = {e.name for e in card_set.registry.complexity_structure}
    tag_names = {e.name for e in card_set.registry.ambiguity_tags}
    problems: list[str] = []
    affected: list[str] = []
    for card in card_set.cards.values():
        card_problems = []
        if card.intent_pattern not in intent_names:
            card_problems.append(f"intent_pattern {card.intent_pattern!r} not in registry")
        if card.complexity_structure not in complexity_names:
            card_problems.append(f"complexity_structure {card.complexity_structure!r} not in registry")
        invalid_tags = [t for t in card.ambiguity_tags if t not in tag_names]
        if invalid_tags:
            card_problems.append(f"unknown tags: {invalid_tags}")
        if card_problems:
            problems.extend(card_problems)
            affected.append(card.example_id)
    return RationaleCheckResult(
        passed=len(problems) == 0,
        check_name="pruning_cleanup",
        severity="critical",
        details="; ".join(problems) if problems else "All card values in registry",
        affected_ids=affected,
    )


def find_orphaned_examples(card_set: RationaleCardSet) -> RationaleCheckResult:
    """Find examples whose intent_pattern or complexity_structure was pruned."""
    intent_names = {e.name for e in card_set.registry.intent_pattern}
    complexity_names = {e.name for e in card_set.registry.complexity_structure}
    orphaned: list[str] = []
    for card in card_set.cards.values():
        if card.intent_pattern not in intent_names or card.complexity_structure not in complexity_names:
            orphaned.append(card.example_id)
    return RationaleCheckResult(
        passed=len(orphaned) == 0,
        check_name="orphaned_examples",
        severity="warning",
        details=f"Orphaned examples needing re-annotation: {orphaned}" if orphaned else "No orphaned examples",
        affected_ids=orphaned,
    )


async def check_registry_consistency(
    registry: VocabularyRegistry,
    judge_fn: Callable[[str, str], Awaitable[bool]],
) -> RationaleCheckResult:
    """Check no semantic overlap between entries in same vocabulary (LLM-judged)."""
    overlaps: list[str] = []
    for vocab_name in ("intent_pattern", "complexity_structure", "ambiguity_tags"):
        entries = getattr(registry, vocab_name)
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if await judge_fn(entries[i].definition, entries[j].definition):
                    overlaps.append(f"{vocab_name}: {entries[i].name!r} ↔ {entries[j].name!r}")
    return RationaleCheckResult(
        passed=len(overlaps) == 0,
        check_name="registry_consistency",
        severity="warning",
        details=f"Semantic overlaps found: {overlaps}" if overlaps else "No overlaps detected",
        affected_ids=[],
    )


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


async def validate_rationale_card_set(
    card_set: RationaleCardSet,
    available_routes: set[str],
    dataset_size: int,
    judge_fn: Callable[[str, str], Awaitable[bool]],
) -> list[RationaleCheckResult]:
    """Run all validation checks. Dataset-level first, then per-card."""
    results: list[RationaleCheckResult] = []

    # Dataset-level checks
    results.append(check_cluster_thresholds(card_set.registry, dataset_size))
    results.append(check_pruning_cleanup(card_set))
    results.append(find_orphaned_examples(card_set))
    results.append(await check_registry_consistency(card_set.registry, judge_fn))

    # Per-card checks (against the registry in the card_set, which should be post-pruning)
    for card in card_set.cards.values():
        results.append(check_required_fields(card, card_set.registry))
        results.append(check_vocabulary_membership(card, card_set.registry))
        results.append(check_disqualifier_coverage(card, available_routes))
        results.append(check_disqualifier_format(card))
        results.append(check_ambiguity_tag_membership(card, card_set.registry))

    return results
```

- [ ] **Step 4: Run all check tests**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_checks.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_checks.py tests/test_routing_rationale_checks.py
git commit -m "feat(thp-82): add dataset-level validation checks and top-level runner"
```

---

## Chunk 3: Registry Management

### Task 5: Content hashing and seed initialization

**Files:**
- Create: `odysseus/agents/routing_rationale_registry.py`
- Create: `tests/test_routing_rationale_registry.py`

- [ ] **Step 1: Write failing tests for hashing and seeds**

```python
"""Tests for odysseus.agents.routing_rationale_registry."""

from __future__ import annotations

from odysseus.agents.routing_rationale_registry import (
    compute_dataset_hash,
    create_seed_registry,
)
from odysseus.eval.models import Example, Expected, ModelCostQuality


def _make_example(id: str, input: str, route: str) -> Example:
    return Example(
        id=id,
        input=input,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split="dev",
    )


class TestComputeDatasetHash:
    def test_deterministic(self) -> None:
        examples = [_make_example("ex-1", "What is X?", "0"), _make_example("ex-2", "Compare A and B", "1")]
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(examples)
        assert h1 == h2

    def test_order_independent(self) -> None:
        ex1 = _make_example("ex-1", "What is X?", "0")
        ex2 = _make_example("ex-2", "Compare A and B", "1")
        h1 = compute_dataset_hash([ex1, ex2])
        h2 = compute_dataset_hash([ex2, ex1])
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_dataset_hash([_make_example("ex-1", "What is X?", "0")])
        h2 = compute_dataset_hash([_make_example("ex-1", "What is Y?", "0")])
        assert h1 != h2

    def test_hash_is_16_hex_chars(self) -> None:
        h = compute_dataset_hash([_make_example("ex-1", "What is X?", "0")])
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestCreateSeedRegistry:
    def test_seed_registry_structure(self) -> None:
        registry = create_seed_registry()
        assert len(registry.intent_pattern) == 0
        assert len(registry.complexity_structure) == 0
        assert len(registry.ambiguity_tags) == 4

    def test_seed_tag_names(self) -> None:
        registry = create_seed_registry()
        names = {e.name for e in registry.ambiguity_tags}
        assert names == {"AMBIGUOUS_COMPLEXITY", "AMBIGUOUS_DOMAIN", "POTENTIAL_MISLABEL", "BOUNDARY_CASE"}

    def test_seed_tags_have_definitions(self) -> None:
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.definition.strip() != ""

    def test_seed_tags_have_empty_example_ids(self) -> None:
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.example_ids == []

    def test_seed_tags_have_no_justification(self) -> None:
        registry = create_seed_registry()
        for entry in registry.ambiguity_tags:
            assert entry.justification is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement hashing and seeds**

Create `odysseus/agents/routing_rationale_registry.py`:

```python
"""Vocabulary registry management for routing rationale cards.

Handles content hashing, YAML persistence, append-only merging,
threshold-based pruning, and seed initialization.

See: docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-implementation.md
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from odysseus.agents.routing_rationale_models import VocabularyEntry, VocabularyRegistry
from odysseus.eval.models import Example


def compute_dataset_hash(examples: list[Example]) -> str:
    """Deterministic SHA-256 hash over sorted (id, input, route) tuples. Truncated to 16 hex chars."""
    tuples = sorted((ex.id, ex.input, ex.expected.route) for ex in examples)
    content = repr(tuples).encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


def create_seed_registry() -> VocabularyRegistry:
    """Create a fresh registry with only ambiguity_tags seeds."""
    return VocabularyRegistry(
        intent_pattern=[],
        complexity_structure=[],
        ambiguity_tags=[
            VocabularyEntry(
                name="AMBIGUOUS_COMPLEXITY",
                definition="Complexity signals point to different routes",
                example_ids=[],
            ),
            VocabularyEntry(
                name="AMBIGUOUS_DOMAIN",
                definition="Domain knowledge required to determine correct route",
                example_ids=[],
            ),
            VocabularyEntry(
                name="POTENTIAL_MISLABEL",
                definition="Ground-truth route assignment may be incorrect",
                example_ids=[],
            ),
            VocabularyEntry(
                name="BOUNDARY_CASE",
                definition="Example sits at the decision boundary between two routes",
                example_ids=[],
            ),
        ],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_registry.py tests/test_routing_rationale_registry.py
git commit -m "feat(thp-82): add dataset hashing and seed registry initialization"
```

### Task 6: Registry persistence (save/load/resolve)

**Files:**
- Modify: `odysseus/agents/routing_rationale_registry.py`
- Modify: `tests/test_routing_rationale_registry.py`

- [ ] **Step 1: Write failing tests for persistence**

Append to `tests/test_routing_rationale_registry.py`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from odysseus.agents.routing_rationale_models import VocabularyRegistry
from odysseus.agents.routing_rationale_registry import (
    load_registry,
    resolve_registry,
    save_registry,
)


class TestSaveLoadRegistry:
    def test_round_trip(self) -> None:
        registry = create_seed_registry()
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
            assert len(loaded.ambiguity_tags) == 4
            assert loaded.intent_pattern == []
            assert loaded.complexity_structure == []

    def test_preserves_entry_details(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(
                    name="factual-lookup",
                    definition="Single fact query",
                    example_ids=["ex-1", "ex-2", "ex-3"],
                    justification="New pattern",
                ),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.yaml"
            save_registry(registry, path)
            loaded = load_registry(path)
            entry = loaded.intent_pattern[0]
            assert entry.name == "factual-lookup"
            assert entry.definition == "Single fact query"
            assert entry.example_ids == ["ex-1", "ex-2", "ex-3"]
            assert entry.justification == "New pattern"


class TestResolveRegistry:
    def test_resolve_by_hash(self) -> None:
        registry = create_seed_registry()
        with TemporaryDirectory() as tmpdir:
            registry_dir = Path(tmpdir)
            save_registry(registry, registry_dir / "abc123.yaml")
            resolved = resolve_registry("abc123", registry_dir)
            assert resolved is not None
            assert len(resolved.ambiguity_tags) == 4

    def test_resolve_falls_back_to_inherit(self) -> None:
        registry = create_seed_registry()
        with TemporaryDirectory() as tmpdir:
            inherit_path = Path(tmpdir) / "parent.yaml"
            save_registry(registry, inherit_path)
            resolved = resolve_registry("nonexistent", Path(tmpdir) / "empty_dir", inherit_from=inherit_path)
            assert resolved is not None

    def test_resolve_returns_none_for_fresh_start(self) -> None:
        with TemporaryDirectory() as tmpdir:
            resolved = resolve_registry("nonexistent", Path(tmpdir))
            assert resolved is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py::TestSaveLoadRegistry -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement save/load/resolve**

Add to `odysseus/agents/routing_rationale_registry.py`:

```python
def save_registry(registry: VocabularyRegistry, path: Path) -> None:
    """Write registry to YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = registry.model_dump()
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_registry(path: Path) -> VocabularyRegistry:
    """Read registry from YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return VocabularyRegistry(**data)


def resolve_registry(
    dataset_hash: str,
    registry_dir: Path,
    inherit_from: Path | None = None,
) -> VocabularyRegistry | None:
    """Look up registry by content hash, fall back to inheritance, or return None.

    Lookup order:
    1. registry_dir/<dataset_hash>.yaml
    2. inherit_from path (if provided)
    3. None (caller should use create_seed_registry())
    """
    hash_path = registry_dir / f"{dataset_hash}.yaml"
    if hash_path.exists():
        return load_registry(hash_path)
    if inherit_from is not None and inherit_from.exists():
        return load_registry(inherit_from)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_registry.py tests/test_routing_rationale_registry.py
git commit -m "feat(thp-82): add registry persistence (save/load/resolve)"
```

### Task 7: Registry merge and prune

**Files:**
- Modify: `odysseus/agents/routing_rationale_registry.py`
- Modify: `tests/test_routing_rationale_registry.py`

- [ ] **Step 1: Write failing tests for merge and prune**

Append to `tests/test_routing_rationale_registry.py`:

```python
import pytest

from odysseus.agents.routing_rationale_registry import (
    RegistryMergeError,
    merge_registry,
    prune_registry,
)


class TestMergeRegistry:
    def test_append_new_entries(self) -> None:
        existing = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1", "ex-2", "ex-3"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        proposed = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1", "ex-2", "ex-3"]),
                VocabularyEntry(name="data-filtering", definition="d2", example_ids=["ex-4", "ex-5", "ex-6"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        merged = merge_registry(existing, proposed)
        assert len(merged.intent_pattern) == 2

    def test_removing_entry_raises(self) -> None:
        existing = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        proposed = VocabularyRegistry(
            intent_pattern=[],  # removed factual-lookup
            complexity_structure=[],
            ambiguity_tags=[],
        )
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)

    def test_renaming_entry_raises(self) -> None:
        existing = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="factual-lookup", definition="d", example_ids=["ex-1"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        proposed = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="fact-retrieval", definition="d", example_ids=["ex-1"])],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        with pytest.raises(RegistryMergeError):
            merge_registry(existing, proposed)


class TestPruneRegistry:
    def test_entries_above_threshold_kept(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=["a", "b", "c"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=20)
        assert len(pruned.intent_pattern) == 1
        assert removed == {"intent_pattern": [], "complexity_structure": [], "ambiguity_tags": []}

    def test_entries_below_threshold_pruned(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="factual-lookup", definition="d", example_ids=["a"]),
                VocabularyEntry(name="data-filtering", definition="d", example_ids=["b", "c", "d"]),
            ],
            complexity_structure=[],
            ambiguity_tags=[],
        )
        pruned, removed = prune_registry(registry, dataset_size=20)
        assert len(pruned.intent_pattern) == 1
        assert pruned.intent_pattern[0].name == "data-filtering"
        assert removed["intent_pattern"] == ["factual-lookup"]

    def test_prune_categorizes_by_vocabulary(self) -> None:
        registry = VocabularyRegistry(
            intent_pattern=[VocabularyEntry(name="rare-intent", definition="d", example_ids=["a"])],
            complexity_structure=[VocabularyEntry(name="rare-structure", definition="d", example_ids=["b"])],
            ambiguity_tags=[VocabularyEntry(name="RARE_TAG", definition="d", example_ids=["c"])],
        )
        _, removed = prune_registry(registry, dataset_size=20)
        assert "rare-intent" in removed["intent_pattern"]
        assert "rare-structure" in removed["complexity_structure"]
        assert "RARE_TAG" in removed["ambiguity_tags"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py::TestMergeRegistry -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement merge and prune**

Add to `odysseus/agents/routing_rationale_registry.py`:

```python
import math


class RegistryMergeError(Exception):
    """Raised when a proposed registry violates append-only semantics."""


def merge_registry(
    existing: VocabularyRegistry,
    proposed: VocabularyRegistry,
) -> VocabularyRegistry:
    """Merge proposed registry into existing, enforcing append-only semantics.

    Raises RegistryMergeError if existing entries are removed or renamed.
    """
    for vocab_name in ("intent_pattern", "complexity_structure", "ambiguity_tags"):
        existing_names = {e.name for e in getattr(existing, vocab_name)}
        proposed_names = {e.name for e in getattr(proposed, vocab_name)}
        removed = existing_names - proposed_names
        if removed:
            raise RegistryMergeError(
                f"Append-only violation in {vocab_name}: entries removed: {sorted(removed)}"
            )
    return proposed


def prune_registry(
    registry: VocabularyRegistry,
    dataset_size: int,
) -> tuple[VocabularyRegistry, dict[str, list[str]]]:
    """Remove entries below minimum cluster size threshold.

    Returns (pruned_registry, removed) where removed is a dict
    keyed by vocabulary name -> list of removed entry names.
    """
    threshold = max(3, math.ceil(0.05 * dataset_size))
    removed: dict[str, list[str]] = {
        "intent_pattern": [],
        "complexity_structure": [],
        "ambiguity_tags": [],
    }

    def _prune_entries(entries: list[VocabularyEntry], vocab_name: str) -> list[VocabularyEntry]:
        kept = []
        for entry in entries:
            if len(entry.example_ids) >= threshold:
                kept.append(entry)
            else:
                removed[vocab_name].append(entry.name)
        return kept

    pruned = VocabularyRegistry(
        intent_pattern=_prune_entries(registry.intent_pattern, "intent_pattern"),
        complexity_structure=_prune_entries(registry.complexity_structure, "complexity_structure"),
        ambiguity_tags=_prune_entries(registry.ambiguity_tags, "ambiguity_tags"),
    )
    return pruned, removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest tests/test_routing_rationale_registry.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/routing_rationale_registry.py tests/test_routing_rationale_registry.py
git commit -m "feat(thp-82): add registry merge (append-only) and prune functions"
```

---

## Chunk 4: Skills and Exports

### Task 8: classify-example skill

**Files:**
- Create: `odysseus/skills/classify-example/SKILL.md`
- Create: `odysseus/skills/classify-example/references/vocabulary-registry-rules.md`

- [ ] **Step 1: Create classify-example SKILL.md**

Create `odysseus/skills/classify-example/SKILL.md`:

```markdown
---
name: classify-example
description: >
  Jointly determine intent_pattern and complexity_structure for a routing
  example. Use when annotating dataset examples with routing rationale cards.
  Takes query text, ground-truth route, and vocabulary registry as input.
  Outputs field values and optionally proposes new vocabulary entries when
  no existing entry fits.
---

# Classify Example

Jointly determine `intent_pattern` and `complexity_structure` for a single routing example.

## Input

- Query text
- Ground-truth route assignment
- Current vocabulary registry

## Procedure

1. **Identify reasoning topology first.** Count the steps needed to answer the query. Check for dependencies between steps — does each step's output feed the next? Look for parallel vs sequential structure. This determines `complexity_structure`.

2. **Classify the task type.** Using the complexity structure to disambiguate, determine what kind of task the query represents. A query mentioning multiple data sources with sequential-dependency structure is a different intent than one with parallel-constraints structure, even if the surface topic is similar. This determines `intent_pattern`.

3. **Match against the vocabulary registry.** If an existing entry fits, use it. If no existing entry covers the observed pattern, propose a new entry:
   - Name: kebab-case (e.g., `cross-source-join`)
   - Definition: one sentence describing the observable pattern
   - Example IDs: list of examples exhibiting this pattern
   - Justification: why existing entries are insufficient

   See [vocabulary-registry-rules.md](references/vocabulary-registry-rules.md) for naming conventions and threshold rules.

## Output

- `intent_pattern`: string (kebab-case, from vocabulary registry)
- `complexity_structure`: string (kebab-case, from vocabulary registry)
- `proposed_entries`: (optional) list of new vocabulary entry proposals

## Common Mistakes

- **Confusing verbosity with complexity.** Long queries with many parallel constraints are not necessarily sequential dependencies. Count actual reasoning hops, not words.
- **Assuming domain-specific categories.** Do not start with preconceived intent categories. Let them emerge from the data. The vocabulary registry adapts to any routing domain.
- **Classifying intent before complexity.** Always determine reasoning topology first. Intent classification depends on understanding the complexity structure — classifying in the wrong order leads to lock-in errors.
- **Ignoring joint reasoning.** Intent and complexity inform each other. A query that looks like simple retrieval may actually require multi-step reasoning when you examine the dependencies.
```

- [ ] **Step 2: Create vocabulary-registry-rules.md reference**

Create `odysseus/skills/classify-example/references/vocabulary-registry-rules.md`:

```markdown
# Vocabulary Registry Rules

Shared rules governing all three dynamic vocabularies: `intent_pattern`, `complexity_structure`, and `ambiguity_tags`.

## Naming Conventions

| Vocabulary | Convention | Example |
|---|---|---|
| `intent_pattern` | kebab-case | `factual-lookup`, `data-filtering` |
| `complexity_structure` | kebab-case | `single-hop`, `sequential-dependency` |
| `ambiguity_tags` | SCREAMING_SNAKE_CASE | `AMBIGUOUS_COMPLEXITY`, `BOUNDARY_CASE` |

## Cluster Threshold

An entry is only included if it applies to at least `max(3, ceil(0.05 * dataset_size))` examples. This threshold applies uniformly — seed values and new entries alike.

## No Semantic Overlap

A new entry must not duplicate an existing one. Before proposing a new entry, check all existing entries in that vocabulary and explain why none of them cover the observed pattern. The routing analysis agent compares definitions within each vocabulary and flags duplicates.

## Append-Only Semantics

Across multiple runs on the same dataset, existing entries cannot be renamed or removed. New entries can be added. This ensures consistency. Dataset identity is determined by content hash.

## Proposing New Entries

Each proposal must include:
1. **Name** following the naming convention for its vocabulary
2. **Definition** — one sentence describing the observable pattern
3. **Example IDs** — which dataset examples exhibit this pattern
4. **Justification** — why existing entries are insufficient
```

- [ ] **Step 3: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add -f odysseus/skills/classify-example/
git commit -m "feat(thp-82): add classify-example annotation skill"
```

### Task 9: generate-routing-rationale skill

**Files:**
- Create: `odysseus/skills/generate-routing-rationale/SKILL.md`
- Create: `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md`

- [ ] **Step 1: Create generate-routing-rationale SKILL.md**

Create `odysseus/skills/generate-routing-rationale/SKILL.md`:

```markdown
---
name: generate-routing-rationale
description: >
  Produce tier_disqualifiers and propose ambiguity_tags for a routing example.
  Use after classify-example has determined intent and complexity. Takes query
  text, ground-truth route, classification output, and vocabulary registry.
  Outputs disqualifier list covering all non-assigned routes and candidate
  ambiguity tags.
---

# Generate Routing Rationale

Produce `tier_disqualifiers` and propose `ambiguity_tags` for a single routing example.

## Input

- Query text
- Ground-truth route assignment
- `intent_pattern` and `complexity_structure` from classify-example
- Current vocabulary registry
- Set of all available routes in the dataset

## Procedure

1. **Generate disqualifiers for each non-assigned route.** For every route in the dataset that is not the assigned route for this example, write a disqualifier explaining why that route is ruled out.
   - If routes have a natural ordering (e.g., tiers 0/1/2 by cost or complexity), work from lowest to highest.
   - If routes are unordered (e.g., named models or agents), iterate all non-assigned routes in alphabetical order.
   - See [disqualifier-guidelines.md](references/disqualifier-guidelines.md) for writing rules.

2. **Write each disqualifier as a single concise sentence** referencing an observable property of the query. Focus on what the query requires, not what the route target can or cannot do.

3. **Assess ambiguity.** Look for these signals:
   - A disqualifier was hard to write — the reasoning felt forced or unconvincing
   - The intent pattern or complexity structure pulled toward a different route than the assigned one
   - Multiple disqualifiers for the same route contradict each other
   If any signals are present, propose applicable ambiguity tags from the registry.

4. **Tags are candidates, not final.** The minimum cluster threshold is enforced during post-loop validation, not during annotation. Propose tags based on the evidence, even if only one example shows the pattern so far.

## Output

- `tier_disqualifiers`: list of `{route: string, reason: string}` covering every non-assigned route
- `ambiguity_tags`: list of candidate tag names (SCREAMING_SNAKE_CASE)
```

- [ ] **Step 2: Create disqualifier-guidelines.md reference**

Create `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md`:

```markdown
# Disqualifier Guidelines

Rules for writing tier disqualifiers in routing rationale cards.

## Core Principle

Disqualifiers describe what the **query** requires, never what the **route target** can or cannot do. Route identifiers are opaque strings — you do not know what model, agent, or system sits behind them.

## DO

Reference observable properties of the query:
- "query requires joining 3 independent sources"
- "query has a single unambiguous answer available from common knowledge"
- "answer depends on precise numerical thresholds not available without computation"
- "query asks for a creative generation task with subjective quality criteria"
- "resolution requires maintaining state across 4 dependent filtering steps"

## DON'T

Reference route target capabilities:
- "this route's model can't handle it"
- "too complex for this tier"
- "this route lacks the intelligence for multi-step reasoning"
- "route 0 is only for simple queries"

## Format Requirements

- The `route` field must exactly match the dataset's `expected.route` values — treat these as opaque strings
- Each `reason` is a single, concise sentence
- `reason` must be non-empty
- Every route in the dataset that is not the assigned route for this example must have at least one disqualifier

## Coverage Requirement

If the dataset has routes `{"0", "1", "2"}` and the example's assigned route is `"1"`, there must be disqualifier entries for both `"0"` and `"2"`. Missing coverage will be flagged during validation.
```

- [ ] **Step 3: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add -f odysseus/skills/generate-routing-rationale/
git commit -m "feat(thp-82): add generate-routing-rationale annotation skill"
```

### Task 10: Update exports and run full test suite

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Update __init__.py exports**

Add to `odysseus/agents/__init__.py`:

```python
from odysseus.agents.routing_rationale_checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_cluster_thresholds,
    check_disqualifier_coverage,
    check_disqualifier_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
    validate_rationale_card_set,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    TierDisqualifier,
    VocabularyEntry,
    VocabularyRegistry,
)
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
```

And add these names to the `__all__` list.

- [ ] **Step 2: Run full test suite**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run pytest -v`
Expected: All tests pass (existing 352 + new rationale tests)

- [ ] **Step 3: Run linter and type checker**

Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run ruff check odysseus/agents/routing_rationale_models.py odysseus/agents/routing_rationale_checks.py odysseus/agents/routing_rationale_registry.py`
Run: `cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema && uv run ruff format --check odysseus/agents/routing_rationale_models.py odysseus/agents/routing_rationale_checks.py odysseus/agents/routing_rationale_registry.py`

Fix any issues found.

- [ ] **Step 4: Commit**

```bash
cd ~/.config/superpowers/worktrees/project-odysseus/thp-82-routing-rationale-schema
git add odysseus/agents/__init__.py
git commit -m "feat(thp-82): export routing rationale models and checks from agents package"
```

---

## Task Dependency Graph

```
Task 1 (TierDisqualifier, RationaleCard)
  └─▶ Task 2 (VocabularyEntry, VocabularyRegistry, RationaleCardSet)
        ├─▶ Task 3 (Per-card checks) ──▶ Task 4 (Dataset-level checks + runner)
        ├─▶ Task 5 (Hashing + seeds) ──▶ Task 6 (Persistence) ──▶ Task 7 (Merge + prune)
        └─▶ Task 8 (classify-example skill) ─┐
            Task 9 (generate-routing-rationale skill) ─┤
                                                       └─▶ Task 10 (Exports + full test suite)
```

**Parallelizable after Task 2:**
- Tasks 3–4 (validation checks) are independent from Tasks 5–7 (registry management)
- Tasks 8–9 (skills) are independent from both
- Task 10 depends on all others
