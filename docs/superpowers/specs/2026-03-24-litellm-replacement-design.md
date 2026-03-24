# Replace LiteLLM with Direct Provider SDKs

**Date**: 2026-03-24
**Status**: Approved
**Motivation**: LiteLLM supply-chain compromise — remove the dependency and replace with direct SDK calls to Anthropic, OpenAI, and AWS Bedrock.

## Decision

Replace the single `LiteLLMBackend` class with three provider-specific backend classes, each using the provider's own SDK. The `BackendProfile.type` field becomes `provider` to explicitly select the SDK.

## BackendProfile Changes

| Field | Before | After |
|---|---|---|
| `type` | `Literal["litellm", "mock_echo"]`, default `"litellm"` | Renamed to `provider`: `Literal["anthropic", "openai", "bedrock", "mock_echo"]`, default `"anthropic"` |

All other fields (`model`, `api_key_env`, `api_base`, `pricing`, `requests_per_minute`, `tokens_per_minute`, `max_tokens`, `temperature`, `extra_params`, `provider_params`) remain unchanged.

## Provider Backend Classes

Three new files in `odysseus/eval/backends/`, each implementing the `Backend` protocol.

**Common behavior**: The `prompt` string is sent as a single user message (`{"role": "user", "content": prompt}`) for all providers. No system message is used — the eval engine's prompt already contains all instructions inline. `provider_params` are passed to **client construction**, `extra_params` are splatted into the **SDK call**. Exceptions propagate unchanged to the caller (no wrapping or translation).

### `anthropic_backend.py`

- Client: `anthropic.AsyncAnthropic(api_key=..., base_url=..., **provider_params)`
- Call: `client.messages.create(model=..., max_tokens=..., messages=[{"role": "user", "content": prompt}], **extra_params)`
- Response content: `response.content[0].text`
- Token mapping: `response.usage.input_tokens`, `getattr(response.usage, "cache_read_input_tokens", 0)`, `response.usage.output_tokens`

### `openai_backend.py`

- Client: `openai.AsyncOpenAI(api_key=..., base_url=..., **provider_params)`
- Call: `client.chat.completions.create(model=..., messages=[{"role": "user", "content": prompt}], **extra_params)`
- Response content: `response.choices[0].message.content`
- Token mapping: `usage.prompt_tokens` → `input_tokens`, `getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0` → `cached_tokens`, `usage.completion_tokens` → `output_tokens`

### `bedrock_backend.py`

- Client: `anthropic.AsyncAnthropicBedrock(aws_session=boto3.Session(), aws_region=...)` — uses the Anthropic SDK's native Bedrock support. Session and client created once in `__init__`.
- Authentication: `boto3.Session(**provider_params)` with standard AWS credential chain
- Region: from `provider_params.get("region_name")` or boto3 default
- Call, response content extraction, and token mapping: same as `anthropic_backend.py`
- `extra_params` splatted into `messages.create()` call

### Deleted

- `litellm_backend.py` — removed entirely

## Registry Changes

`BackendRegistry.create_backend()` return type changes from `LiteLLMBackend` to `Backend` (the protocol type). Dispatch on `profile.provider`:

| `provider` value | Class | Import |
|---|---|---|
| `"anthropic"` | `AnthropicBackend` | Lazy |
| `"openai"` | `OpenAIBackend` | Lazy |
| `"bedrock"` | `BedrockBackend` | Lazy |
| `"mock_echo"` | `MockEchoBackend` | Lazy |

All imports are lazy (inside dispatch branches) to avoid importing unused SDKs.

## Dependency Changes

| Action | Package |
|---|---|
| Remove | `litellm>=1.50.0` |
| Add | `boto3>=1.34.0` |
| Keep | `anthropic>=0.40.0` (includes `AsyncAnthropicBedrock`), `openai>=1.40.0` (includes `prompt_tokens_details`) |

## Test Changes

- `TestLiteLLMBackend` → split into `TestAnthropicBackend`, `TestOpenAIBackend`, `TestBedrockBackend`
- Each test class mocks its respective SDK client
- Profile/registry tests: `type` → `provider`, default assertion `"litellm"` → `"anthropic"`
- `test_profile_type_defaults_to_litellm` → `test_profile_provider_defaults_to_anthropic`
- Registry `create_backend` tests updated to check each provider type

## Doc Updates

Update these files to replace LiteLLM references:

- `odysseus/eval/docs/backends.md`
- `odysseus/eval/docs/architecture.md`
- `odysseus/eval/docs/README.md`

THP tickets (`THP-113.md`, `THP-114.md`, `THP-129.md`) are historical — no changes needed.

## Files Changed

| File | Action |
|---|---|
| `odysseus/eval/backends/litellm_backend.py` | Delete |
| `odysseus/eval/backends/anthropic_backend.py` | Create |
| `odysseus/eval/backends/openai_backend.py` | Create |
| `odysseus/eval/backends/bedrock_backend.py` | Create |
| `odysseus/eval/backends/profile.py` | Edit (`type` → `provider`) |
| `odysseus/eval/backends/registry.py` | Edit (dispatch logic) |
| `odysseus/eval/backends/__init__.py` | Edit (exports) |
| `tests/test_backends.py` | Edit (rewrite backend tests) |
| `pyproject.toml` | Edit (swap deps) |
| `odysseus/eval/docs/backends.md` | Edit |
| `odysseus/eval/docs/architecture.md` | Edit |
| `odysseus/eval/docs/README.md` | Edit |
