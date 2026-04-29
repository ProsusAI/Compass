#!/usr/bin/env python3
"""Generate a search tree HTML visualization for a beam search run.

Usage:
    python scripts/viz_search_tree.py <run_id> [--output-dir outputs] [--out search_tree.html]
    python scripts/viz_search_tree.py --run-dir outputs/abc123 [--out search_tree.html]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from odysseus.agents.prompt_builder.search_tree import collect_data, render_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate search tree visualization")
    parser.add_argument("run_id", nargs="?", help="Run ID")
    parser.add_argument("--output-dir", default="outputs", help="Root output directory")
    parser.add_argument("--run-dir", help="Direct path to run directory")
    parser.add_argument("--out", help="Output HTML file path")
    args = parser.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_id = run_dir.name
        # Handle both dir/search/ layout and flat layout
        search_dir = run_dir / "search" if (run_dir / "search").exists() else run_dir
    elif args.run_id:
        run_id = args.run_id
        run_dir = Path(args.output_dir) / args.run_id
        search_dir = run_dir / "search" if (run_dir / "search").exists() else run_dir
    else:
        parser.error("Provide either run_id or --run-dir")
        return

    if not search_dir.exists():
        print(f"Error: search directory not found: {search_dir}", file=sys.stderr)
        sys.exit(1)

    data = collect_data(search_dir, run_dir=run_dir)
    out_path = Path(args.out) if args.out else run_dir / "search_tree.html"
    html = render_html(data, run_id)
    out_path.write_text(html, encoding="utf-8")
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
