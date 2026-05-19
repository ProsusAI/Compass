"""Shared debug-mode helpers for optional audit artifacts."""

from __future__ import annotations

import os


def is_debug_enabled() -> bool:
    """Return True iff debug-only audit artifacts should be written."""
    return os.getenv("ODYSSEUS_DEBUG") == "1"
