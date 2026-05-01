"""Test that stratified_split_tool is available via data_validation_tools."""

import inspect


def test_tool_importable_from_data_validation_tools():
    from odysseus.mcp.data_validation_tools import stratified_split_tool

    assert callable(stratified_split_tool)


def test_tool_has_no_card_set_parameter():
    from odysseus.mcp.data_validation_tools import stratified_split_tool

    sig = inspect.signature(stratified_split_tool)
    param_names = set(sig.parameters.keys())
    assert "card_set_path" not in param_names
