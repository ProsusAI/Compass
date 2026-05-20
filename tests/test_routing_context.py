# tests/test_routing_context.py
"""Tests for relocated RoutingContext models."""

from compass.agents.routing_context import (
    RouteDefinition,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
)


def test_route_definition_creation():
    rd = RouteDefinition(name="simple", description="Simple queries")
    assert rd.name == "simple"
    assert rd.description == "Simple queries"


def test_routing_dimension_creation():
    dim = RoutingDimension(
        name="complexity",
        direction="higher_is_better",
        description="Query complexity",
    )
    assert dim.direction == "higher_is_better"


def test_route_ordering_creation():
    ordering = RouteOrdering(
        dimension="complexity",
        order=["simple", "moderate", "complex"],
    )
    assert len(ordering.order) == 3


def test_routing_context_without_seed_vocabulary():
    """RoutingContext no longer has seed_vocabulary field."""
    ctx = RoutingContext(
        domain="customer support",
        routes=[RouteDefinition(name="simple", description="Simple")],
        routing_dimensions=[
            RoutingDimension(
                name="complexity",
                direction="higher_is_better",
                description="Complexity",
            )
        ],
    )
    assert ctx.domain == "customer support"
    assert "seed_vocabulary" not in RoutingContext.model_fields


def test_routing_context_serialization_roundtrip():
    ctx = RoutingContext(
        domain="test",
        routes=[RouteDefinition(name="a", description="A")],
        routing_dimensions=[
            RoutingDimension(
                name="cost",
                direction="lower_is_better",
                description="Cost",
            )
        ],
        route_ordering=RouteOrdering(dimension="cost", order=["a"]),
    )
    data = ctx.model_dump()
    restored = RoutingContext.model_validate(data)
    assert restored.domain == ctx.domain
    assert restored.route_ordering is not None
    assert restored.route_ordering.order == ["a"]
