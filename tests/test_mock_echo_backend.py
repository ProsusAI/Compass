# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for MockEchoBackend."""

from __future__ import annotations

from compass.eval.backends.mock_echo import MockEchoBackend
from compass.eval.backends.profile import BackendProfile
from compass.eval.models import Example, Expected


def _make_profile() -> BackendProfile:
    return BackendProfile(
        model="mock-echo",
        provider="mock_echo",
        requests_per_minute=10000,
        tokens_per_minute=1000000,
    )


async def test_echoes_expected_route():
    """MockEchoBackend returns output matching the expected route."""
    backend = MockEchoBackend(_make_profile())
    example = Example(
        id="ex-1",
        input="route me",
        expected=Expected.model_validate(
            {
                "route": "billing",
                "routes": {"billing": {"cost": 0.01, "quality_score": 0.9}},
            }
        ),
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
