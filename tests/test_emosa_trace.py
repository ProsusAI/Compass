"""Tests for odysseus.agents.prompt_builder.emosa_trace."""

from __future__ import annotations

import json

import pytest

import odysseus.agents.prompt_builder.emosa_trace as trace_mod
from odysseus.agents.prompt_builder.emosa_trace import record_metropolis_decision


def _reset_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_mod, "_attached_runs", set())


def test_record_metropolis_decision_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_mod, "EMOSA_TRACE_ENABLED", False)
    record_metropolis_decision(
        tmp_path,
        round=1,
        trajectory_id=0,
        parent_version="v1",
        child_version="v2",
        parent_energy=0.5,
        child_energy=0.4,
        delta_e=-0.1,
        temperature=1.0,
        p_accept=1.0,
        accepted=True,
    )
    assert not (tmp_path / "emosa_trace.jsonl").exists()


def test_record_metropolis_decision_enabled_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_mod, "EMOSA_TRACE_ENABLED", True)
    _reset_module(monkeypatch)

    record_metropolis_decision(
        tmp_path,
        round=1,
        trajectory_id=0,
        parent_version="v1",
        child_version="v2",
        parent_energy=0.5,
        child_energy=0.4,
        delta_e=-0.1,
        temperature=1.0,
        p_accept=1.0,
        accepted=True,
    )
    record_metropolis_decision(
        tmp_path,
        round=2,
        trajectory_id=1,
        parent_version="v3",
        child_version="v4",
        parent_energy=0.6,
        child_energy=0.7,
        delta_e=0.1,
        temperature=0.5,
        p_accept=0.8187307530779818,
        accepted=False,
    )

    jsonl_path = tmp_path / "emosa_trace.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    required_keys = {
        "round",
        "trajectory_id",
        "parent_version",
        "child_version",
        "parent_energy",
        "child_energy",
        "delta_e",
        "temperature",
        "p_accept",
        "accepted",
    }

    for line in lines:
        record = json.loads(line)
        assert set(record.keys()) == required_keys

    first = json.loads(lines[0])
    assert first["round"] == 1
    assert first["trajectory_id"] == 0
    assert first["accepted"] is True

    second = json.loads(lines[1])
    assert second["round"] == 2
    assert second["accepted"] is False


def test_record_metropolis_decision_handles_none_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_mod, "EMOSA_TRACE_ENABLED", True)
    _reset_module(monkeypatch)

    record_metropolis_decision(
        tmp_path,
        round=1,
        trajectory_id=2,
        parent_version=None,
        child_version="v1",
        parent_energy=None,
        child_energy=0.9,
        delta_e=None,
        temperature=2.0,
        p_accept=None,
        accepted=True,
    )

    jsonl_path = tmp_path / "emosa_trace.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["parent_version"] is None
    assert record["parent_energy"] is None
    assert record["delta_e"] is None
    assert record["p_accept"] is None
    assert record["accepted"] is True
    assert record["child_version"] == "v1"
