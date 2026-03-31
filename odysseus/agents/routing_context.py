# odysseus/agents/routing_context.py
"""Domain-agnostic routing context models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


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


class RoutingContext(BaseModel):
    """Domain-agnostic routing configuration.

    Synthesized by the Data Validation Agent from the dataset
    and user-provided problem description.
    """

    domain: str
    routes: list[RouteDefinition]
    routing_dimensions: list[RoutingDimension]
    route_ordering: RouteOrdering | None = None

    @field_validator("routes")
    @classmethod
    def routes_must_be_non_empty(cls, v: list[RouteDefinition]) -> list[RouteDefinition]:
        if len(v) == 0:
            raise ValueError("routes must contain at least one route")
        return v

    @field_validator("routing_dimensions")
    @classmethod
    def dimensions_must_be_non_empty(
        cls, v: list[RoutingDimension]
    ) -> list[RoutingDimension]:
        if len(v) == 0:
            raise ValueError("routing_dimensions must contain at least one dimension")
        return v
