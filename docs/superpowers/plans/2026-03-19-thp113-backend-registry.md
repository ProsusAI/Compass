# THP-113 Backend Registry & Client Abstraction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a file-based backend registry that loads YAML profiles and constructs `LiteLLMBackend` instances satisfying the `Backend` protocol.

**Architecture:** One YAML file per backend profile in a `backends/` directory. A `BackendProfile` Pydantic model validates each file. `BackendRegistry` loads profiles by directory, `LiteLLMBackend` wraps `litellm.acompletion()`. Rate limits move from `ConcurrencyConfig` to backend profiles, bridged to the controller via `RunDependencies`.

**Tech Stack:** Python 3.11+, Pydantic v2, LiteLLM (already in deps), PyYAML, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-19-thp113-backend-registry-design.md`

---

## Chunk 1: BackendProfile Model + Tests

### Task 1: BackendProfile — Failing Tests

**Files:**
- Create: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for BackendProfile**

```python
"""Tests for backend profile, registry, and LiteLLM backend."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import pytest
import yaml
from pydantic import ValidationError


# --- BackendProfile tests ---


def test_profile_valid_minimal():
    """Minimal valid profile loads correctly."""
    from odysseus.eval.backends.profile import BackendProfile

    p = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    assert p.model == "gpt-4o"
    assert p.requests_per_minute == 100
    assert p.tokens_per_minute == 50000
    assert p.api_key_env is None
    assert p.api_base is None
    assert p.max_tokens is None
    assert p.temperature is None
    assert p.pricing_model is None
    assert p.extra_params == {}
    assert p.provider_params == {}


def test_profile_valid_full():
    """Full profile with all fields loads correctly."""
    from odysseus.eval.backends.profile import BackendProfile

    p = BackendProfile(
        model="claude-sonnet-4-20250514",
        pricing_model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        api_base="https://proxy.example.com",
        requests_per_minute=100,
        tokens_per_minute=80000,
        max_tokens=1024,
        temperature=0.0,
        extra_params={"reasoning_effort": "high"},
        provider_params={"aws_region_name": "us-east-1"},
    )
    assert p.model == "claude-sonnet-4-20250514"
    assert p.pricing_model == "claude-sonnet-4-20250514"
    assert p.max_tokens == 1024
    assert p.extra_params == {"reasoning_effort": "high"}
    assert p.provider_params == {"aws_region_name": "us-east-1"}


def test_profile_missing_model_rejected():
    """Missing model field raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(requests_per_minute=100, tokens_per_minute=50000)  # type: ignore[call-arg]


def test_profile_empty_model_rejected():
    """Empty model string raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="", requests_per_minute=100, tokens_per_minute=50000)


def test_profile_whitespace_model_rejected():
    """Whitespace-only model string raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="   ", requests_per_minute=100, tokens_per_minute=50000)


def test_profile_model_stripped():
    """Model string is stripped of whitespace."""
    from odysseus.eval.backends.profile import BackendProfile

    p = BackendProfile(model="  gpt-4o  ", requests_per_minute=100, tokens_per_minute=50000)
    assert p.model == "gpt-4o"


def test_profile_missing_rpm_rejected():
    """Missing requests_per_minute raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="gpt-4o", tokens_per_minute=50000)  # type: ignore[call-arg]


def test_profile_missing_tpm_rejected():
    """Missing tokens_per_minute raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="gpt-4o", requests_per_minute=100)  # type: ignore[call-arg]


def test_profile_rpm_zero_rejected():
    """Zero RPM raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="gpt-4o", requests_per_minute=0, tokens_per_minute=50000)


def test_profile_tpm_negative_rejected():
    """Negative TPM raises ValidationError."""
    from odysseus.eval.backends.profile import BackendProfile

    with pytest.raises(ValidationError):
        BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=-1)


def test_profile_effective_pricing_model_default():
    """effective_pricing_model returns model when pricing_model is None."""
    from odysseus.eval.backends.profile import BackendProfile

    p = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    assert p.effective_pricing_model == "gpt-4o"


def test_profile_effective_pricing_model_override():
    """effective_pricing_model returns pricing_model when set."""
    from odysseus.eval.backends.profile import BackendProfile

    p = BackendProfile(
        model="bedrock/anthropic.claude-3-sonnet",
        pricing_model="claude-sonnet-4-20250514",
        requests_per_minute=100,
        tokens_per_minute=50000,
    )
    assert p.effective_pricing_model == "claude-sonnet-4-20250514"


def test_profile_from_yaml_valid():
    """from_yaml loads a valid YAML file."""
    from odysseus.eval.backends.profile import BackendProfile

    data = {"model": "gpt-4o", "requests_per_minute": 100, "tokens_per_minute": 50000}
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)
    try:
        p = BackendProfile.from_yaml(path)
        assert p.model == "gpt-4o"
        assert p.requests_per_minute == 100
    finally:
        path.unlink()


def test_profile_from_yaml_with_all_fields():
    """from_yaml loads all optional fields."""
    from odysseus.eval.backends.profile import BackendProfile

    data = {
        "model": "vertex_ai/gemini-2.5-pro",
        "requests_per_minute": 200,
        "tokens_per_minute": 100000,
        "max_tokens": 2048,
        "temperature": 0.5,
        "provider_params": {"vertex_project": "my-project", "vertex_location": "us-central1"},
        "extra_params": {"reasoning_effort": "medium"},
    }
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)
    try:
        p = BackendProfile.from_yaml(path)
        assert p.model == "vertex_ai/gemini-2.5-pro"
        assert p.provider_params["vertex_project"] == "my-project"
        assert p.extra_params["reasoning_effort"] == "medium"
    finally:
        path.unlink()


def test_profile_from_yaml_missing_required_field():
    """from_yaml raises ValidationError for missing required fields."""
    from odysseus.eval.backends.profile import BackendProfile

    data = {"model": "gpt-4o"}  # missing rate limits
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)
    try:
        with pytest.raises(ValidationError):
            BackendProfile.from_yaml(path)
    finally:
        path.unlink()


def test_profile_from_yaml_malformed_yaml():
    """from_yaml raises yaml.YAMLError for malformed YAML."""
    from odysseus.eval.backends.profile import BackendProfile

    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(":\n  invalid: [yaml\n  broken")
        path = Path(f.name)
    try:
        with pytest.raises(yaml.YAMLError):
            BackendProfile.from_yaml(path)
    finally:
        path.unlink()


def test_profile_from_yaml_non_mapping():
    """from_yaml raises ValueError for non-mapping YAML (e.g. a plain string)."""
    from odysseus.eval.backends.profile import BackendProfile

    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write('"just a string"')
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            BackendProfile.from_yaml(path)
    finally:
        path.unlink()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.eval.backends'`

### Task 2: BackendProfile — Implementation

**Files:**
- Create: `odysseus/eval/backends/__init__.py`
- Create: `odysseus/eval/backends/profile.py`

- [ ] **Step 3: Create the backends package init**

```python
"""Backend registry and client abstraction."""
```

- [ ] **Step 4: Implement BackendProfile**

```python
"""Backend profile model — validated configuration loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class BackendProfile(BaseModel):
    """Validated backend configuration loaded from YAML.

    Fields:
        model: LiteLLM model string (e.g. "claude-sonnet-4-20250514").
        pricing_model: Override for MODEL_PRICING lookup. Defaults to model.
        api_key_env: Env var name for API key (e.g. "ANTHROPIC_API_KEY").
        api_base: Custom endpoint URL.
        requests_per_minute: RPM rate limit (required, >= 1).
        tokens_per_minute: TPM rate limit (required, >= 1).
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        extra_params: Passthrough generation kwargs (reasoning_effort, thinking, etc.).
        provider_params: Provider auth/config (Vertex, Bedrock, etc.).
    """

    model: str
    pricing_model: str | None = None
    api_key_env: str | None = None
    api_base: str | None = None

    requests_per_minute: int
    tokens_per_minute: int

    max_tokens: int | None = None
    temperature: float | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    provider_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def model_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model must be non-empty")
        return v.strip()

    @field_validator("requests_per_minute", "tokens_per_minute")
    @classmethod
    def rate_limits_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v

    @property
    def effective_pricing_model(self) -> str:
        """Model name for pricing lookup. Defaults to model if pricing_model is not set."""
        return self.pricing_model or self.model

    @classmethod
    def from_yaml(cls, path: str | Path) -> BackendProfile:
        """Load profile from YAML file.

        Raises:
            yaml.YAMLError: Malformed YAML.
            ValueError: YAML content is not a mapping.
            pydantic.ValidationError: Invalid field values or missing required fields.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
        return cls(**data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py -v`
Expected: All BackendProfile tests PASS

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check odysseus/eval/backends/ tests/test_backends.py && uv run ruff format odysseus/eval/backends/ tests/test_backends.py`

- [ ] **Step 7: Commit**

```bash
git add odysseus/eval/backends/__init__.py odysseus/eval/backends/profile.py tests/test_backends.py
git commit -m "feat(eval): add BackendProfile model with YAML loading and validation"
```

---

## Chunk 2: BackendRegistry + Tests

### Task 3: BackendRegistry — Failing Tests

**Files:**
- Modify: `tests/test_backends.py`

- [ ] **Step 8: Add registry tests to test_backends.py**

Append these tests to `tests/test_backends.py`:

```python
# --- BackendRegistry tests ---


def test_registry_from_directory_loads_profiles():
    """from_directory loads all .yaml files from a directory."""
    from odysseus.eval.backends.registry import BackendRegistry

    with TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        _write_profile(p / "fast.yaml", model="gpt-4o-mini", rpm=1000, tpm=200000)
        _write_profile(p / "quality.yaml", model="claude-sonnet-4-20250514", rpm=100, tpm=80000)

        registry = BackendRegistry.from_directory(p)
        assert sorted(registry.list_profiles()) == ["fast", "quality"]


def test_registry_from_directory_label_is_stem():
    """Profile label is the filename stem."""
    from odysseus.eval.backends.registry import BackendRegistry

    with TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        _write_profile(p / "my-backend.yaml", model="gpt-4o", rpm=100, tpm=50000)

        registry = BackendRegistry.from_directory(p)
        assert "my-backend" in registry.list_profiles()


def test_registry_yaml_precedence_over_yml():
    """.yaml takes precedence over .yml for the same stem."""
    from odysseus.eval.backends.registry import BackendRegistry

    with TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        _write_profile(p / "backend.yaml", model="from-yaml", rpm=100, tpm=50000)
        _write_profile(p / "backend.yml", model="from-yml", rpm=100, tpm=50000)

        registry = BackendRegistry.from_directory(p)
        profile = registry.get_profile("backend")
        assert profile.model == "from-yaml"


def test_registry_loads_yml_if_no_yaml():
    """.yml files are loaded when no .yaml exists for that stem."""
    from odysseus.eval.backends.registry import BackendRegistry

    with TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        _write_profile(p / "only-yml.yml", model="yml-model", rpm=100, tpm=50000)

        registry = BackendRegistry.from_directory(p)
        profile = registry.get_profile("only-yml")
        assert profile.model == "yml-model"


def test_registry_get_profile_unknown_raises():
    """get_profile raises KeyError for unknown label."""
    from odysseus.eval.backends.registry import BackendRegistry

    registry = BackendRegistry()
    with pytest.raises(KeyError, match="Unknown backend profile"):
        registry.get_profile("nonexistent")


def test_registry_get_profile_returns_profile():
    """get_profile returns the correct BackendProfile."""
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.backends.registry import BackendRegistry

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    registry = BackendRegistry(profiles={"test": profile})
    assert registry.get_profile("test") is profile


def test_registry_empty_directory():
    """Empty directory produces empty registry."""
    from odysseus.eval.backends.registry import BackendRegistry

    with TemporaryDirectory() as tmpdir:
        registry = BackendRegistry.from_directory(Path(tmpdir))
        assert registry.list_profiles() == []


def test_registry_inject_profiles_directly():
    """Profiles can be injected via __init__ without filesystem."""
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.backends.registry import BackendRegistry

    profiles = {
        "a": BackendProfile(model="model-a", requests_per_minute=100, tokens_per_minute=50000),
        "b": BackendProfile(model="model-b", requests_per_minute=200, tokens_per_minute=100000),
    }
    registry = BackendRegistry(profiles=profiles)
    assert sorted(registry.list_profiles()) == ["a", "b"]


# --- Test helper ---


def _write_profile(path: Path, model: str, rpm: int, tpm: int) -> None:
    """Write a minimal backend profile YAML."""
    data = {"model": model, "requests_per_minute": rpm, "tokens_per_minute": tpm}
    with open(path, "w") as f:
        yaml.dump(data, f)
```

- [ ] **Step 9: Run tests to verify new tests fail**

Run: `uv run pytest tests/test_backends.py -k "registry" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.eval.backends.registry'`

### Task 4: BackendRegistry — Implementation

**Files:**
- Create: `odysseus/eval/backends/registry.py`

- [ ] **Step 10: Implement BackendRegistry**

```python
"""Backend registry — loads profiles from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path

from odysseus.eval.backends.litellm_backend import LiteLLMBackend
from odysseus.eval.backends.profile import BackendProfile


class BackendRegistry:
    """Loads and indexes backend profiles by label (filename stem).

    Usage:
        registry = BackendRegistry.from_directory(Path("backends"))
        backend = registry.create_backend("claude-sonnet")
    """

    def __init__(self, profiles: dict[str, BackendProfile] | None = None) -> None:
        self._profiles: dict[str, BackendProfile] = profiles or {}

    @classmethod
    def from_directory(cls, path: Path) -> BackendRegistry:
        """Load all .yaml/.yml files from a directory. Label = filename stem.

        .yaml takes precedence over .yml for the same stem.
        Caller must provide the path (no default).
        """
        profiles: dict[str, BackendProfile] = {}
        for file in sorted(path.glob("*.yaml")):
            profiles[file.stem] = BackendProfile.from_yaml(file)
        for file in sorted(path.glob("*.yml")):
            if file.stem not in profiles:
                profiles[file.stem] = BackendProfile.from_yaml(file)
        return cls(profiles)

    def get_profile(self, label: str) -> BackendProfile:
        """Return profile by label. Raises KeyError if not found."""
        if label not in self._profiles:
            raise KeyError(f"Unknown backend profile: '{label}'. Available: {list(self._profiles.keys())}")
        return self._profiles[label]

    def create_backend(self, label: str) -> LiteLLMBackend:
        """Construct a LiteLLMBackend from a named profile."""
        return LiteLLMBackend(self.get_profile(label))

    def list_profiles(self) -> list[str]:
        """Return available profile labels."""
        return list(self._profiles.keys())
```

Note: This file imports `LiteLLMBackend` which doesn't exist yet. The registry tests don't call `create_backend`, so they will pass. We'll test `create_backend` in Chunk 3.

- [ ] **Step 11: Run all backend tests**

Run: `uv run pytest tests/test_backends.py -v`
Expected: All BackendProfile and BackendRegistry tests PASS

- [ ] **Step 12: Lint and format**

Run: `uv run ruff check odysseus/eval/backends/ tests/test_backends.py && uv run ruff format odysseus/eval/backends/ tests/test_backends.py`

- [ ] **Step 13: Commit**

```bash
git add odysseus/eval/backends/registry.py tests/test_backends.py
git commit -m "feat(eval): add BackendRegistry with directory loading and label lookup"
```

---

## Chunk 3: LiteLLMBackend + Tests

### Task 5: LiteLLMBackend — Failing Tests

**Files:**
- Modify: `tests/test_backends.py`

- [ ] **Step 14: Add LiteLLMBackend tests to test_backends.py**

Append these tests to `tests/test_backends.py` (add imports at the top of the file: `import os` and `from unittest.mock import AsyncMock, MagicMock, patch`):

```python
# --- LiteLLMBackend tests ---


def test_backend_model_name_default():
    """model_name returns model when pricing_model is not set."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    backend = LiteLLMBackend(profile)
    assert backend.model_name == "gpt-4o"


def test_backend_model_name_pricing_override():
    """model_name returns pricing_model when set."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile

    profile = BackendProfile(
        model="bedrock/anthropic.claude-3-sonnet",
        pricing_model="claude-sonnet-4-20250514",
        requests_per_minute=100,
        tokens_per_minute=50000,
    )
    backend = LiteLLMBackend(profile)
    assert backend.model_name == "claude-sonnet-4-20250514"


def test_backend_missing_env_var_raises():
    """Construction fails if api_key_env references a missing env var."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile

    profile = BackendProfile(
        model="gpt-4o",
        api_key_env="NONEXISTENT_KEY_FOR_TEST_12345",
        requests_per_minute=100,
        tokens_per_minute=50000,
    )
    with pytest.raises(KeyError):
        LiteLLMBackend(profile)


def test_backend_api_key_not_in_repr():
    """API key should not appear in repr (SecretStr protection)."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile

    os.environ["_TEST_API_KEY"] = "sk-super-secret-123"
    try:
        profile = BackendProfile(
            model="gpt-4o",
            api_key_env="_TEST_API_KEY",
            requests_per_minute=100,
            tokens_per_minute=50000,
        )
        backend = LiteLLMBackend(profile)
        assert "sk-super-secret-123" not in repr(backend._api_key)
    finally:
        del os.environ["_TEST_API_KEY"]


async def test_backend_call_passes_kwargs():
    """call() passes all profile fields to litellm.acompletion."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.models import Example

    os.environ["_TEST_API_KEY"] = "sk-test"
    try:
        profile = BackendProfile(
            model="gpt-4o",
            api_key_env="_TEST_API_KEY",
            api_base="https://proxy.example.com",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=512,
            temperature=0.7,
            provider_params={"organization": "org-123"},
            extra_params={"seed": 42},
        )
        backend = LiteLLMBackend(profile)
        example = Example(id="ex-1", input={"q": "test"}, expected={"a": "answer"})

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.cache_read_input_tokens = 2

        mock_choice = MagicMock()
        mock_choice.message.content = "response text"

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_call:
            output, usage = await backend.call("You are a router.", example)

            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args
            assert call_kwargs.kwargs["model"] == "gpt-4o"
            assert call_kwargs.kwargs["api_key"] == "sk-test"
            assert call_kwargs.kwargs["base_url"] == "https://proxy.example.com"
            assert call_kwargs.kwargs["max_tokens"] == 512
            assert call_kwargs.kwargs["temperature"] == 0.7
            assert call_kwargs.kwargs["organization"] == "org-123"
            assert call_kwargs.kwargs["seed"] == 42
    finally:
        del os.environ["_TEST_API_KEY"]


async def test_backend_call_token_normalisation():
    """call() normalises LiteLLM usage to Anthropic-style TokenUsage."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.models import Example

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    backend = LiteLLMBackend(profile)
    example = Example(id="ex-1", input={"q": "test"}, expected={"a": "answer"})

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 25
    mock_usage.cache_read_input_tokens = 15

    mock_choice = MagicMock()
    mock_choice.message.content = "output"

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        output, token_usage = await backend.call("prompt", example)

        assert token_usage.input_tokens == 100
        assert token_usage.cached_tokens == 15
        assert token_usage.output_tokens == 25
        assert output == {"content": "output"}


async def test_backend_call_no_cache_tokens():
    """call() defaults cached_tokens to 0 when not present in response."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.models import Example

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    backend = LiteLLMBackend(profile)
    example = Example(id="ex-1", input={"q": "test"}, expected={"a": "answer"})

    mock_usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
    mock_usage.prompt_tokens = 50
    mock_usage.completion_tokens = 10

    mock_choice = MagicMock()
    mock_choice.message.content = "output"

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        _, token_usage = await backend.call("prompt", example)
        assert token_usage.cached_tokens == 0


async def test_backend_call_minimal_kwargs():
    """call() with no optional profile fields passes only model and messages."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.models import Example

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    backend = LiteLLMBackend(profile)
    example = Example(id="ex-1", input={"q": "test"}, expected={"a": "answer"})

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.cache_read_input_tokens = 0

    mock_choice = MagicMock()
    mock_choice.message.content = "output"

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_call:
        await backend.call("prompt", example)

        call_kwargs = mock_call.call_args.kwargs
        assert "api_key" not in call_kwargs
        assert "base_url" not in call_kwargs
        assert "max_tokens" not in call_kwargs
        assert "temperature" not in call_kwargs
```

async def test_backend_extra_params_overrides_provider_params():
    """extra_params overrides provider_params on key conflict."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.models import Example

    profile = BackendProfile(
        model="gpt-4o",
        requests_per_minute=100,
        tokens_per_minute=50000,
        provider_params={"organization": "org-from-provider"},
        extra_params={"organization": "org-from-extra"},
    )
    backend = LiteLLMBackend(profile)
    example = Example(id="ex-1", input={"q": "test"}, expected={"a": "answer"})

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.cache_read_input_tokens = 0

    mock_choice = MagicMock()
    mock_choice.message.content = "output"

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_call:
        await backend.call("prompt", example)
        assert mock_call.call_args.kwargs["organization"] == "org-from-extra"
```

- [ ] **Step 15: Run tests to verify new tests fail**

Run: `uv run pytest tests/test_backends.py -k "backend" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.eval.backends.litellm_backend'`

### Task 6: LiteLLMBackend — Implementation

**Files:**
- Create: `odysseus/eval/backends/litellm_backend.py`

- [ ] **Step 16: Implement LiteLLMBackend**

```python
"""LiteLLM backend — unified client for all LLM providers."""

from __future__ import annotations

import os
from typing import Any

import litellm
from pydantic import SecretStr

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage


class LiteLLMBackend:
    """Backend implementation using LiteLLM's acompletion() for all providers.

    Satisfies the Backend protocol defined in odysseus.eval.protocols.
    """

    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        self._api_key: SecretStr | None = None
        if profile.api_key_env:
            self._api_key = SecretStr(os.environ[profile.api_key_env])

    @property
    def model_name(self) -> str:
        """Model name for pricing lookup (uses effective_pricing_model)."""
        return self._profile.effective_pricing_model

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        """Call the LLM and return normalised output + token usage."""
        kwargs: dict[str, Any] = {}

        if self._api_key:
            kwargs["api_key"] = self._api_key.get_secret_value()
        if self._profile.api_base:
            kwargs["base_url"] = self._profile.api_base
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature

        kwargs.update(self._profile.provider_params)
        kwargs.update(self._profile.extra_params)

        response = await litellm.acompletion(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        token_usage = TokenUsage(
            input_tokens=usage.prompt_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            output_tokens=usage.completion_tokens,
        )
        output = {"content": response.choices[0].message.content}
        return output, token_usage
```

- [ ] **Step 17: Run all backend tests**

Run: `uv run pytest tests/test_backends.py -v`
Expected: All tests PASS

- [ ] **Step 18: Lint and format**

Run: `uv run ruff check odysseus/eval/backends/ tests/test_backends.py && uv run ruff format odysseus/eval/backends/ tests/test_backends.py`

- [ ] **Step 19: Commit**

```bash
git add odysseus/eval/backends/litellm_backend.py tests/test_backends.py
git commit -m "feat(eval): add LiteLLMBackend with SecretStr auth and token normalisation"
```

---

## Chunk 4: Update __init__.py Re-exports + Registry create_backend Test

### Task 7: Update Package Re-exports

**Files:**
- Modify: `odysseus/eval/backends/__init__.py`

- [ ] **Step 20: Update __init__.py with re-exports**

```python
"""Backend registry and client abstraction."""

from odysseus.eval.backends.litellm_backend import LiteLLMBackend
from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.backends.registry import BackendRegistry

__all__ = [
    "BackendProfile",
    "BackendRegistry",
    "LiteLLMBackend",
]
```

- [ ] **Step 21: Add create_backend test to test_backends.py**

Append to `tests/test_backends.py`:

```python
def test_registry_create_backend():
    """create_backend returns a LiteLLMBackend from a named profile."""
    from odysseus.eval.backends.litellm_backend import LiteLLMBackend
    from odysseus.eval.backends.profile import BackendProfile
    from odysseus.eval.backends.registry import BackendRegistry

    profile = BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=50000)
    registry = BackendRegistry(profiles={"test": profile})
    backend = registry.create_backend("test")
    assert isinstance(backend, LiteLLMBackend)
    assert backend.model_name == "gpt-4o"
```

- [ ] **Step 22: Run all backend tests**

Run: `uv run pytest tests/test_backends.py -v`
Expected: All tests PASS

- [ ] **Step 23: Lint, format, and commit**

```bash
uv run ruff check odysseus/eval/backends/ tests/test_backends.py && uv run ruff format odysseus/eval/backends/ tests/test_backends.py
git add odysseus/eval/backends/__init__.py tests/test_backends.py
git commit -m "feat(eval): add backends package re-exports and create_backend test"
```

---

## Chunk 5: Integration Changes (ConcurrencyConfig, RunDependencies, Controller)

### Task 8: Update ConcurrencyConfig — Tests First

**Files:**
- Modify: `tests/test_models.py`
- Modify: `odysseus/eval/models.py`

- [ ] **Step 24: Update ConcurrencyConfig tests in test_models.py**

Replace `test_concurrency_config_defaults` (line 31-35):
```python
def test_concurrency_config_defaults():
    cc = ConcurrencyConfig()
    assert cc.max_concurrent_requests == 20
```

Remove these tests entirely:
- `test_concurrency_rpm_negative_rejected` (lines 120-122)
- `test_concurrency_tpm_zero_rejected` (lines 125-127)
- `test_concurrency_minimum_valid_accepted` (lines 130-134)

Note: `test_concurrency_max_concurrent_zero_rejected` (lines 115-117) stays — it still applies.

Add this new test verifying old fields are rejected:
```python
def test_concurrency_old_rate_limit_fields_rejected():
    """requests_per_minute and tokens_per_minute are no longer accepted."""
    with pytest.raises(ValidationError):
        ConcurrencyConfig(requests_per_minute=500)
    with pytest.raises(ValidationError):
        ConcurrencyConfig(tokens_per_minute=100000)
```

- [ ] **Step 25: Run test_models.py to see expected failures**

Run: `uv run pytest tests/test_models.py -v`
Expected: Some tests fail because ConcurrencyConfig still has the old fields

- [ ] **Step 26: Update ConcurrencyConfig in models.py**

In `odysseus/eval/models.py`, replace `ConcurrencyConfig` (lines 32-50) with:

```python
from pydantic import ConfigDict

class ConcurrencyConfig(BaseModel):
    """Concurrency settings.

    Fields:
        max_concurrent_requests: Max parallel requests (>= 1). Default: 20.
    """

    model_config = ConfigDict(extra="forbid")

    max_concurrent_requests: int = 20

    @field_validator("max_concurrent_requests")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v
```

Note: `ConfigDict(extra="forbid")` ensures old fields (`requests_per_minute`, `tokens_per_minute`) raise `ValidationError` instead of being silently ignored. Add `ConfigDict` to the imports from `pydantic` at the top of `models.py`.

- [ ] **Step 27: Update example-run.yaml**

In `configs/example-run.yaml`, remove the `requests_per_minute` and `tokens_per_minute` lines from the `concurrency` section (lines 27-28). Keep only:

```yaml
concurrency:
  max_concurrent_requests: 20   # >= 1
```

- [ ] **Step 28: Run test_models.py**

Run: `uv run pytest tests/test_models.py -v`
Expected: All PASS

### Task 9: Update RunDependencies

**Files:**
- Modify: `odysseus/eval/protocols.py`

- [ ] **Step 29: Add rate limit fields and __post_init__ to RunDependencies**

In `odysseus/eval/protocols.py`, replace `RunDependencies` (lines 64-73) with:

```python
@dataclasses.dataclass
class RunDependencies:
    """Container for all injected dependencies required by the run controller."""

    backend: Backend
    prompt_manager: PromptManager
    dataset_manager: DatasetManager
    metrics_engine: MetricsEngine
    results_collector: ResultsCollector
    requests_per_minute: int
    tokens_per_minute: int

    def __post_init__(self) -> None:
        if self.requests_per_minute < 1:
            raise ValueError("requests_per_minute must be >= 1")
        if self.tokens_per_minute < 1:
            raise ValueError("tokens_per_minute must be >= 1")
```

- [ ] **Step 29b: Add RunDependencies validation tests to test_backends.py**

Append to `tests/test_backends.py`:

```python
# --- RunDependencies validation tests ---


def test_run_dependencies_valid():
    """RunDependencies accepts valid rate limit values."""
    from odysseus.eval.protocols import RunDependencies

    # Use mock objects for protocol fields
    deps = RunDependencies(
        backend=MockBackend(),
        prompt_manager=MockPromptManager(),
        dataset_manager=MockDatasetManager(),
        metrics_engine=MockMetricsEngine(),
        results_collector=MockResultsCollector(),
        requests_per_minute=100,
        tokens_per_minute=50000,
    )
    assert deps.requests_per_minute == 100
    assert deps.tokens_per_minute == 50000


def test_run_dependencies_rpm_zero_rejected():
    """RunDependencies rejects requests_per_minute < 1."""
    from odysseus.eval.protocols import RunDependencies

    with pytest.raises(ValueError, match="requests_per_minute must be >= 1"):
        RunDependencies(
            backend=MockBackend(),
            prompt_manager=MockPromptManager(),
            dataset_manager=MockDatasetManager(),
            metrics_engine=MockMetricsEngine(),
            results_collector=MockResultsCollector(),
            requests_per_minute=0,
            tokens_per_minute=50000,
        )


def test_run_dependencies_tpm_negative_rejected():
    """RunDependencies rejects tokens_per_minute < 1."""
    from odysseus.eval.protocols import RunDependencies

    with pytest.raises(ValueError, match="tokens_per_minute must be >= 1"):
        RunDependencies(
            backend=MockBackend(),
            prompt_manager=MockPromptManager(),
            dataset_manager=MockDatasetManager(),
            metrics_engine=MockMetricsEngine(),
            results_collector=MockResultsCollector(),
            requests_per_minute=100,
            tokens_per_minute=-1,
        )
```

Note: This requires adding simple mock classes at the top of `tests/test_backends.py` (or importing them from `tests/test_controller.py`). Add these minimal mocks near the top of the file:

```python
from typing import Literal

from odysseus.eval.models import EvalResult, Example, MetricConfig, RunReport, TokenUsage


class MockBackend:
    @property
    def model_name(self) -> str:
        return "test-model"

    async def call(self, prompt: str, example: Example) -> tuple[dict, TokenUsage]:
        return {"answer": "mock"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)


class MockPromptManager:
    def load(self, version: str) -> str:
        return "mock prompt"


class MockDatasetManager:
    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]:
        return []


class MockMetricsEngine:
    def compute(self, results: list[EvalResult], examples: list[Example], metric_configs: list[MetricConfig]) -> dict[str, float]:
        return {}


class MockResultsCollector:
    def write_results(self, results: list[EvalResult], path: str) -> None:
        pass

    def write_report(self, report: RunReport, path: str) -> None:
        pass
```

### Task 10: Update Controller

**Files:**
- Modify: `odysseus/eval/controller.py`

- [ ] **Step 30: Update rate limiter construction in controller.py**

In `odysseus/eval/controller.py`, replace lines 54-57:

```python
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=config.concurrency.requests_per_minute,
        tokens_per_minute=config.concurrency.tokens_per_minute,
    )
```

With:

```python
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=deps.requests_per_minute,
        tokens_per_minute=deps.tokens_per_minute,
    )
```

### Task 11: Update Controller Tests

**Files:**
- Modify: `tests/test_controller.py`

- [ ] **Step 31: Update _make_deps helper**

In `tests/test_controller.py`, replace `_make_deps` (lines 136-149) with:

```python
def _make_deps(
    backend: Any = None,
    examples: list[Example] | None = None,
    metrics: dict[str, float] | None = None,
    requests_per_minute: int = 10000,
    tokens_per_minute: int = 1_000_000,
) -> tuple[RunDependencies, MockResultsCollector]:
    collector = MockResultsCollector()
    deps = RunDependencies(
        backend=backend or MockBackend(),
        prompt_manager=MockPromptManager(),
        dataset_manager=MockDatasetManager(examples or _make_examples(5)),
        metrics_engine=MockMetricsEngine(metrics),
        results_collector=collector,
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute,
    )
    return deps, collector
```

- [ ] **Step 32: Update test_concurrency_limit**

In `tests/test_controller.py`, replace the `test_concurrency_limit` function (lines 198-230) with:

```python
async def test_concurrency_limit():
    """Semaphore limits max concurrent backend calls."""
    backend = MockBackend()

    async def slow_call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        async with self._lock:
            self._concurrent += 1
            self._max_concurrent = max(self._max_concurrent, self._concurrent)
        await asyncio.sleep(0.05)
        async with self._lock:
            self._concurrent -= 1
        self._attempt_counts.setdefault(example.id, 0)
        self._attempt_counts[example.id] += 1
        return {"answer": "ok"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)

    import types

    backend.call = types.MethodType(slow_call, backend)

    from odysseus.eval.models import ConcurrencyConfig

    config = _make_config(
        concurrency=ConcurrencyConfig(max_concurrent_requests=2),
    )
    deps, _ = _make_deps(backend=backend, examples=_make_examples(6))
    await run(config, deps)

    assert backend._max_concurrent <= 2
```

- [ ] **Step 33: Run all controller tests**

Run: `uv run pytest tests/test_controller.py -v`
Expected: All PASS

- [ ] **Step 34: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 35: Lint and format all changed files**

Run: `uv run ruff check odysseus/eval/ tests/ configs/ && uv run ruff format odysseus/eval/ tests/ configs/`

- [ ] **Step 36: Commit**

```bash
git add odysseus/eval/models.py odysseus/eval/protocols.py odysseus/eval/controller.py tests/test_controller.py tests/test_models.py configs/example-run.yaml
git commit -m "refactor(eval): move rate limits from ConcurrencyConfig to RunDependencies

BREAKING: ConcurrencyConfig no longer has requests_per_minute or tokens_per_minute.
These now live on BackendProfile and are bridged to the controller via RunDependencies."
```

---

## Chunk 6: Final Verification

### Task 12: Full Suite + Type Check

- [ ] **Step 37: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 38: Run type checker**

Run: `uv run pyright`
Expected: No errors (or only pre-existing ones unrelated to this change)

- [ ] **Step 39: Run linter**

Run: `uv run ruff check .`
Expected: No errors

- [ ] **Step 40: Verify Backend protocol satisfaction**

Run a quick Python check:
```bash
uv run python -c "
from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.backends.litellm_backend import LiteLLMBackend
from odysseus.eval.protocols import Backend
p = BackendProfile(model='gpt-4o', requests_per_minute=100, tokens_per_minute=50000)
b = LiteLLMBackend(p)
print(f'isinstance check: {isinstance(b, Backend)}')
assert isinstance(b, Backend), 'LiteLLMBackend does not satisfy Backend protocol'
print('OK')
"
```
Expected: `isinstance check: True` and `OK`
