"""Tests for MockEchoBackend."""

from __future__ import annotations

from odysseus.eval.backends.mock_echo import MockEchoBackend
from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example


def _make_profile() -> BackendProfile:
    return BackendProfile(
        model="mock-echo",
        type="mock_echo",
        requests_per_minute=10000,
        tokens_per_minute=1000000,
    )


async def test_echoes_expected_route():
    """MockEchoBackend returns output matching the expected route."""
    backend = MockEchoBackend(_make_profile())
    example = Example(
        id="ex-1",
        input="route me",
        expected={
            "route": "billing",
            "routes": {"billing": {"cost": 0.01, "quality_score": 0.9}},
        },
    )
    output, usage = await backend.call("prompt", example)
    assert output == {"route": "billing"}
    assert usage.input_tokens >= 0
    assert usage.output_tokens >= 0


async def test_model_name():
    backend = MockEchoBackend(_make_profile())
    assert backend.model_name == "mock-echo"


async def test_pricing_is_none():
    backend = MockEchoBackend(_make_profile())
    assert backend.pricing is None
