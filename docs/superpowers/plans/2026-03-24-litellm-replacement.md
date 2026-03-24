# Replace LiteLLM with Direct Provider SDKs — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the compromised LiteLLM dependency and replace it with three provider-specific backends (Anthropic, OpenAI, Bedrock) using direct SDKs.

**Architecture:** Replace the single `LiteLLMBackend` with `AnthropicBackend`, `OpenAIBackend`, and `BedrockBackend`, each in its own file. The `BackendProfile.type` field is renamed to `provider`. The `BackendRegistry` dispatches on `profile.provider` with lazy imports.

**Tech Stack:** `anthropic` SDK (direct + Bedrock via `AsyncAnthropicBedrock`), `openai` SDK, `boto3` for AWS session management.

**Spec:** `docs/superpowers/specs/2026-03-24-litellm-replacement-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `odysseus/eval/backends/profile.py` | Modify | Rename `type` → `provider`, update Literal values |
| `odysseus/eval/backends/anthropic_backend.py` | Create | Anthropic direct API backend |
| `odysseus/eval/backends/openai_backend.py` | Create | OpenAI API backend |
| `odysseus/eval/backends/bedrock_backend.py` | Create | AWS Bedrock backend (via Anthropic SDK) |
| `odysseus/eval/backends/registry.py` | Modify | Dispatch on `provider`, return `Backend` protocol type |
| `odysseus/eval/backends/__init__.py` | Modify | Update exports |
| `odysseus/eval/backends/litellm_backend.py` | Delete | Remove LiteLLM dependency |
| `pyproject.toml` | Modify | Remove litellm, add boto3, tighten openai version |
| `tests/test_backends.py` | Modify | Rewrite backend tests for new providers |
| `tests/fixtures/integration/backends/mock-echo.yaml` | Modify | `type` → `provider` |
| `odysseus/eval/docs/backends.md` | Modify | Replace LiteLLM references |
| `odysseus/eval/docs/architecture.md` | Modify | Update protocol table |
| `odysseus/eval/docs/README.md` | Modify | Update module inventory |

---

## Chunk 1: Core Infrastructure

### Task 1: Update BackendProfile — rename `type` to `provider`

**Files:**
- Modify: `odysseus/eval/backends/profile.py:18`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for the new `provider` field**

Add these tests to `tests/test_backends.py`, replacing the existing `test_profile_type_defaults_to_litellm` and `test_profile_type_mock_echo`:

```python
def test_profile_provider_defaults_to_anthropic(tmp_path: Path):
    """BackendProfile.provider defaults to 'anthropic'."""
    profile_path = tmp_path / "default.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "claude-sonnet-4-20250514",
                "requests_per_minute": 100,
                "tokens_per_minute": 100000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.provider == "anthropic"


def test_profile_provider_mock_echo(tmp_path: Path):
    """BackendProfile.provider can be set to 'mock_echo'."""
    profile_path = tmp_path / "mock.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "provider": "mock_echo",
                "requests_per_minute": 10000,
                "tokens_per_minute": 1000000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.provider == "mock_echo"


def test_profile_provider_openai():
    """BackendProfile.provider can be set to 'openai'."""
    profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
    assert profile.provider == "openai"


def test_profile_provider_bedrock():
    """BackendProfile.provider can be set to 'bedrock'."""
    profile = BackendProfile(model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000)
    assert profile.provider == "bedrock"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::test_profile_provider_defaults_to_anthropic tests/test_backends.py::test_profile_provider_mock_echo tests/test_backends.py::test_profile_provider_openai tests/test_backends.py::test_profile_provider_bedrock -v`
Expected: FAIL — `BackendProfile` has no field `provider`

- [ ] **Step 3: Update BackendProfile and remove old tests**

In `odysseus/eval/backends/profile.py`, change line 18:

```python
# Before:
    type: Literal["litellm", "mock_echo"] = "litellm"

# After:
    provider: Literal["anthropic", "openai", "bedrock", "mock_echo"] = "anthropic"
```

Also delete `test_profile_type_defaults_to_litellm` and `test_profile_type_mock_echo` from `tests/test_backends.py` (they reference the old `type` field).

- [ ] **Step 4: Update the mock-echo fixture**

In `tests/fixtures/integration/backends/mock-echo.yaml`, change `type: mock_echo` to `provider: mock_echo`:

```yaml
model: mock-echo
provider: mock_echo
requests_per_minute: 10000
tokens_per_minute: 1000000
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::test_profile_provider_defaults_to_anthropic tests/test_backends.py::test_profile_provider_mock_echo tests/test_backends.py::test_profile_provider_openai tests/test_backends.py::test_profile_provider_bedrock -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/backends/profile.py tests/test_backends.py tests/fixtures/integration/backends/mock-echo.yaml
git commit -m "refactor: rename BackendProfile.type to provider with new Literal values"
```

---

### Task 2: Create AnthropicBackend

**Files:**
- Create: `odysseus/eval/backends/anthropic_backend.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for AnthropicBackend**

Add to `tests/test_backends.py`. First add the import at the top:

```python
from odysseus.eval.backends.anthropic_backend import AnthropicBackend
```

Then add the EXAMPLE constant (already exists in the file) and the test class:

```python
def _make_anthropic_mock_response(
    text: str = "response text",
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_read_input_tokens: int | None = 5,
) -> MagicMock:
    """Build a mock Anthropic response object."""
    content_block = MagicMock()
    content_block.text = text

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    if cache_read_input_tokens is not None:
        usage.cache_read_input_tokens = cache_read_input_tokens
    else:
        # Simulate usage object lacking cache_read_input_tokens
        del usage.cache_read_input_tokens

    resp = MagicMock()
    resp.content = [content_block]
    resp.usage = usage
    return resp


class TestAnthropicBackend:
    def test_backend_model_name(self) -> None:
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000)
        backend = AnthropicBackend(profile)
        assert backend.model_name == "claude-sonnet-4-20250514"

    def test_backend_pricing_none_by_default(self) -> None:
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000)
        backend = AnthropicBackend(profile)
        assert backend.pricing is None

    def test_backend_pricing_from_profile(self) -> None:
        pricing = ModelPricing(
            input_cost_per_million_tokens=3.0,
            cached_cost_per_million_tokens=0.3,
            output_cost_per_million_tokens=15.0,
        )
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000, pricing=pricing)
        backend = AnthropicBackend(profile)
        assert backend.pricing is pricing

    def test_backend_missing_env_var_raises(self) -> None:
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000, api_key_env="NONEXISTENT_KEY_12345")
        with pytest.raises(KeyError):
            AnthropicBackend(profile)

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_token_normalisation(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response(
            input_tokens=100, output_tokens=50, cache_read_input_tokens=30,
        ))
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000, max_tokens=1024)
        backend = AnthropicBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_no_cache_tokens(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response(
            input_tokens=100, output_tokens=50, cache_read_input_tokens=None,
        ))
        profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000, max_tokens=1024)
        backend = AnthropicBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cached_tokens == 0

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_passes_extra_params(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            temperature=0.5,
            extra_params={"top_p": 0.9},
        )
        backend = AnthropicBackend(profile)
        await backend.call("test prompt", EXAMPLE)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["top_p"] == 0.9

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_provider_params_passed_to_client(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"default_headers": {"X-Custom": "value"}},
        )
        backend = AnthropicBackend(profile)

        MockClient.assert_called_once()
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["default_headers"] == {"X-Custom": "value"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestAnthropicBackend -v`
Expected: FAIL — `anthropic_backend` module does not exist

- [ ] **Step 3: Write the implementation**

Create `odysseus/eval/backends/anthropic_backend.py`:

```python
"""Anthropic backend — direct SDK client for Anthropic API."""

from __future__ import annotations

import os
from typing import Any

import anthropic

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class AnthropicBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        api_key: str | None = None
        if profile.api_key_env:
            api_key = os.environ[profile.api_key_env]

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if profile.api_base:
            client_kwargs["base_url"] = profile.api_base
        client_kwargs.update(profile.provider_params)

        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._profile.model

    @property
    def pricing(self) -> ModelPricing | None:
        return self._profile.pricing

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        kwargs: dict[str, Any] = {}
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        else:
            kwargs["max_tokens"] = 1024
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        kwargs.update(self._profile.extra_params)

        response = await self._client.messages.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        token_usage = TokenUsage(
            input_tokens=usage.input_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            output_tokens=usage.output_tokens,
        )
        output = {"content": response.content[0].text}
        return output, token_usage
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestAnthropicBackend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/anthropic_backend.py tests/test_backends.py
git commit -m "feat: add AnthropicBackend using direct Anthropic SDK"
```

---

### Task 3: Create OpenAIBackend

**Files:**
- Create: `odysseus/eval/backends/openai_backend.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for OpenAIBackend**

Add import:

```python
from odysseus.eval.backends.openai_backend import OpenAIBackend
```

Add mock response helper and test class:

```python
def _make_openai_mock_response(
    content: str = "response text",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    cached_tokens: int | None = 5,
) -> MagicMock:
    """Build a mock OpenAI response object."""
    choice = MagicMock()
    choice.message.content = content

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    if cached_tokens is not None:
        details = MagicMock()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
    else:
        usage.prompt_tokens_details = None

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


class TestOpenAIBackend:
    def test_backend_model_name(self) -> None:
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        assert backend.model_name == "gpt-4o"

    def test_backend_pricing_none_by_default(self) -> None:
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        assert backend.pricing is None

    def test_backend_missing_env_var_raises(self) -> None:
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000, api_key_env="NONEXISTENT_KEY_12345")
        with pytest.raises(KeyError):
            OpenAIBackend(profile)

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_token_normalisation(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response(
            prompt_tokens=100, completion_tokens=50, cached_tokens=30,
        ))
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_no_cached_tokens(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response(
            prompt_tokens=100, completion_tokens=50, cached_tokens=None,
        ))
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cached_tokens == 0

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_passes_extra_params(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response())
        profile = BackendProfile(
            model="gpt-4o",
            provider="openai",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=2048,
            temperature=0.5,
            extra_params={"top_p": 0.9},
        )
        backend = OpenAIBackend(profile)
        await backend.call("test prompt", EXAMPLE)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"
        assert call_kwargs.kwargs["max_tokens"] == 2048
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["top_p"] == 0.9

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_provider_params_passed_to_client(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response())
        profile = BackendProfile(
            model="gpt-4o",
            provider="openai",
            requests_per_minute=100,
            tokens_per_minute=50000,
            provider_params={"organization": "org-123"},
        )
        backend = OpenAIBackend(profile)

        MockClient.assert_called_once()
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["organization"] == "org-123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestOpenAIBackend -v`
Expected: FAIL — `openai_backend` module does not exist

- [ ] **Step 3: Write the implementation**

Create `odysseus/eval/backends/openai_backend.py`:

```python
"""OpenAI backend — direct SDK client for OpenAI API."""

from __future__ import annotations

import os
from typing import Any

import openai

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class OpenAIBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        api_key: str | None = None
        if profile.api_key_env:
            api_key = os.environ[profile.api_key_env]

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if profile.api_base:
            client_kwargs["base_url"] = profile.api_base
        client_kwargs.update(profile.provider_params)

        self._client = openai.AsyncOpenAI(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._profile.model

    @property
    def pricing(self) -> ModelPricing | None:
        return self._profile.pricing

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        kwargs: dict[str, Any] = {}
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        kwargs.update(self._profile.extra_params)

        response = await self._client.chat.completions.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        assert usage is not None, "OpenAI response missing usage data"
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0

        token_usage = TokenUsage(
            input_tokens=usage.prompt_tokens or 0,
            cached_tokens=cached,
            output_tokens=usage.completion_tokens or 0,
        )
        output = {"content": response.choices[0].message.content}
        return output, token_usage
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestOpenAIBackend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/openai_backend.py tests/test_backends.py
git commit -m "feat: add OpenAIBackend using direct OpenAI SDK"
```

---

### Task 4: Create BedrockBackend

**Files:**
- Create: `odysseus/eval/backends/bedrock_backend.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for BedrockBackend**

Add import:

```python
from odysseus.eval.backends.bedrock_backend import BedrockBackend
```

Add test class:

```python
class TestBedrockBackend:
    def test_backend_model_name(self) -> None:
        with patch("odysseus.eval.backends.bedrock_backend.boto3.Session"):
            with patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock"):
                profile = BackendProfile(model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000)
                backend = BedrockBackend(profile)
                assert backend.model_name == "anthropic.claude-3-sonnet"

    def test_backend_pricing_none_by_default(self) -> None:
        with patch("odysseus.eval.backends.bedrock_backend.boto3.Session"):
            with patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock"):
                profile = BackendProfile(model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000)
                backend = BedrockBackend(profile)
                assert backend.pricing is None

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_call_token_normalisation(self, MockSession: MagicMock, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response(
            input_tokens=100, output_tokens=50, cache_read_input_tokens=30,
        ))
        profile = BackendProfile(model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000, max_tokens=1024)
        backend = BedrockBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_region_from_provider_params(self, MockSession: MagicMock, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"region_name": "eu-west-1"},
        )
        backend = BedrockBackend(profile)

        MockClient.assert_called_once()
        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["aws_region"] == "eu-west-1"

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_provider_params_forwarded_to_session(self, MockSession: MagicMock, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"region_name": "eu-west-1", "profile_name": "my-sso-profile"},
        )
        backend = BedrockBackend(profile)

        MockSession.assert_called_once_with(profile_name="my-sso-profile")  # region_name excluded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestBedrockBackend -v`
Expected: FAIL — `bedrock_backend` module does not exist

- [ ] **Step 3: Write the implementation**

Create `odysseus/eval/backends/bedrock_backend.py`:

```python
"""Bedrock backend — Anthropic models via AWS Bedrock using the Anthropic SDK."""

from __future__ import annotations

from typing import Any

import anthropic
import boto3

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class BedrockBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        session_kwargs = {k: v for k, v in profile.provider_params.items() if k != "region_name"}
        region = profile.provider_params.get("region_name")

        session = boto3.Session(**session_kwargs)
        client_kwargs: dict[str, Any] = {"aws_session": session}
        if region:
            client_kwargs["aws_region"] = region

        self._client = anthropic.AsyncAnthropicBedrock(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._profile.model

    @property
    def pricing(self) -> ModelPricing | None:
        return self._profile.pricing

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        kwargs: dict[str, Any] = {}
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        else:
            kwargs["max_tokens"] = 1024
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        kwargs.update(self._profile.extra_params)

        response = await self._client.messages.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        token_usage = TokenUsage(
            input_tokens=usage.input_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            output_tokens=usage.output_tokens,
        )
        output = {"content": response.content[0].text}
        return output, token_usage
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestBedrockBackend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/bedrock_backend.py tests/test_backends.py
git commit -m "feat: add BedrockBackend using Anthropic SDK with boto3 session"
```

---

## Chunk 2: Wiring and Cleanup

### Task 5: Update BackendRegistry dispatch

**Files:**
- Modify: `odysseus/eval/backends/registry.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write failing tests for new registry dispatch**

Update the existing `test_registry_create_backend` and add new tests. Replace the `LiteLLMBackend` import with protocol-based checks:

```python
def test_registry_create_backend_anthropic() -> None:
    profile = BackendProfile(model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000)
    reg = BackendRegistry(profiles={"claude": profile})
    with patch("odysseus.eval.backends.registry.AnthropicBackend") as MockBackend:
        backend = reg.create_backend("claude")
        MockBackend.assert_called_once_with(profile)


def test_registry_create_backend_openai() -> None:
    profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
    reg = BackendRegistry(profiles={"gpt": profile})
    with patch("odysseus.eval.backends.registry.OpenAIBackend") as MockBackend:
        backend = reg.create_backend("gpt")
        MockBackend.assert_called_once_with(profile)


def test_registry_create_backend_bedrock() -> None:
    profile = BackendProfile(model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000)
    reg = BackendRegistry(profiles={"bedrock": profile})
    with patch("odysseus.eval.backends.registry.BedrockBackend") as MockBackend:
        backend = reg.create_backend("bedrock")
        MockBackend.assert_called_once_with(profile)


def test_registry_create_backend_mock_echo(tmp_path: Path) -> None:
    """Registry creates MockEchoBackend when profile provider is 'mock_echo'."""
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    (backends_dir / "mock.yaml").write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "provider": "mock_echo",
                "requests_per_minute": 10000,
                "tokens_per_minute": 1000000,
            }
        )
    )
    registry = BackendRegistry.from_directory(backends_dir)
    backend = registry.create_backend("mock")

    from odysseus.eval.backends.mock_echo import MockEchoBackend
    assert isinstance(backend, MockEchoBackend)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::test_registry_create_backend_anthropic tests/test_backends.py::test_registry_create_backend_openai tests/test_backends.py::test_registry_create_backend_bedrock -v`
Expected: FAIL — registry still uses LiteLLMBackend

- [ ] **Step 3: Update the registry**

Rewrite `odysseus/eval/backends/registry.py`:

```python
"""Backend registry — loads profiles from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from odysseus.eval.backends.profile import BackendProfile

if TYPE_CHECKING:
    from odysseus.eval.protocols import Backend


class BackendRegistry:
    def __init__(self, profiles: dict[str, BackendProfile] | None = None) -> None:
        self._profiles: dict[str, BackendProfile] = profiles or {}

    @classmethod
    def from_directory(cls, path: Path) -> BackendRegistry:
        profiles: dict[str, BackendProfile] = {}
        for file in sorted(path.glob("*.yaml")):
            profiles[file.stem] = BackendProfile.from_yaml(file)
        for file in sorted(path.glob("*.yml")):
            if file.stem not in profiles:
                profiles[file.stem] = BackendProfile.from_yaml(file)
        return cls(profiles)

    def get_profile(self, label: str) -> BackendProfile:
        if label not in self._profiles:
            raise KeyError(f"Unknown backend profile: '{label}'. Available: {list(self._profiles.keys())}")
        return self._profiles[label]

    def create_backend(self, label: str) -> Backend:
        profile = self.get_profile(label)
        if profile.provider == "mock_echo":
            from odysseus.eval.backends.mock_echo import MockEchoBackend

            return MockEchoBackend(profile)
        elif profile.provider == "openai":
            from odysseus.eval.backends.openai_backend import OpenAIBackend

            return OpenAIBackend(profile)
        elif profile.provider == "bedrock":
            from odysseus.eval.backends.bedrock_backend import BedrockBackend

            return BedrockBackend(profile)
        else:
            from odysseus.eval.backends.anthropic_backend import AnthropicBackend

            return AnthropicBackend(profile)

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::test_registry_create_backend_anthropic tests/test_backends.py::test_registry_create_backend_openai tests/test_backends.py::test_registry_create_backend_bedrock tests/test_backends.py::test_registry_create_backend_mock_echo -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/registry.py tests/test_backends.py
git commit -m "refactor: update BackendRegistry to dispatch on provider field"
```

---

### Task 6: Delete LiteLLMBackend, update exports and dependencies

**Files:**
- Delete: `odysseus/eval/backends/litellm_backend.py`
- Modify: `odysseus/eval/backends/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `__init__.py`**

Replace `odysseus/eval/backends/__init__.py`:

```python
"""Backend registry and client abstraction."""

from odysseus.eval.backends.anthropic_backend import AnthropicBackend
from odysseus.eval.backends.bedrock_backend import BedrockBackend
from odysseus.eval.backends.openai_backend import OpenAIBackend
from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.backends.registry import BackendRegistry

__all__ = [
    "AnthropicBackend",
    "BedrockBackend",
    "BackendProfile",
    "BackendRegistry",
    "OpenAIBackend",
]
```

- [ ] **Step 2: Delete `litellm_backend.py`**

```bash
rm odysseus/eval/backends/litellm_backend.py
```

- [ ] **Step 3: Update `pyproject.toml`**

Remove `litellm>=1.50.0`, add `boto3>=1.34.0`, tighten `openai>=1.40.0`:

```toml
dependencies = [
    "mcp[cli]>=1.0.0",
    "anthropic>=0.40.0",
    "openai>=1.40.0",
    "aiohttp>=3.9.0",
    "pyyaml>=6.0",
    "pydantic>=2.0.0",
    "boto3>=1.34.0",
    "watchfiles>=0.21.0",
]
```

- [ ] **Step 4: Remove old LiteLLM imports and tests from test file**

In `tests/test_backends.py`:
- Remove `from odysseus.eval.backends.litellm_backend import LiteLLMBackend`
- Remove `_make_mock_response()` helper
- Remove entire `TestLiteLLMBackend` class
- Remove `test_registry_create_backend` (the old one that checks `isinstance(backend, LiteLLMBackend)`)
- Remove `test_registry_creates_mock_echo_backend` (replaced by `test_registry_create_backend_mock_echo`)

- [ ] **Step 5: Run uv sync and full test suite**

```bash
uv sync
uv run pytest tests/test_backends.py -v
```

Expected: All tests pass, no litellm import errors

- [ ] **Step 6: Run lint and type check**

```bash
uv run ruff check .
uv run pyright
```

Expected: Clean (or only pre-existing issues)

- [ ] **Step 7: Commit**

```bash
git add odysseus/eval/backends/__init__.py pyproject.toml tests/test_backends.py uv.lock
git rm odysseus/eval/backends/litellm_backend.py
git commit -m "refactor: remove LiteLLM dependency, add boto3, update exports"
```

---

## Chunk 3: Documentation

### Task 7: Update documentation

**Files:**
- Modify: `odysseus/eval/docs/backends.md`
- Modify: `odysseus/eval/docs/architecture.md:111`
- Modify: `odysseus/eval/docs/README.md:17`

- [ ] **Step 1: Update `eval/docs/README.md`**

Change the backends row in the module inventory table (line 17):

```markdown
# Before:
| `eval/backends/` | `BackendProfile`, `BackendRegistry`, `LiteLLMBackend` | YAML-driven backend registry and LiteLLM client |

# After:
| `eval/backends/` | `BackendProfile`, `BackendRegistry`, `AnthropicBackend`, `OpenAIBackend`, `BedrockBackend` | YAML-driven backend registry with direct provider SDK clients |
```

- [ ] **Step 2: Update `eval/docs/architecture.md`**

Change the Backend row in the protocols table (line 111):

```markdown
# Before:
| `Backend` | `model_name: str` (property); `async call(prompt, example) → (dict, TokenUsage)` | `LiteLLMBackend` | `eval/backends/litellm_backend.py` |

# After:
| `Backend` | `model_name: str` (property); `async call(prompt, example) → (dict, TokenUsage)` | `AnthropicBackend`, `OpenAIBackend`, `BedrockBackend` | `eval/backends/anthropic_backend.py`, `eval/backends/openai_backend.py`, `eval/backends/bedrock_backend.py` |
```

- [ ] **Step 3: Update `eval/docs/backends.md`**

This file needs the most changes. Key edits:

1. Replace the top-level diagram (lines 5-12): change `LiteLLMBackend` to `AnthropicBackend / OpenAIBackend / BedrockBackend` and update the description line.

2. Update the BackendProfile field reference table (lines 26-37):
   - `model` description: change "LiteLLM model string" to "Model identifier string"
   - `api_key_env` description: change "Resolved eagerly at `LiteLLMBackend` construction" to "Resolved eagerly at backend construction"
   - `api_base` description: change "Passed as `base_url` to `litellm.acompletion()`" to "Passed as `base_url` to the SDK client constructor"
   - `max_tokens` / `temperature` descriptions: change "Omitted from the LiteLLM call when `None`" to "Omitted from the SDK call when `None`"
   - `extra_params` description: change "forwarded to `acompletion()`" to "forwarded to the SDK's create call"
   - `provider_params` description: change "Provider-specific kwargs (AWS credentials, Vertex project/location, etc.). Applied before `extra_params`" to "Provider-specific kwargs passed to client construction (e.g. `organization` for OpenAI, `region_name` for Bedrock). Not splatted into the API call."
   - Add `provider` field row: `provider | Literal["anthropic", "openai", "bedrock", "mock_echo"] | "anthropic" | Selects which SDK backend to use`

3. Update Bedrock YAML example (lines 97-113): change model string to plain `anthropic.claude-3-sonnet-20240229-v1:0` (no `bedrock/` prefix), add `provider: bedrock`, update `provider_params` to use `region_name` instead of `aws_region_name` and `aws_profile_name`.

4. Remove Vertex AI YAML example section (lines 115-127) — no longer supported.

5. Update `extra_params` description (line 146): change "litellm.acompletion()" to "the provider SDK's create call".

6. Update BackendRegistry section (lines 150-191): change all `LiteLLMBackend` references to `Backend` (protocol type). Update `create_backend` signature and description.

7. Replace the entire "LiteLLMBackend" section (lines 194-268) with three shorter sections for each provider backend, covering construction, call, and token mapping.

8. Update error reference table (lines 311-321): change `LiteLLMBackend.__init__` to "backend constructor", remove `LiteLLMBackend.call()` reference.

- [ ] **Step 4: Run lint on docs (check for broken references)**

```bash
uv run ruff check .
```

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/docs/backends.md odysseus/eval/docs/architecture.md odysseus/eval/docs/README.md
git commit -m "docs: update eval docs to reflect direct SDK backends replacing LiteLLM"
```

---

## Verification

After all tasks are complete:

- [ ] `uv run pytest` — all tests pass
- [ ] `uv run ruff check .` — no lint errors
- [ ] `uv run pyright` — no type errors
- [ ] `grep -r litellm odysseus/` — no remaining litellm references in source code
- [ ] `grep -r litellm tests/` — no remaining litellm references in tests
- [ ] `python -c "import litellm"` — should fail (not installed)
