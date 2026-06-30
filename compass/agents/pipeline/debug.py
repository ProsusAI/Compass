# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Shared debug-mode helpers for optional audit artifacts."""

from __future__ import annotations

import os


def is_debug_enabled() -> bool:
    """Return True iff debug-only audit artifacts should be written."""
    return os.getenv("COMPASS_DEBUG") == "1"
