"""Backend setup tools — pricing lookup."""

import json

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import compass.project_dir as _project_dir_mod
from compass.eval.pricing import get_default_pricing as _get_default_pricing
from compass.mcp.server import mcp


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


@mcp.tool()
async def save_backend_options(ctx: Context, run_id: str, backend_options_json: str) -> str:
    """[Stage 3: Backend Setup] Save available backend options for orchestrator-mediated user selection.

    Args:
        run_id: Pipeline run identifier.
        backend_options_json: JSON object with key ``available_backends`` (list of backend dicts).

    Returns:
        Confirmation message with the persisted file path.
    """
    try:
        backend_options = json.loads(backend_options_json)
    except json.JSONDecodeError as exc:
        raise ToolError(f"Invalid JSON for backend_options_json: {exc}") from exc

    if "available_backends" not in backend_options or not isinstance(backend_options["available_backends"], list):
        raise ToolError("backend_options_json must contain key 'available_backends' with a list value.")

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    out_dir = project_dir / "outputs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "backend_options.json"
    out_path.write_text(json.dumps(backend_options, indent=2), encoding="utf-8")
    return f"Backend options saved to {out_path}"
