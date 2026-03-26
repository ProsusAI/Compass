"""CLI commands for Odysseus."""

from __future__ import annotations

import argparse
from pathlib import Path


_MOCK_BACKEND = """\
model: mock-echo
provider: mock_echo
requests_per_minute: 10000
tokens_per_minute: 1000000
"""

_RUN_CONFIG = """\
metrics:
  - name: accuracy
output:
  results_path: outputs/results.jsonl
  report_path: outputs/report.json
concurrency:
  max_concurrent_requests: 20
retry:
  max_attempts: 3
  backoff_factor: 2.0
  per_call_timeout_seconds: 60.0
"""


def run_init(target: Path) -> None:
    """Scaffold the required project directories and starter files."""
    dirs = ["outputs", "prompts", "backends"]
    for d in dirs:
        (target / d).mkdir(parents=True, exist_ok=True)

    starters: dict[str, str] = {
        "backends/mock-echo.yaml": _MOCK_BACKEND,
        "outputs/run_config.yaml": _RUN_CONFIG,
    }
    for rel_path, content in starters.items():
        path = target / rel_path
        if not path.exists():
            path.write_text(content)

    print(f"Initialized Odysseus project in {target}")
    print("Created directories: outputs/, prompts/, backends/")
    print("Next steps:")
    print("  1. Add backend configs to backends/ (e.g. anthropic.yaml)")
    print("  2. Add routing prompts to prompts/")
    print("  3. Edit outputs/run_config.yaml for your metrics")


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint — routes to subcommands or starts MCP server."""
    parser = argparse.ArgumentParser(prog="odysseus", description="Odysseus Routing Optimizer")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Scaffold project directories and starter files")
    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Target directory (default: current directory)",
    )

    subparsers.add_parser("serve", help="Start the MCP server (default)")

    args = parser.parse_args(argv)

    if args.command == "init":
        run_init(Path(args.directory).resolve())
    else:
        from odysseus.mcp import main as mcp_main

        mcp_main()
