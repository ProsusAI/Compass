"""Backend setup tools — pricing lookup."""

import json

from odysseus.eval.pricing import get_default_pricing as _get_default_pricing
from odysseus.mcp.server import mcp


@mcp.tool()
async def get_default_pricing(provider: str, model: str) -> str:
    """Look up default pricing for a (provider, model) pair.

    Used by the backend setup agent to resolve pricing when configuring a
    new backend. Returns the pricing table entry if found.

    Args:
        provider: Provider identifier (e.g. "openai", "anthropic", "bedrock").
        model: Model identifier (e.g. "gpt-5.2", "claude-haiku-4-5").

    Returns:
        JSON object with ``found: true`` and pricing fields (all costs in USD
        per million tokens), or ``{"found": false}`` if no entry exists.
    """
    pricing = _get_default_pricing(provider, model)
    if pricing is None:
        return json.dumps({"found": False})
    return json.dumps({"found": True, **pricing.model_dump()})
