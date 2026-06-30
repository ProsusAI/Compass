# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""User input — input report constants and status handling."""

from __future__ import annotations

from compass.agents.user_input.report import (
    CONTEXT_KEY,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    read_status,
)

__all__ = [
    "CONTEXT_KEY",
    "STATUS_PROCEED",
    "STATUS_PROCEED_WITH_DEFAULTS",
    "read_status",
]
