# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Shared test fixtures."""

import pytest

from compass.mcp.server import set_active_stage


@pytest.fixture(autouse=True)
def _disable_stage_filtering():
    """Disable MCP stage filtering so all tools are visible in tests.

    Individual tests that need to exercise stage scoping should call
    ``set_active_stage(...)`` explicitly within the test body.
    """
    set_active_stage(None)
    yield
    set_active_stage(None)
