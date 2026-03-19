"""MCP server entrypoint for Odysseus."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("odysseus")


@mcp.tool()
async def optimize_routing_prompt(
    data_path: str,
    problem_description: str,
    target_metrics: list[str],
) -> str:
    """Run the full routing prompt optimization pipeline.

    Args:
        data_path: Path to JSONL routing dataset.
        problem_description: Natural language description of the routing task.
        target_metrics: List of metric names and thresholds (e.g. "accuracy>=0.90").

    Returns:
        Structured evaluation report with the final optimized prompt.
    """
    # TODO: Wire up the full pipeline
    return f"Pipeline not yet implemented. Received: {data_path}, {problem_description}, {target_metrics}"


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
