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

Pricing is resolved via `get_default_pricing(provider, model)` from `odysseus/eval/pricing.py`.
- If found: show the resolved `ModelPricing` values and offer override
- If not found: pricing becomes blocking — ask user for all three cost fields

## Override Mechanism

- User can override any default in the confirmation step
- Overrides replace the full default value
- Only non-blocking fields can have defaults; blocking fields always require explicit input (except conditionally-blocking pricing when auto-resolved)
