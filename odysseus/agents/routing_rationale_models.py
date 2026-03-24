"""Pydantic models for the routing rationale schema (THP-82).

Design spec: docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-schema.md

This module defines the foundational data structures for annotating routing
examples with structured rationale cards and a dynamic vocabulary registry.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

# ---------------------------------------------------------------------------
# Regex constants (exported for use by other modules)
# ---------------------------------------------------------------------------

KEBAB_CASE_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SCREAMING_SNAKE_RE: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


# ---------------------------------------------------------------------------
# RouteExclusion
# ---------------------------------------------------------------------------


class RouteExclusion(BaseModel):
    """A single route exclusion record for a rationale card.

    Fields:
        route: The route identifier that was ruled out (non-empty).
        reason: Why this route was ruled out (non-empty).
    """

    route: str
    reason: str

    @field_validator("route")
    @classmethod
    def route_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("route must be non-empty")
        return v.strip()

    @field_validator("reason")
    @classmethod
    def reason_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must be non-empty")
        return v.strip()




# ---------------------------------------------------------------------------
# RationaleCard
# ---------------------------------------------------------------------------


class RationaleCard(BaseModel):
    """Structured annotation for a single routing example.

    Fields:
        example_id: ID of the corresponding dataset example (non-empty).
        assigned_route: The route this example is assigned to (non-empty).
        intent_pattern: Task type the query represents (kebab-case).
        complexity_structure: Reasoning topology required (kebab-case).
        route_exclusions: Why specific routes are ruled out.
        ambiguity_tags: Controlled vocabulary labels for boundary examples
            (each must be SCREAMING_SNAKE_CASE).
    """

    example_id: str
    assigned_route: str
    intent_pattern: str
    complexity_structure: str
    route_exclusions: list[RouteExclusion]
    ambiguity_tags: list[str]

    @field_validator("example_id")
    @classmethod
    def example_id_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("example_id must be non-empty")
        return v.strip()

    @field_validator("assigned_route")
    @classmethod
    def assigned_route_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("assigned_route must be non-empty")
        return v.strip()

    @field_validator("intent_pattern")
    @classmethod
    def intent_pattern_must_be_kebab_case(cls, v: str) -> str:
        if not KEBAB_CASE_RE.fullmatch(v):
            raise ValueError("intent_pattern must be kebab-case (e.g. 'data-analysis')")
        return v

    @field_validator("complexity_structure")
    @classmethod
    def complexity_structure_must_be_kebab_case(cls, v: str) -> str:
        if not KEBAB_CASE_RE.fullmatch(v):
            raise ValueError("complexity_structure must be kebab-case (e.g. 'multi-step-reasoning')")
        return v

    @field_validator("ambiguity_tags")
    @classmethod
    def ambiguity_tags_must_be_screaming_snake(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not SCREAMING_SNAKE_RE.fullmatch(tag):
                raise ValueError(f"ambiguity_tags entries must be SCREAMING_SNAKE_CASE, got {tag!r}")
        return v


# ---------------------------------------------------------------------------
# VocabularyEntry
# ---------------------------------------------------------------------------


class VocabularyEntry(BaseModel):
    """A single entry in the vocabulary registry.

    Fields:
        name: Vocabulary term (non-empty). Naming convention depends on which
            registry list this entry belongs to (kebab-case for intent/complexity,
            SCREAMING_SNAKE_CASE for ambiguity_tags).
        definition: Human-readable description of the term (non-empty).
        example_ids: Dataset example IDs supporting this entry.
        justification: Optional rationale for adding this entry (e.g. run context).
    """

    name: str
    definition: str
    example_ids: list[str]
    justification: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()

    @field_validator("definition")
    @classmethod
    def definition_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("definition must be non-empty")
        return v.strip()


# ---------------------------------------------------------------------------
# VocabularyRegistry
# ---------------------------------------------------------------------------


class VocabularyRegistry(BaseModel):
    """Dynamic vocabulary registry for all annotation dimensions.

    Fields:
        intent_pattern: Vocabulary entries for intent patterns (kebab-case names).
        complexity_structure: Vocabulary entries for complexity structures (kebab-case names).
        ambiguity_tags: Vocabulary entries for ambiguity tags (SCREAMING_SNAKE_CASE names).

    Cross-field validation:
        intent_pattern and complexity_structure entries must have kebab-case names.
        ambiguity_tags entries must have SCREAMING_SNAKE_CASE names.
    """

    intent_pattern: list[VocabularyEntry]
    complexity_structure: list[VocabularyEntry]
    ambiguity_tags: list[VocabularyEntry]

    @model_validator(mode="after")
    def validate_entry_naming_conventions(self) -> VocabularyRegistry:
        for entry in self.intent_pattern:
            if not KEBAB_CASE_RE.fullmatch(entry.name):
                raise ValueError(f"intent_pattern entries must have kebab-case names, got {entry.name!r}")
        for entry in self.complexity_structure:
            if not KEBAB_CASE_RE.fullmatch(entry.name):
                raise ValueError(f"complexity_structure entries must have kebab-case names, got {entry.name!r}")
        for entry in self.ambiguity_tags:
            if not SCREAMING_SNAKE_RE.fullmatch(entry.name):
                raise ValueError(f"ambiguity_tags entries must have SCREAMING_SNAKE_CASE names, got {entry.name!r}")
        return self


# ---------------------------------------------------------------------------
# Routing Context (domain-agnostic routing configuration)
# ---------------------------------------------------------------------------


class RouteDefinition(BaseModel):
    """A single route target in the routing system."""

    name: str
    description: str

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        return v.strip()


class RoutingDimension(BaseModel):
    """A dimension along which routes differ (e.g., cost, capability)."""

    name: str
    direction: Literal["lower_is_better", "higher_is_better"]
    description: str

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        return v.strip()


class RouteOrdering(BaseModel):
    """Optional ordering of routes along a specific dimension."""

    dimension: str
    order: list[str]

    @field_validator("order")
    @classmethod
    def order_must_be_non_empty(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("order must contain at least one route")
        return v


class SeedVocabulary(BaseModel):
    """Optional seed vocabulary for bootstrapping annotation."""

    intent_pattern: list[VocabularyEntry] = []
    complexity_structure: list[VocabularyEntry] = []
    ambiguity_tags: list[VocabularyEntry] = []


class RoutingContext(BaseModel):
    """Domain-agnostic routing configuration passed to annotation skills."""

    domain: str
    routes: list[RouteDefinition]
    routing_dimensions: list[RoutingDimension]
    route_ordering: RouteOrdering | None = None
    seed_vocabulary: SeedVocabulary | None = None

    @field_validator("routes")
    @classmethod
    def routes_must_be_non_empty(cls, v: list[RouteDefinition]) -> list[RouteDefinition]:
        if len(v) == 0:
            raise ValueError("routes must contain at least one route")
        return v

    @field_validator("routing_dimensions")
    @classmethod
    def dimensions_must_be_non_empty(cls, v: list[RoutingDimension]) -> list[RoutingDimension]:
        if len(v) == 0:
            raise ValueError("routing_dimensions must contain at least one dimension")
        return v


# ---------------------------------------------------------------------------
# RationaleCardSet
# ---------------------------------------------------------------------------


class RationaleCardSet(BaseModel):
    """A complete set of rationale cards for a dataset, with its registry.

    Fields:
        cards: Mapping from example_id to RationaleCard.
        dataset_hash: Content hash of the dataset this set was built from (non-empty).
        registry: Vocabulary registry for this card set.
        created_at: Timestamp when this card set was created.
        inherited_from: Optional hash of a previous dataset this registry was
            inherited from (via --inherit-registry-from).
    """

    cards: dict[str, RationaleCard]
    dataset_hash: str
    registry: VocabularyRegistry
    created_at: datetime
    inherited_from: str | None = None

    @field_validator("dataset_hash")
    @classmethod
    def dataset_hash_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("dataset_hash must be non-empty")
        return v.strip()
