# Backend Setup — Field Taxonomy

Classification rules for backend configuration fields.

## Blocking Fields

| Priority | Field | Classification | Rationale | Default |
|----------|-------|---------------|-----------|---------|
| 0 | `backend_choice` | Blocking | Determines whether to use existing or create new | — |
| 1 | `label` | Blocking | YAML filename; must be unique if creating new | — |
| 2 | `provider` | Blocking | Determines SDK, pricing lookup, and api_key_env | — |
| 3 | `model` | Blocking | Model identifier for API calls | — |
| 4 | `pricing` | Conditionally blocking | Auto-resolved via `get_default_pricing(provider, model)`. Blocking only if lookup returns `None` — user must then provide `input_cost_per_million_tokens`, `cached_cost_per_million_tokens`, `output_cost_per_million_tokens` | Resolved from DEFAULT_PRICING |
| 5 | `requests_per_minute` | Blocking | Rate limit; no safe universal default | — |
| 6 | `tokens_per_minute` | Blocking | Rate limit; no safe universal default | — |

## Non-blocking Fields

| Field | Classification | Rationale | Default |
|-------|---------------|-----------|---------|
| `api_key_env` | Non-blocking | Standard env var names per provider | Inferred: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AWS_ACCESS_KEY_ID` |
| `temperature` | Non-blocking | Provider default is fine for routing | `None` |
| `max_tokens` | Non-blocking | Provider default sufficient | `None` |
| `reasoning_level` | Non-blocking | Sensible middle ground | `"medium"` |

## Status Decision Logic

1. User selects existing backend → short-circuit, no further fields needed
2. Any blocking gap unresolved → continue conversing
3. Pricing lookup succeeds → show resolved pricing, offer override, treat as resolved
4. Pricing lookup fails → pricing becomes blocking, ask user
5. All blocking fields resolved → apply non-blocking defaults → produce output
