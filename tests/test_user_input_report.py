"""Tests for the validated input report contract."""

from odysseus.agents.user_input_report import (
    CONTEXT_KEY,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
)


def test_context_key_is_non_empty_string():
    assert isinstance(CONTEXT_KEY, str)
    assert len(CONTEXT_KEY) > 0


def test_status_proceed_value():
    assert STATUS_PROCEED == "proceed"


def test_status_proceed_with_defaults_value():
    assert STATUS_PROCEED_WITH_DEFAULTS == "proceed_with_defaults"


def test_status_clarification_required_value():
    assert STATUS_CLARIFICATION_REQUIRED == "clarification_required"
