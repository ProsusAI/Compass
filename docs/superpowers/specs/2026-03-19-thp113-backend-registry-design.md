# THP-113 Backend Registry and Client Abstraction Design Spec

**Goal:** Implement a file-based backend registry that loads provider-specific profiles from YAML files and constructs `LiteLLMBackend` instances satisfying the `Backend` protocol. Rate limits are backend-specific and live on the profile, not on `RunConfig`.

**Approach:** Pydantic-validated backend profiles (one YAML file per profile in a `backends/` directory), a `BackendRegistry` that loads and indexes them by filename stem, and a single `LiteLLMBackend` class that handles all providers via LiteLLM's unified `acompletion()` API.

---

## BackendProfile Model

`odysseus/eval/backends/profile.py`

```python
class BackendProfile(BaseModel):
    """Validated backend configuration loaded from YAML."""

    model: str                          # LiteLLM model string, e.g. "claude-sonnet-4-20250514"
    api_key_env: str | None = None      # Env var name, e.g. "ANTHROPIC_API_KEY"
    api_base: str | None = None         # Custom endpoint URL

    # Rate limits (required — provider-specific, no defaults)
    requests_per_minute: int            # RPM cap
    tokens_per_minute: int              # TPM cap

    # Generation parameters (optional)
    max_tokens: int | None = None
    temperature: float | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)  # reasoning_effort, thinking, etc.

    # Provider auth/config — Vertex, Bedrock, etc.
    provider_params: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> BackendProfile:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
```

### Validation rules

- `model` must be non-empty (stripped).
- `requests_per_minute` and `tokens_per_minute` must be >= 1. No defaults — must be explicitly set.
- `api_key_env`, if set, must correspond to an existing environment variable (validated at `LiteLLMBackend` construction time, not at profile load time).

### Example profiles

**OpenAI/Anthropic direct:**
```yaml
# backends/claude-sonnet.yaml
model: "claude-sonnet-4-20250514"
api_key_env: "ANTHROPIC_API_KEY"
requests_per_minute: 100
tokens_per_minute: 80000
max_tokens: 1024
temperature: 0.0
```

**AWS Bedrock:**
```yaml
# backends/bedrock-claude.yaml
model: "bedrock/anthropic.claude-3-sonnet-20240229-v1:0"
requests_per_minute: 200
tokens_per_minute: 100000
provider_params:
  aws_region_name: "us-east-1"
  aws_profile_name: "my-sso-profile"
```

**Vertex AI:**
```yaml
# backends/vertex-gemini.yaml
model: "vertex_ai/gemini-2.5-pro"
requests_per_minute: 200
tokens_per_minute: 100000
provider_params:
  vertex_project: "my-project"
  vertex_location: "us-central1"
  vertex_credentials_env: "GOOGLE_APPLICATION_CREDENTIALS"
```

---

## LiteLLMBackend Class

`odysseus/eval/backends/litellm_backend.py`

Single class satisfying the `Backend` protocol. Handles all providers — LiteLLM does the routing internally.

```python
class LiteLLMBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        self._api_key: SecretStr | None = None
        if profile.api_key_env:
            self._api_key = SecretStr(os.environ[profile.api_key_env])  # Fail fast

    @property
    def model_name(self) -> str:
        return self._profile.model

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
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

### Key decisions

- **API key resolved eagerly** in `__init__` via `SecretStr` — fails fast if the env var is missing, won't leak in `repr()` or logging.
- **`provider_params` and `extra_params` are splatted** into `acompletion()` — LiteLLM routes them to the correct provider handler.
- **Token normalisation** uses Anthropic-style disjoint fields: `input_tokens` (non-cached), `cached_tokens`, `output_tokens`. LiteLLM's `cache_read_input_tokens` is extracted via `getattr` with a 0 default for providers that don't support caching.

---

## BackendRegistry

`odysseus/eval/backends/registry.py`

```python
class BackendRegistry:
    DEFAULT_DIR = Path("backends")

    def __init__(self, profiles: dict[str, BackendProfile] | None = None) -> None:
        self._profiles: dict[str, BackendProfile] = profiles or {}

    @classmethod
    def from_directory(cls, path: Path | None = None) -> BackendRegistry:
        directory = path or cls.DEFAULT_DIR
        profiles: dict[str, BackendProfile] = {}
        for file in sorted(directory.glob("*.yaml")):
            profiles[file.stem] = BackendProfile.from_yaml(file)
        for file in sorted(directory.glob("*.yml")):
            if file.stem not in profiles:
                profiles[file.stem] = BackendProfile.from_yaml(file)
        return cls(profiles)

    def get_profile(self, label: str) -> BackendProfile:
        if label not in self._profiles:
            raise KeyError(f"Unknown backend profile: '{label}'. Available: {list(self._profiles.keys())}")
        return self._profiles[label]

    def create_backend(self, label: str) -> LiteLLMBackend:
        return LiteLLMBackend(self.get_profile(label))

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())
```

### Key decisions

- **Label = filename stem** — `backends/claude-sonnet.yaml` → `"claude-sonnet"`. Intuitive for an agent to create/modify.
- **`from_directory` is a classmethod** — tests can inject profiles directly via `__init__` without touching the filesystem.
- **No caching** — `create_backend` constructs a fresh `LiteLLMBackend` each time. The backend is stateless, so the agent can overwrite a YAML file and re-load without stale state.
- **`.yaml` takes precedence over `.yml`** for the same stem.

---

## Integration: RunConfig and Controller

### ConcurrencyConfig change

`requests_per_minute` and `tokens_per_minute` are removed from `ConcurrencyConfig`. It retains only orchestration-level config:

```python
class ConcurrencyConfig(BaseModel):
    max_concurrent_requests: int = 20

    @field_validator("max_concurrent_requests")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v
```

### Controller signature change

`run()` gains a `profile: BackendProfile` parameter. The rate limiter reads from the profile:

```python
async def run(config: RunConfig, deps: RunDependencies, profile: BackendProfile) -> RunReport:
    ...
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=profile.requests_per_minute,
        tokens_per_minute=profile.tokens_per_minute,
    )
    semaphore = asyncio.Semaphore(config.concurrency.max_concurrent_requests)
```

### MCP layer wiring

```python
registry = BackendRegistry.from_directory()
profile = registry.get_profile(config.backend)
backend = registry.create_backend(config.backend)
deps = RunDependencies(backend=backend, ...)
report = await run(config, deps, profile)
```

---

## Error Handling

- **Missing env var for `api_key_env`**: `KeyError` raised at `LiteLLMBackend.__init__` — fail fast before any API calls.
- **Unknown profile label**: `KeyError` with available labels listed.
- **Invalid YAML / missing required fields**: Pydantic `ValidationError` at profile load time with clear field-level messages.
- **LiteLLM API errors**: Propagate to the caller — the controller's existing retry logic in `_eval_with_retry()` handles these.
- **Empty backends directory**: `BackendRegistry` initialises with no profiles — `get_profile()` raises `KeyError` on any lookup.

---

## File Structure

| File | Action | Contents |
|---|---|---|
| `odysseus/eval/backends/__init__.py` | Create | Re-exports `BackendProfile`, `BackendRegistry`, `LiteLLMBackend` |
| `odysseus/eval/backends/profile.py` | Create | `BackendProfile` Pydantic model |
| `odysseus/eval/backends/litellm_backend.py` | Create | `LiteLLMBackend` class |
| `odysseus/eval/backends/registry.py` | Create | `BackendRegistry` class |
| `odysseus/eval/models.py` | Modify | Remove `requests_per_minute`, `tokens_per_minute` from `ConcurrencyConfig` |
| `odysseus/eval/controller.py` | Modify | `run()` takes `profile` param, rate limiter reads from profile |
| `tests/test_controller.py` | Modify | Pass profile to `run()` |
| `tests/test_backends.py` | Create | Full test coverage |

---

## Testing Strategy

All tests use synthetic data, no real API calls. `litellm.acompletion` is mocked.

**BackendProfile tests:**
- Valid YAML loads correctly
- Missing `requests_per_minute` or `tokens_per_minute` → `ValidationError`
- Missing `model` → `ValidationError`
- Optional fields default to `None` / empty dict
- `from_yaml` round-trips correctly

**BackendRegistry tests:**
- `from_directory` loads multiple profiles from YAML files
- Label equals filename stem
- `get_profile` raises `KeyError` for unknown label with helpful message
- `list_profiles` returns all available labels
- `.yaml` takes precedence over `.yml` for same stem
- Empty directory → empty registry

**LiteLLMBackend tests (mocked `litellm.acompletion`):**
- Kwargs assembled correctly: `api_key`, `base_url`, `max_tokens`, `temperature`, `provider_params`, `extra_params` all passed through
- `TokenUsage` normalisation: `prompt_tokens` → `input_tokens`, `cache_read_input_tokens` → `cached_tokens` (defaults to 0), `completion_tokens` → `output_tokens`
- `SecretStr` used for API key — not visible in `repr()`
- Missing env var → `KeyError` on construction

**ConcurrencyConfig tests:**
- `requests_per_minute` and `tokens_per_minute` no longer accepted as fields
- `max_concurrent_requests` validation unchanged

**Controller integration tests:**
- Existing tests updated to pass `profile` parameter
- Rate limiter uses profile values, semaphore uses `config.concurrency.max_concurrent_requests`
