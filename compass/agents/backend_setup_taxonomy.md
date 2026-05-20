# Backend Setup — Field Taxonomy

Classification rules for backend configuration fields.

## Blocking Fields

| Priority | Field | Classification | Rationale | Default |
|----------|-------|---------------|-----------|---------|
| 0 | `backend_choice` | Blocking | Determines whether to use existing or create new | — |
| 1 | `label` | Blocking | YAML filename; must be unique if creating new | — |
| 2 | `provider` | Blocking | Determines SDK, pricing lookup, and api_key_env | — |
| 3 | `model` | Blocking | Model identifier for API calls | — |
| 4 | `pricing` | Auto-resolved | Resolved silently via `get_default_pricing`. Escalates to orchestrator if lookup fails — never asked by this agent directly. | Resolved from DEFAULT_PRICING |
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
3. Pricing lookup succeeds → apply resolved pricing, show in summary
4. Pricing lookup fails → write YAML without pricing, exit with PRICING_MISSING — orchestrator collects pricing from user and re-dispatches
5. All blocking fields resolved → apply non-blocking defaults → produce output
