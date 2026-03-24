# Backend Registry and Client Abstraction

The `odysseus.eval.backends` subpackage provides a three-class design for configuring and invoking LLM providers:

```
BackendProfile    —  validated YAML config for one provider/model
      ↓
BackendRegistry   —  loads profiles from disk, constructs backends by label
      ↓
AnthropicBackend  —  direct Anthropic SDK (anthropic.AsyncAnthropic)
OpenAIBackend     —  direct OpenAI SDK (openai.AsyncOpenAI)
BedrockBackend    —  Anthropic via AWS Bedrock (anthropic.AsyncAnthropicBedrock + boto3)
```

Rate limits (`requests_per_minute`, `tokens_per_minute`) live on the profile rather than on `RunConfig`. This means a single `backends/` directory can contain profiles for many providers, each with its own tier-specific limits, without touching the run configuration.

---

## BackendProfile

`odysseus/eval/backends/profile.py`

Pydantic `BaseModel` representing a validated backend configuration loaded from a YAML file.

### Field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `Literal["anthropic", "openai", "bedrock", "mock_echo"]` | `"anthropic"` | Selects which SDK backend to use. |
| `model` | `str` | required | Model identifier string (e.g. `"claude-sonnet-4-20250514"`, `"gpt-4o"`, `"anthropic.claude-3-sonnet-..."`) |
| `pricing` | `ModelPricing \| None` | `None` | Inline pricing config. When set, cost is computed from token usage. When `None`, `EvalResult.cost` is `None`. See `eval/pricing.py`. |
| `api_key_env` | `str \| None` | `None` | Environment variable name holding the API key (e.g. `"ANTHROPIC_API_KEY"`). Resolved eagerly at backend construction time. |
| `api_base` | `str \| None` | `None` | Custom endpoint URL. Passed as `base_url` to the SDK client constructor. |
| `requests_per_minute` | `int` | required | RPM cap. Must be >= 1. |
| `tokens_per_minute` | `int` | required | TPM cap. Must be >= 1. |
| `max_tokens` | `int \| None` | `None` | Maximum tokens to generate. Omitted from the SDK call when `None` (Anthropic/Bedrock default to 1024). |
| `temperature` | `float \| None` | `None` | Sampling temperature. Omitted from the SDK call when `None`. |
| `extra_params` | `dict[str, Any]` | `{}` | Additional keyword arguments splatted into the provider SDK's `create()` call. Use for model-specific options like `reasoning_effort`, `thinking`, etc. |
| `provider_params` | `dict[str, Any]` | `{}` | Provider-specific kwargs passed to client construction (e.g. `organization` for OpenAI, `region_name`/`profile_name` for Bedrock). Not splatted into the API call. |

### Validators

- `model`: stripped of whitespace; raises `ValueError` if the result is empty.
- `requests_per_minute`, `tokens_per_minute`: must be >= 1; raises `ValueError` otherwise.

### `from_yaml(path)` classmethod

```python
@classmethod
def from_yaml(cls, path: str | Path) -> BackendProfile
```

Reads the file, calls `yaml.safe_load()`, validates it is a YAML mapping, then passes the keys as kwargs to `BackendProfile(...)`. Raises:
- `yaml.YAMLError` — malformed YAML syntax
- `ValueError` — YAML root is not a mapping (e.g. a bare string or list)
- `pydantic.ValidationError` — missing required fields or invalid values

---

## Profile YAML format

### Anthropic direct API

```yaml
# backends/claude-sonnet.yaml
model: "claude-sonnet-4-20250514"
api_key_env: "ANTHROPIC_API_KEY"
requests_per_minute: 100
tokens_per_minute: 80000
max_tokens: 1024
temperature: 0.0
pricing:
  input_cost_per_million_tokens: 3.0
  cached_cost_per_million_tokens: 0.3
  output_cost_per_million_tokens: 15.0
```

- `api_key_env` names the environment variable; the value is resolved at backend construction time via `os.environ[api_key_env]`.
- `pricing` defines per-million-token costs inline; omit it entirely to skip cost tracking.

### OpenAI direct API

```yaml
# backends/gpt-4o.yaml
model: "gpt-4o"
api_key_env: "OPENAI_API_KEY"
requests_per_minute: 500
tokens_per_minute: 150000
max_tokens: 2048
temperature: 0.0
pricing:
  input_cost_per_million_tokens: 2.5
  cached_cost_per_million_tokens: 1.25
  output_cost_per_million_tokens: 10.0
```

### AWS Bedrock

```yaml
# backends/bedrock-claude.yaml
model: "anthropic.claude-3-sonnet-20240229-v1:0"
provider: bedrock
requests_per_minute: 200
tokens_per_minute: 100000
pricing:
  input_cost_per_million_tokens: 3.0
  cached_cost_per_million_tokens: 0.3
  output_cost_per_million_tokens: 15.0
provider_params:
  region_name: "us-east-1"
  profile_name: "my-sso-profile"
```

- `provider_params` (except `region_name`) are forwarded to `boto3.Session()`. `region_name` is passed as `aws_region` to `AsyncAnthropicBedrock`.
- No `api_key_env` needed when using an AWS SSO profile or instance role.

### Extended params (reasoning, structured output, etc.)

```yaml
# backends/claude-extended-thinking.yaml
model: "claude-sonnet-4-20250514"
api_key_env: "ANTHROPIC_API_KEY"
requests_per_minute: 50
tokens_per_minute: 40000
pricing:
  input_cost_per_million_tokens: 3.0
  cached_cost_per_million_tokens: 0.3
  output_cost_per_million_tokens: 15.0
extra_params:
  thinking:
    type: "enabled"
    budget_tokens: 8000
```

`extra_params` is the escape hatch for any kwarg that the provider SDK's `create()` call accepts but that `BackendProfile` does not have an explicit field for.

---

## BackendRegistry

`odysseus/eval/backends/registry.py`

Indexes `BackendProfile` objects by their label (filename stem) and constructs backend instances on demand.

### Construction

**From a directory (normal usage):**

```python
registry = BackendRegistry.from_directory(Path("backends"))
```

`from_directory(path)` globs `*.yaml` then `*.yml` (both sorted alphabetically). For a given stem, `.yaml` takes precedence over `.yml`. Each file is loaded via `BackendProfile.from_yaml()`. The caller must provide an absolute or resolvable path.

**Direct injection (testing):**

```python
registry = BackendRegistry(profiles={"my-backend": some_profile})
```

Passing `profiles` directly skips disk I/O entirely. Useful in unit tests where real YAML files are undesirable.

### Label convention

The label is the filename stem: `backends/claude-sonnet.yaml` → label `"claude-sonnet"`. This is the value that must appear in `RunConfig.backend`.

### Methods

**`get_profile(label) → BackendProfile`**

Returns the profile for `label`. Raises `KeyError` with a message listing all available labels if `label` is not found.

**`create_backend(label) → Backend`**

Calls `get_profile(label)` then constructs a fresh backend based on `profile.provider`. No caching — each call returns a new instance. Dispatches to `AnthropicBackend`, `OpenAIBackend`, `BedrockBackend`, or `MockEchoBackend` via lazy imports.

**`list_profiles() → list[str]`**

Returns all loaded labels in insertion order (which is alphabetical, since `from_directory` uses `sorted()`).

---

## Provider Backends

Three concrete implementations of the `Backend` protocol, each using a direct provider SDK. All share the same interface: `model_name` property, `pricing` property, and `async call(prompt, example)`.

If `profile.api_key_env` is set, the constructor reads `os.environ[profile.api_key_env]` eagerly — `KeyError` is raised before any API calls.

### AnthropicBackend

`odysseus/eval/backends/anthropic_backend.py`

Uses `anthropic.AsyncAnthropic`. `provider_params` forwarded to client constructor, `extra_params` splatted into `messages.create()`. Response content: `response.content[0].text`. Default `max_tokens=1024` when not set.

### OpenAIBackend

`odysseus/eval/backends/openai_backend.py`

Uses `openai.AsyncOpenAI`. `provider_params` forwarded to client constructor, `extra_params` splatted into `chat.completions.create()`. Response content: `response.choices[0].message.content`.

### BedrockBackend

`odysseus/eval/backends/bedrock_backend.py`

Uses `anthropic.AsyncAnthropicBedrock` with `boto3.Session`. `provider_params` (except `region_name`) forwarded to `boto3.Session()`, `region_name` passed as `aws_region` to `AsyncAnthropicBedrock`. Call interface identical to `AnthropicBackend`.

### TokenUsage normalisation

Each backend normalises provider-specific token usage fields to Odysseus's disjoint `TokenUsage` model:

| Provider | `input_tokens` | `cached_tokens` | `output_tokens` |
|----------|---------------|-----------------|-----------------|
| Anthropic / Bedrock | `usage.input_tokens` | `getattr(usage, "cache_read_input_tokens", 0)` | `usage.output_tokens` |
| OpenAI | `usage.prompt_tokens` | `prompt_tokens_details.cached_tokens` (fallback 0) | `usage.completion_tokens` |

The return value is `({"content": response_text}, token_usage)`.

---

## MCP layer wiring

The MCP server is responsible for constructing `RunDependencies`. The pattern is:

```python
from pathlib import Path
from odysseus.eval.backends import BackendRegistry
from odysseus.eval.protocols import RunDependencies
from odysseus.eval.metrics import create_default_engine
from odysseus.eval.dataset import JsonlDatasetManager
from odysseus.eval.collector import JsonResultsCollector
from odysseus.prompts.manager import FilePromptManager

backends_dir = Path(__file__).parent.parent / "backends"
registry = BackendRegistry.from_directory(backends_dir)

# config.backend is the label from RunConfig (e.g. "claude-sonnet")
profile = registry.get_profile(config.backend)
backend = registry.create_backend(config.backend)

deps = RunDependencies(
    backend=backend,
    prompt_manager=FilePromptManager("prompts"),
    dataset_manager=JsonlDatasetManager(),
    metrics_engine=create_default_engine(),
    results_collector=JsonResultsCollector(),
    requests_per_minute=profile.requests_per_minute,  # sourced from profile
    tokens_per_minute=profile.tokens_per_minute,       # sourced from profile
)

report = await run(config, deps)
```

The controller never sees `BackendProfile` or `BackendRegistry` directly. Rate limits flow through `RunDependencies` as plain `int` fields.

---

## Error reference

| Condition | Error type | Where raised | Message / notes |
|-----------|-----------|--------------|-----------------|
| `api_key_env` is set but env var missing | `KeyError` | Backend constructor | Standard `os.environ` `KeyError`. Fails before any API calls. |
| Unknown profile label | `KeyError` | `BackendRegistry.get_profile()` | `"Unknown backend profile: '{label}'. Available: [...]"` |
| Malformed YAML syntax | `yaml.YAMLError` | `BackendProfile.from_yaml()` | Raised by `yaml.safe_load()` |
| YAML root is not a mapping | `ValueError` | `BackendProfile.from_yaml()` | `"Expected a YAML mapping in {path}, got {type}"` |
| Missing required field or invalid value | `pydantic.ValidationError` | `BackendProfile.from_yaml()` | Field-level messages from Pydantic |
| Profile file not found | `FileNotFoundError` | `BackendProfile.from_yaml()` | Propagated from `open()` |
| Empty `backends/` directory | — | `BackendRegistry.from_directory()` | No error at load time. `get_profile()` raises `KeyError` on any subsequent lookup. |
| `extra_params` / `provider_params` key collision | — | — | `provider_params` go to client construction, `extra_params` go to the API call. No collision possible. |
