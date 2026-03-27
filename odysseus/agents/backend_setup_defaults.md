# Backend Setup — Defaults Table

Default values for non-blocking backend configuration fields.

## Defaults

| Field | Default value | Rationale | User-facing note |
|-------|--------------|-----------|------------------|
| `api_key_env` | Inferred from provider | Standard env var per provider: `ANTHROPIC_API_KEY` for anthropic, `OPENAI_API_KEY` for openai, `AWS_ACCESS_KEY_ID` for bedrock | "API key environment variable set to `<var>` based on provider. You can specify a different env var if needed." |
| `temperature` | `None` | Uses provider default; routing responses are short and don't need temperature tuning | "No temperature specified — using provider default." |
| `max_tokens` | `None` | Provider default is sufficient for routing responses | "No max_tokens specified — using provider default." |
| `reasoning_level` | `"medium"` | Balances cost and quality for eval runs | "Reasoning level set to medium. Options: low (cheaper), medium, high (more thorough)." |

## Provider → api_key_env Mapping

| Provider | Default `api_key_env` |
|----------|-----------------------|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `bedrock` | `AWS_ACCESS_KEY_ID` |
| `mock_echo` | `None` |

## Pricing Resolution

Pricing is resolved by calling the `get_default_pricing` MCP tool with `provider` and `model` arguments.

`ModelPricing` fields (all costs are USD per million tokens):

| Field | Purpose |
|-------|---------|
| `input_cost_per_million_tokens` | Standard input |
| `cached_cost_per_million_tokens` | Cache read / prompt cache hits |
| `cache_write_5m_cost_per_million_tokens` | Anthropic 5-minute TTL cache writes (optional, default `0.0`) |
| `cache_write_1h_cost_per_million_tokens` | Anthropic 1-hour TTL cache writes (optional, default `0.0`) |
| `output_cost_per_million_tokens` | Output |

For **OpenAI** and **Bedrock**, the two cache-write fields stay at `0.0` (writes are billed as normal input). For **Anthropic**, defaults include non-zero cache-write rates when auto-resolved from the table.

- If found: show the resolved `ModelPricing` values and offer override
- If not found: pricing becomes blocking — ask user for the required cost fields (at minimum input, cached/read, output; include cache-write fields for Anthropic if not using table defaults)

## Override Mechanism

- User can override any default in the confirmation step
- Overrides replace the full default value
- Only non-blocking fields can have defaults; blocking fields always require explicit input (except conditionally-blocking pricing when auto-resolved)
