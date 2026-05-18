"""Test that stratified_split is available via data_validation_tools."""

import inspect


def test_tool_importable_from_data_validation_tools():
    from odysseus.mcp.data_validation_tools import stratified_split

    assert callable(stratified_split)


def test_tool_has_no_card_set_parameter():
    from odysseus.mcp.data_validation_tools import stratified_split

    sig = inspect.signature(stratified_split)
    param_names = set(sig.parameters.keys())
    assert "card_set_path" not in param_names
