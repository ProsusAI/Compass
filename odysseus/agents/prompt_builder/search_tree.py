"""Search tree visualization module for prompt-builder search runs.

Provides functions to collect search data from a run directory and render
it as a self-contained HTML visualization (search tree, scatter plot, timeline).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path


def load_json(path: Path, default: dict | list | None = None) -> dict | list | None:
    """Load a JSON file, returning *default* on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


_STRATEGY_LABELS: dict[str | None, str] = {
    "emosa": "EMOSA",
}

TRAJECTORY_COLORS: list[str] = [
    "#22d3ee",  # T0 — cyan
    "#a78bfa",  # T1 — violet
    "#34d399",  # T2 — emerald
    "#fbbf24",  # T3 — amber
    "#fb7185",  # T4 — rose
]


def _algorithm_chips(state_data: dict) -> list[dict]:
    """Return strategy-specific stat chips for the header. Adapters per algorithm."""
    algo = state_data.get("algorithm")
    pocket = state_data.get("algorithm_state", {})
    if algo == "emosa":
        chips = []
        num_trajectories = pocket.get("num_trajectories")
        if num_trajectories is not None:
            chips.append({"label": "traj", "value": str(num_trajectories)})
        trajectories_pocket = pocket.get("trajectories", []) or []
        temps = [t.get("temperature") for t in trajectories_pocket if t.get("temperature") is not None]
        if temps:
            chips.append({"label": "T", "value": f"{min(temps):.2e}–{max(temps):.2e}"})
        steps = [t.get("step_count") for t in trajectories_pocket if t.get("step_count") is not None]
        if steps:
            chips.append({"label": "step", "value": f"{min(steps)}–{max(steps)}"})
        total_evals = pocket.get("total_evals")
        max_evals = pocket.get("max_evals")
        if total_evals is not None and max_evals is not None:
            chips.append({"label": "evals", "value": f"{total_evals}/{max_evals}"})
        return chips
    return []


def _build_reduction_lookup_from_evals(eval_dir: Path, versions: Iterable[str]) -> dict[str, dict]:
    """Build version -> metrics dict by reading per-candidate eval/<version>/report.json."""
    lookup: dict[str, dict] = {}
    for v in versions:
        report_path = eval_dir / v / "report.json"
        if not report_path.exists():
            lookup[v] = {}
            continue
        metrics = json.loads(report_path.read_text(encoding="utf-8")).get("metrics", {})
        lookup[v] = {
            "cost_reduction": metrics.get("cost_change_with_overhead", metrics.get("cost_change", 0.0)),
            "quality_change": metrics.get("quality_change", 0.0),
            "predicted_cost": metrics.get("predicted_cost"),
            "routing_overhead": metrics.get("routing_overhead"),
            "baseline_cost": metrics.get("baseline_cost"),
            "baseline_quality": metrics.get("baseline_quality"),
            "oracle_cost_change": metrics.get("oracle_cost_change"),
            "oracle_quality_change": metrics.get("oracle_quality_change"),
        }
    return lookup


def _dict_pareto_front(cs: list[dict]) -> set[str]:
    """Return version strings on the Pareto front over (abs_quality, abs_cost)."""
    dominated: set[str] = set()
    for i, a in enumerate(cs):
        if a["version"] in dominated:
            continue
        for j, b in enumerate(cs):
            if i == j or b["version"] in dominated:
                continue
            if (
                a["abs_quality"] >= b["abs_quality"]
                and a["abs_cost"] <= b["abs_cost"]
                and (a["abs_quality"] > b["abs_quality"] or a["abs_cost"] < b["abs_cost"])
            ):
                dominated.add(b["version"])
    return {c["version"] for c in cs if c["version"] not in dominated}


def collect_data(search_dir: Path, run_dir: Path | None = None) -> dict:
    """Read all search data and return the DATA dict for the template."""
    state_data = load_json(search_dir / "search_state.json")
    if not isinstance(state_data, dict):
        raise FileNotFoundError(f"search_state.json not found in {search_dir}")

    # Extract per-round trajectory snapshots (EMOSA only; absent for other algorithms).
    algo_state = state_data.get("algorithm_state", {}) or {}
    traj_history = algo_state.get("trajectory_history", []) if isinstance(algo_state, dict) else []
    iteration_currents: dict[int, list[str]] = {}
    for snap in traj_history:
        if not isinstance(snap, dict):
            continue
        rnd = snap.get("round")
        currents = snap.get("currents") or {}
        if rnd is None or not isinstance(currents, dict):
            continue
        versions = sorted({v for v in currents.values() if isinstance(v, str)})
        iteration_currents[int(rnd)] = versions
    use_trajectory_highlight = bool(iteration_currents)

    archive_loaded = load_json(search_dir / "candidate_archive.json")
    archive: list = archive_loaded if isinstance(archive_loaded, list) else []

    pending_loaded = load_json(search_dir / "pending_candidates.json")
    pending: list = pending_loaded if isinstance(pending_loaded, list) else []

    # Resolve eval dir: prefer run_dir/eval, fall back to search_dir/../eval
    eval_dir = run_dir / "eval" if run_dir is not None else search_dir.parent / "eval"

    # elite_set is the canonical unified field; population is a legacy state-file fallback
    elite_entries = state_data.get("elite_set", state_data.get("population", []))  # legacy state-file fallback
    elite_versions = {c["prompt_version"] for c in elite_entries}

    # Build deduplicated candidate list from union of elite_set + archive + pending.
    # Precedence: elite_set > archive > pending (elite_set is most current).
    # Only include entries where eval_status is "complete" or absent (canonical search-side
    # statuses: pending, running, complete, failed). Ghost entries synthesised from the eval/
    # directory are tagged "scored" to distinguish them; that tag also passes here.
    elite_set_versions = [e["prompt_version"] for e in elite_entries]
    archive_versions = [e["prompt_version"] for e in archive]
    pending_versions = [p["prompt_version"] for p in pending if p.get("eval_status") in ("complete", None)]

    # Ghost candidates: evaluated (eval/<v>/report.json exists) but not in
    # elite_set, archive, or pending — recover from the eval directory.
    # Lineage (parent_version) is lost for ghosts; they render as orphans.
    eval_versions: list[str] = []
    if eval_dir.exists():
        eval_versions = sorted(p.name for p in eval_dir.iterdir() if (p / "report.json").exists())
    all_versions = list(dict.fromkeys(elite_set_versions + archive_versions + pending_versions + eval_versions))

    reductions = _build_reduction_lookup_from_evals(eval_dir, all_versions)

    # Build a lookup of raw entries by version (first write wins = elite_set precedence)
    source_entries: dict[str, dict] = {}
    for src in (elite_entries, archive, pending):
        for e in src:
            v = e["prompt_version"]
            if v not in source_entries:
                source_entries[v] = e

    for v in eval_versions:
        if v in source_entries:
            continue
        source_entries[v] = {
            "prompt_version": v,
            "parent_version": None,
            "secondary_parent_version": None,
            "quality_score": 0.0,
            "iteration_introduced": 0,
            "eval_status": "scored",
            "trajectory_id": None,
        }

    candidates: list[dict] = []
    seen: set[str] = set()
    for v in all_versions:
        if v in seen:
            continue
        e = source_entries[v]
        if e.get("eval_status") not in ("complete", "scored", None):
            continue
        seen.add(v)
        r = reductions.get(v, {})
        pred_cost = r.get("predicted_cost")
        overhead = r.get("routing_overhead")
        abs_cost = round(pred_cost + (overhead or 0.0), 4) if pred_cost is not None else 0.0
        candidates.append(
            {
                "version": v,
                "parent": e.get("parent_version"),
                "secondary_parent": e.get("secondary_parent_version"),
                "score": round(r.get("quality_change", 0.0), 4),
                "cost": round(r.get("cost_reduction", 0.0), 4),
                "abs_quality": round(e.get("quality_score", 0.0), 4),
                "abs_cost": abs_cost,
                "iteration": e.get("iteration_introduced", e.get("round_introduced", 0)),
                "on_front": v in elite_versions,
                "trajectory_id": e.get("trajectory_id"),
            }
        )

    # Synthesize iterations from iteration_introduced buckets
    buckets: dict[int, list[str]] = defaultdict(list)
    for c in candidates:
        buckets[c["iteration"]].append(c["version"])

    iterations = []
    for it in sorted(buckets):
        visible = [c for c in candidates if c["iteration"] <= it]
        front = _dict_pareto_front(visible)
        iterations.append(
            {
                "iteration": it,
                "candidates": buckets[it],
                "new_elite": [v for v in buckets[it] if v in front],
                "front_size": len(front),
            }
        )

    # ── User targets ──
    user_targets_dict: dict[str, float | None] = {
        "quality_delta": None,
        "cost_delta": None,
        "quality_abs": None,
        "cost_abs": None,
    }
    if run_dir is not None:
        input_report = run_dir / "input" / "input_report.md"
        if input_report.exists():
            try:
                from odysseus.agents.review.preprocessor import parse_user_targets

                targets = parse_user_targets(input_report.read_text(encoding="utf-8"))
                quality_delta = next(
                    (t.threshold for t in targets if t.operator in (">=", ">")),
                    None,
                )
                cost_delta = next(
                    (t.threshold for t in targets if t.operator in ("<=", "<")),
                    None,
                )
                user_targets_dict["quality_delta"] = quality_delta
                user_targets_dict["cost_delta"] = cost_delta

                # Compute absolute-mode targets.
                # User targets are percentage deltas relative to the "always use
                # baseline route" reference (e.g. cost_change <= -0.45).
                # quality_abs = baseline_quality * (1 + quality_delta).
                # cost_abs = baseline_cost * (1 + cost_delta), where baseline_cost
                # is the all-baseline-route total from the metrics, not the
                # candidate's predicted route cost.
                if quality_delta is not None or cost_delta is not None:
                    # Find the earliest candidate to derive baselines.
                    # Deltas are relative to the "always use baseline route"
                    # reference. For cost, use baseline_cost from metrics.
                    # For quality, derive from abs_quality / (1 + quality_change)
                    # since abs_quality (the aggregate metric) and the summed
                    # per-example baseline_quality are on different scales.
                    earliest = min(candidates, key=lambda c: c.get("iteration", 0)) if candidates else None
                    if earliest is not None:
                        v = earliest["version"]
                        r = reductions.get(v, {})
                        if quality_delta is not None:
                            qc = r.get("quality_change", 0.0)
                            if (1 + qc) != 0:
                                baseline_abs_quality = earliest["abs_quality"] / (1 + qc)
                                user_targets_dict["quality_abs"] = round(baseline_abs_quality * (1 + quality_delta), 6)
                        if cost_delta is not None:
                            bl_cost = r.get("baseline_cost")
                            if bl_cost is not None:
                                user_targets_dict["cost_abs"] = round(bl_cost * (1 + cost_delta), 6)
            except Exception:
                pass  # If parsing fails, leave all targets as None

    # ── Oracle ceiling ──
    oracle_ceiling_dict: dict[str, float | None] = {
        "cost_delta": None,
        "quality_delta": None,
        "cost_abs": None,
        "quality_abs": None,
    }
    for r in reductions.values():
        oc = r.get("oracle_cost_change")
        oq = r.get("oracle_quality_change")
        if oc is not None and oq is not None:
            oracle_ceiling_dict["cost_delta"] = round(oc, 6)
            oracle_ceiling_dict["quality_delta"] = round(oq, 6)
            # Compute absolute oracle values using same baseline derivation as user targets
            if candidates:
                earliest = min(candidates, key=lambda c: c.get("iteration", 0))
                v = earliest["version"]
                er = reductions.get(v, {})
                # Quality absolute: baseline_abs_quality * (1 + oracle_quality_change)
                qc = er.get("quality_change", 0.0)
                if (1 + qc) != 0:
                    baseline_abs_quality = earliest["abs_quality"] / (1 + qc)
                    oracle_ceiling_dict["quality_abs"] = round(baseline_abs_quality * (1 + oq), 6)
                # Cost absolute: baseline_cost * (1 + oracle_cost_change)
                bl_cost = er.get("baseline_cost")
                if bl_cost is not None:
                    oracle_ceiling_dict["cost_abs"] = round(bl_cost * (1 + oc), 6)
            break

    return {
        "candidates": candidates,
        "iterations": iterations,
        "strategy_label": _STRATEGY_LABELS.get(state_data.get("algorithm"), "Prompt-Builder Search"),
        "algorithm_chips": _algorithm_chips(state_data),
        "user_targets": user_targets_dict,
        "oracle_ceiling": oracle_ceiling_dict,
        "iteration_currents": iteration_currents,
        "use_trajectory_highlight": use_trajectory_highlight,
        "algorithm": state_data.get("algorithm"),
        "trajectory_colors": TRAJECTORY_COLORS,
        "trajectory_weights": [
            t.get("weight_vector") for t in (state_data.get("algorithm_state", {}).get("trajectories") or [])
        ],
    }


def render_html(data: dict, run_id: str) -> str:
    json_str = json.dumps(data, indent=2)
    html = _HTML_TEMPLATE.replace("/*__DATA__*/", json_str)
    html = html.replace("/*__RUN_ID__*/", run_id)
    html = html.replace("__STRATEGY_LABEL__", data.get("strategy_label", "Prompt-Builder Search"))
    return html


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__STRATEGY_LABEL__ — Run /*__RUN_ID__*/</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-primary: #0d1117;
    --bg-secondary: #141b26;
    --bg-panel: #111827;
    --bg-panel-alt: #0f1923;
    --bg-band-even: rgba(255,255,255,0.018);
    --bg-band-odd: rgba(255,255,255,0.005);
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.14);
    --cyan: #00e5ff;
    --cyan-dim: rgba(0,229,255,0.18);
    --cyan-glow: rgba(0,229,255,0.45);
    --amber: #ff9100;
    --amber-dim: rgba(255,145,0,0.15);
    --gold: #ffd740;
    --gold-glow: rgba(255,215,64,0.45);
    --grey: #4a5568;
    --grey-dim: rgba(100,116,139,0.4);
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-dim: #4a5568;
    --font-mono: 'JetBrains Mono', 'Courier New', monospace;
    --font-sans: 'DM Sans', system-ui, sans-serif;
  }

  html, body {
    width: 100%; height: 100%;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 1.5;
    overflow-x: hidden;
  }

  .app {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    padding: 0;
  }

  /* ── Header ── */
  .header {
    padding: 20px 32px 18px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
    display: flex;
    align-items: baseline;
    gap: 24px;
    flex-wrap: wrap;
  }
  .header-title {
    font-family: var(--font-sans);
    font-weight: 600;
    font-size: 17px;
    color: var(--text-primary);
    letter-spacing: 0.01em;
  }
  .header-runid {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--cyan);
    opacity: 0.8;
  }
  .header-subtitle {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--text-secondary);
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-left: auto;
  }
  .stat-chip {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .stat-chip .label { color: var(--text-dim); }
  .stat-chip .value { color: var(--text-primary); font-weight: 500; }
  .stat-chip .value.highlight { color: var(--gold); }

  /* ── Round Slider Bar ── */
  .round-slider-bar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
  }
  .round-slider-title {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    flex-shrink: 0;
  }
  .round-slider-bar input[type="range"] {
    flex: 1;
    max-width: 240px;
    height: 4px;
    cursor: pointer;
    -webkit-appearance: none;
    appearance: none;
    background: rgba(255,255,255,0.08);
    border-radius: 2px;
    outline: none;
  }
  .round-slider-bar input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--cyan);
    cursor: pointer;
    box-shadow: 0 0 6px rgba(0,229,255,0.5);
  }
  .round-slider-label {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-secondary);
    min-width: 140px;
  }
  .round-play-btn {
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border-strong);
    color: var(--text-secondary);
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
    font-family: var(--font-mono);
    transition: background 0.15s;
  }
  .round-play-btn:hover {
    background: rgba(255,255,255,0.12);
    color: var(--text-primary);
  }

  /* ── Main panels ── */
  .panels {
    flex: 1;
    display: flex;
    gap: 0;
    min-height: 680px;
  }

  .panel {
    position: relative;
    display: flex;
    flex-direction: column;
  }

  .panel-tree {
    flex: 0 0 58%;
    border-right: 1px solid var(--border);
    background: var(--bg-panel);
    overflow: hidden;
  }

  .panel-scatter {
    flex: 1;
    background: var(--bg-panel-alt);
    overflow: hidden;
  }

  .panel-header {
    padding: 10px 18px 9px;
    border-bottom: 1px solid var(--border);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .panel-header .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .panel-canvas-wrap {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
  canvas {
    display: block;
  }

  /* ── Legend row ── */
  .legend {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 8px 18px 7px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-secondary);
  }
  .legend-swatch {
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .legend-line {
    width: 18px; height: 2px;
    flex-shrink: 0;
  }

  /* ── Info panel ── */
  .info-panel {
    position: absolute;
    top: 40px; right: 12px;
    width: 200px;
    background: rgba(13, 17, 23, 0.96);
    border: 1px solid var(--border-strong);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-secondary);
    display: none;
    z-index: 20;
    backdrop-filter: blur(4px);
  }
  .info-panel.visible { display: block; }
  .info-panel .info-version {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
  }
  .info-panel .info-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
  }
  .info-panel .info-row .k { color: var(--text-dim); }
  .info-panel .info-row .v { color: var(--text-primary); }
  .info-panel .info-badge {
    margin-top: 8px;
    font-size: 9.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 2px;
    display: inline-block;
  }
  .badge-elite { background: var(--cyan-dim); color: var(--cyan); border: 1px solid rgba(0,229,255,0.3); }
  .badge-dominated { background: var(--amber-dim); color: var(--amber); border: 1px solid rgba(255,145,0,0.25); }

  /* ── Tooltip ── */
  .tooltip {
    position: fixed;
    pointer-events: none;
    background: rgba(13, 17, 23, 0.97);
    border: 1px solid var(--border-strong);
    border-radius: 3px;
    padding: 8px 11px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-secondary);
    z-index: 100;
    display: none;
    min-width: 140px;
    backdrop-filter: blur(4px);
  }
  .tooltip.visible { display: block; }
  .tooltip .tt-version { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 5px; }
  .tooltip .tt-row { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 2px; }
  .tooltip .tt-k { color: var(--text-dim); }
  .tooltip .tt-v { color: var(--text-primary); }

  /* ── Timeline ── */
  .timeline-section {
    border-top: 1px solid var(--border);
    background: var(--bg-secondary);
    padding: 14px 32px 18px;
  }
  .timeline-label {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 10px;
  }
  .timeline-wrap {
    position: relative;
    height: 80px;
  }
  #timelineCanvas {
    width: 100%;
    height: 80px;
  }
</style>
</head>
<body>
<div class="app">

  <!-- Header -->
  <header class="header">
    <div>
      <span class="header-title">__STRATEGY_LABEL__</span>
      <span class="header-runid"> — Run /*__RUN_ID__*/</span>
    </div>
    <div class="header-subtitle" id="headerStats">
    </div>
  </header>

  <!-- Iteration Slider -->
  <div class="round-slider-bar">
    <label class="round-slider-title">Iteration</label>
    <input type="range" id="iterationSlider" min="1" max="1" step="1" value="1"
           oninput="updateIterationFilter(Number(this.value))">
    <span class="round-slider-label" id="iterationSliderLabel">All iterations (1)</span>
    <button id="iterationPlayBtn" class="round-play-btn" onclick="toggleIterationPlay()">&#9654;</button>
  </div>

  <!-- Main panels -->
  <div class="panels">

    <!-- Left: Tree -->
    <div class="panel panel-tree">
      <div class="panel-header">
        <span class="dot" style="background:var(--cyan)"></span>
        Search Tree
      </div>
      <div class="panel-canvas-wrap" id="treeWrap">
        <canvas id="treeCanvas"></canvas>
      </div>
      <div id="treeLegend"></div>
      <!-- Info panel for selected node -->
      <div class="info-panel" id="infoPanel">
        <div class="info-version" id="infoPanelVersion"></div>
        <div class="info-row"><span class="k">score Δ</span><span class="v" id="infoPanelScore"></span></div>
        <div class="info-row"><span class="k">cost Δ</span><span class="v" id="infoPanelCost"></span></div>
        <div class="info-row"><span class="k">iteration</span><span class="v" id="infoPanelRound"></span></div>
        <div class="info-row"><span class="k">parents</span><span class="v" id="infoPanelParent"></span></div>
        <div id="infoPanelBadge"></div>
      </div>
    </div>

    <!-- Right: Scatter -->
    <div class="panel panel-scatter">
      <div class="panel-header">
        <span class="dot" style="background:var(--amber)"></span>
        <span id="scatterPanelTitle">Elite Set — Score Reduction vs Cost Reduction</span>
        <button id="scatterToggle" onclick="toggleScatterMode()"
          style="margin-left:auto;padding:2px 8px;font-family:var(--font-mono);
          font-size:9.5px;letter-spacing:0.06em;text-transform:uppercase;
          background:rgba(255,255,255,0.06);color:var(--text-secondary);
          border:1px solid var(--border-strong);border-radius:2px;
          cursor:pointer;">Absolute</button>
      </div>
      <div class="panel-canvas-wrap" id="scatterWrap">
        <canvas id="scatterCanvas"></canvas>
      </div>
      <div class="legend">
        <div class="legend-item">
          <div class="legend-swatch" style="background:var(--cyan);box-shadow:0 0 4px var(--cyan)"></div>
          <span class="legend-elite-label">Elite set</span>
        </div>
        <div class="legend-item">
          <div class="legend-swatch" style="background:var(--amber);opacity:0.55"></div>
          <span class="legend-dominated-label">Dominated</span>
        </div>
        <div class="legend-item">
          <div class="legend-swatch" style="border:2px dashed rgba(118,255,3,0.7);
            background:transparent;width:12px;height:12px"></div>
          New this iteration
        </div>
        <div class="legend-item">
          <div class="legend-line" style="background:var(--cyan);height:1.5px;opacity:0.6"></div>
          Elite frontier
        </div>
      </div>
    </div>

  </div>

  <!-- Timeline -->
  <div class="timeline-section">
    <div class="timeline-label">Iteration Timeline — new elite additions</div>
    <div class="timeline-wrap">
      <canvas id="timelineCanvas"></canvas>
    </div>
  </div>

</div>

<!-- Tooltip -->
<div class="tooltip" id="tooltip">
  <div class="tt-version" id="ttVersion"></div>
  <div class="tt-row"><span class="tt-k">score Δ</span><span class="tt-v" id="ttScore"></span></div>
  <div class="tt-row"><span class="tt-k">cost Δ</span><span class="tt-v" id="ttCost"></span></div>
  <div class="tt-row"><span class="tt-k">iteration</span><span class="tt-v" id="ttRound"></span></div>
  <div class="tt-row"><span class="tt-k">parents</span><span class="tt-v" id="ttParent"></span></div>
</div>

<script>
// ─────────────────────────────────────────────
//  DATA
// ─────────────────────────────────────────────
const DATA = /*__DATA__*/;

// ─────────────────────────────────────────────
//  TRAJECTORY COLORING HELPERS
// ─────────────────────────────────────────────
function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

function trajectoryColor(c) {
  if (DATA.algorithm !== 'emosa') return null;
  if (c.trajectory_id == null) return null;
  const colors = DATA.trajectory_colors || [];
  return colors[c.trajectory_id] || null;
}

// ─────────────────────────────────────────────
//  TREE LEGEND (data-driven)
// ─────────────────────────────────────────────
function renderTreeLegend() {
  const el = document.getElementById('treeLegend');
  if (!el) return;
  let html = '<div class="legend">';
  if (DATA.algorithm === 'emosa') {
    const weights = DATA.trajectory_weights || [];
    const colors = DATA.trajectory_colors || [];
    const count = weights.length || colors.length;
    for (let i = 0; i < count; i++) {
      const color = colors[i] || '#888';
      const wv = weights[i];
      let wLabel = '';
      if (wv && Array.isArray(wv)) {
        wLabel = ' (w=' + wv.map(function(v) { return v.toFixed(1); }).join(', ') + ')';
      }
      html += '<div class="legend-item">'
        + '<div class="legend-swatch" style="background:' + color + ';box-shadow:0 0 5px ' + hexToRgba(color, 0.6) + '"></div>'
        + 'T' + i + wLabel
        + '</div>';
    }
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="background:rgba(100,116,139,0.45)"></div>'
      + 'Dominated'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="border:2px dashed rgba(118,255,3,0.7);background:transparent;width:12px;height:12px"></div>'
      + 'New this iteration'
      + '</div>';
  } else {
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="background:var(--cyan);box-shadow:0 0 5px var(--cyan)"></div>'
      + '<span class="legend-elite-label">Elite set</span>'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="background:var(--gold);box-shadow:0 0 5px var(--gold)"></div>'
      + 'Best ever'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="background:var(--amber);opacity:0.7"></div>'
      + '<span class="legend-dominated-label">Dominated</span>'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-swatch" style="border:2px dashed rgba(118,255,3,0.7);background:transparent;width:12px;height:12px"></div>'
      + 'New this iteration'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-line" style="background:rgba(0,229,255,0.6);height:2.5px"></div>'
      + 'Elite parent &rarr; child'
      + '</div>';
    html += '<div class="legend-item">'
      + '<div class="legend-line" style="background:rgba(100,116,139,0.5)"></div>'
      + 'Known parent'
      + '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}
renderTreeLegend();

// ─────────────────────────────────────────────
//  HEADER STATS (populated from DATA)
// ─────────────────────────────────────────────
(function() {
  document.getElementById('headerStats').innerHTML =
    '<span class="stat-chip"><span class="label">candidates</span><span class="value">' + DATA.candidates.length + '</span></span>' +
    '<span class="stat-chip"><span class="label">iterations</span><span class="value">' + DATA.iterations.length + '</span></span>' +
    + (DATA.algorithm_chips || []).map(function(c) {
        return '<span class="stat-chip"><span class="label">' + c.label + '</span><span class="value">' + c.value + '</span></span>';
      }).join('');
})();

// ─────────────────────────────────────────────
//  STATE
// ─────────────────────────────────────────────
let selectedVersion = null;
let hoveredVersion = null;
let scatterMode = 'delta'; // 'delta' or 'absolute'
let activeIteration = DATA.iterations.length > 0
  ? DATA.iterations[DATA.iterations.length - 1].iteration
  : (DATA.candidates.length > 0
       ? Math.max(...DATA.candidates.map(c => c.iteration))
       : 0);
const maxIteration = activeIteration;
let filteredCandidates = [];
let frontAtIteration = new Set();
let playInterval = null;

function toggleScatterMode() {
  scatterMode = scatterMode === 'delta' ? 'absolute' : 'delta';
  document.getElementById('scatterToggle').textContent =
    scatterMode === 'delta' ? 'Absolute' : 'Delta';
  document.getElementById('scatterPanelTitle').textContent =
    scatterMode === 'delta'
      ? 'Elite Set \u2014 Quality Change vs Cost Change'
      : 'Elite Set \u2014 Quality Score vs Cost ($)';
  drawScatter(hoveredVersion);
}

// Node positions in the tree canvas (populated after layout)
const nodePositions = {}; // version -> {x, y}

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────
const byVersion = {};
DATA.candidates.forEach(c => { byVersion[c.version] = c; });

function lerp(a, b, t) { return a + (b - a) * t; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// Score range for node sizing
const scores = DATA.candidates.map(c => c.score);
const scoreMin = Math.min(...scores);
const scoreMax = Math.max(...scores);

function nodeRadius(score) {
  const t = scoreMax > scoreMin ? (score - scoreMin) / (scoreMax - scoreMin) : 0.5;
  return lerp(5, 10, t);
}

function computeParetoFront(candidates) {
  const dominated = new Set();
  for (let i = 0; i < candidates.length; i++) {
    if (dominated.has(candidates[i].version)) continue;
    for (let j = 0; j < candidates.length; j++) {
      if (i === j || dominated.has(candidates[j].version)) continue;
      const a = candidates[i], b = candidates[j];
      if (a.abs_quality >= b.abs_quality && a.abs_cost <= b.abs_cost &&
          (a.abs_quality > b.abs_quality || a.abs_cost < b.abs_cost)) {
        dominated.add(b.version);
      }
    }
  }
  return new Set(candidates.filter(c => !dominated.has(c.version)).map(c => c.version));
}

function updateIterationFilter(iteration) {
  activeIteration = iteration;
  filteredCandidates = DATA.candidates.filter(c => c.iteration <= iteration);
  if (DATA.use_trajectory_highlight) {
    // EMOSA: highlight per-iteration trajectory current_solutions.
    // For "all iterations" view, use the most recent snapshot.
    const snapKey = iteration >= maxIteration ? maxIteration : iteration;
    let versions = DATA.iteration_currents[snapKey];
    if (!versions) {
      // Fallback: walk down to the most recent snapshot at or before the active iteration.
      const keys = Object.keys(DATA.iteration_currents).map(Number).sort((a, b) => a - b);
      let pick = null;
      for (const k of keys) {
        if (k <= snapKey) pick = k;
      }
      versions = pick !== null ? DATA.iteration_currents[pick] : [];
    }
    frontAtIteration = new Set(versions);
  } else if (iteration >= maxIteration) {
    // Use backend elite set (respects max_size pruning via crowding distance)
    frontAtIteration = new Set(filteredCandidates.filter(c => c.on_front).map(c => c.version));
  } else {
    frontAtIteration = computeParetoFront(filteredCandidates);
  }

  const slider = document.getElementById('iterationSlider');
  const label = document.getElementById('iterationSliderLabel');
  slider.value = iteration;
  if (iteration >= maxIteration) {
    label.textContent = 'All iterations (' + maxIteration + ')';
  } else {
    label.textContent = 'Iteration ' + iteration + ' of ' + maxIteration;
  }

  drawTree(hoveredVersion);
  drawScatter(hoveredVersion);
  drawTimeline();
}

function toggleIterationPlay() {
  const btn = document.getElementById('iterationPlayBtn');
  if (playInterval) {
    clearInterval(playInterval);
    playInterval = null;
    btn.innerHTML = '&#9654;';
  } else {
    const slider = document.getElementById('iterationSlider');
    slider.value = 1;
    updateIterationFilter(1);
    btn.innerHTML = '&#9646;&#9646;';
    playInterval = setInterval(() => {
      const cur = Number(slider.value);
      if (cur >= maxIteration) {
        clearInterval(playInterval);
        playInterval = null;
        btn.innerHTML = '&#9654;';
        return;
      }
      slider.value = cur + 1;
      updateIterationFilter(cur + 1);
    }, 1200);
  }
}

// ─────────────────────────────────────────────
//  TREE CANVAS
// ─────────────────────────────────────────────
const treeCanvas = document.getElementById('treeCanvas');
const treeCtx = treeCanvas.getContext('2d');
const treeWrap = document.getElementById('treeWrap');

// Layout constants
const MARGIN_LEFT = 64;   // space for round labels
const MARGIN_RIGHT = 24;
const MARGIN_TOP = 52;    // space for "base" node
const MARGIN_BOTTOM = 24;
const BAND_HEIGHT = 60;   // pixels per round

// Rows: 0=base, 1..N=iterations
const TOTAL_ROWS = DATA.iterations.length + 1;

function computeTreeLayout(canvasW) {
  // Assign x positions to nodes per iteration
  // For each iteration, space candidates evenly across the usable width
  // Also place "base" at top center
  const usableW = canvasW - MARGIN_LEFT - MARGIN_RIGHT;

  // base node
  nodePositions['base'] = { x: MARGIN_LEFT + usableW / 2, y: MARGIN_TOP };

  DATA.iterations.forEach((rd, ri) => {
    const y = MARGIN_TOP + (ri + 1) * BAND_HEIGHT + BAND_HEIGHT / 2;
    const n = rd.candidates.length;
    rd.candidates.forEach((ver, ci) => {
      // spread evenly; 3 nodes → positions at 1/4, 2/4, 3/4 of usable width
      const x = MARGIN_LEFT + usableW * (ci + 1) / (n + 1);
      nodePositions[ver] = { x, y };
    });
  });
}

function drawTree(highlight) {
  const rect = treeWrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const W = rect.width;
  const H = MARGIN_TOP + TOTAL_ROWS * BAND_HEIGHT + MARGIN_BOTTOM;
  treeCanvas.width = W * dpr;
  treeCanvas.height = H * dpr;
  treeCanvas.style.width = W + 'px';
  treeCanvas.style.height = H + 'px';
  treeCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  computeTreeLayout(W);

  const ctx = treeCtx;
  ctx.clearRect(0, 0, W, H);

  const isFiltering = activeIteration < maxIteration;
  const visibleVersions = new Set(filteredCandidates.map(c => c.version));
  visibleVersions.add('base');

  // ── Background bands ──
  DATA.iterations.forEach((rd, ri) => {
    const y = MARGIN_TOP + (ri + 1) * BAND_HEIGHT;
    const isFuture = rd.iteration > activeIteration;
    if (isFuture) {
      ctx.fillStyle = 'rgba(255,255,255,0.005)';
    } else {
      ctx.fillStyle = ri % 2 === 0 ? 'rgba(255,255,255,0.025)' : 'rgba(255,255,255,0.008)';
    }
    ctx.fillRect(0, y, W, BAND_HEIGHT);

    // Active iteration highlight
    if (rd.iteration === activeIteration && isFiltering) {
      ctx.fillStyle = 'rgba(0,229,255,0.04)';
      ctx.fillRect(0, y, W, BAND_HEIGHT);
    }
  });

  // ── Iteration labels ──
  ctx.font = '500 10px "JetBrains Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  DATA.iterations.forEach((rd, ri) => {
    const y = MARGIN_TOP + (ri + 1) * BAND_HEIGHT + BAND_HEIGHT / 2;
    const isFuture = rd.iteration > activeIteration;
    if (isFuture) {
      ctx.fillStyle = 'rgba(100,116,139,0.15)';
    } else if (rd.iteration === activeIteration && isFiltering) {
      ctx.fillStyle = 'rgba(0,229,255,0.8)';
    } else {
      ctx.fillStyle = 'rgba(148,163,184,0.45)';
    }
    ctx.fillText(`I${rd.iteration}`, MARGIN_LEFT - 8, y);
  });

  // ── "base" label ──
  const basePos = nodePositions['base'];
  ctx.font = '500 9.5px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(148,163,184,0.5)';
  ctx.fillText('base', basePos.x, basePos.y - 18);

  // ── Edges ──
  filteredCandidates.forEach(c => {
    const pos = nodePositions[c.version];
    if (!pos) return;

    const isNewThisRound = c.iteration === activeIteration && isFiltering;
    const isOnFront = frontAtIteration.has(c.version);

    const tcolor = trajectoryColor(c);

    if (c.parent && nodePositions[c.parent] && visibleVersions.has(c.parent)) {
      const pPos = nodePositions[c.parent];
      const parentOnFront = frontAtIteration.has(c.parent);
      ctx.beginPath();
      ctx.moveTo(pPos.x, pPos.y);
      ctx.lineTo(pos.x, pos.y);
      ctx.setLineDash([]);

      if (tcolor) {
        if (isNewThisRound && parentOnFront) {
          ctx.strokeStyle = hexToRgba(tcolor, 0.7);
          ctx.lineWidth = 2.5;
        } else if (isNewThisRound) {
          ctx.strokeStyle = hexToRgba(tcolor, 0.55);
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = hexToRgba(tcolor, 0.28);
          ctx.lineWidth = 1;
        }
      } else {
        if (isNewThisRound && parentOnFront) {
          ctx.strokeStyle = 'rgba(0,229,255,0.6)';
          ctx.lineWidth = 2.5;
        } else if (isNewThisRound) {
          ctx.strokeStyle = 'rgba(148,163,184,0.55)';
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = 'rgba(100,116,139,0.28)';
          ctx.lineWidth = 1;
        }
      }
      ctx.stroke();
    }

    if (c.secondary_parent && nodePositions[c.secondary_parent] && visibleVersions.has(c.secondary_parent)) {
      const spPos = nodePositions[c.secondary_parent];
      const secondaryParentOnFront = frontAtIteration.has(c.secondary_parent);
      ctx.beginPath();
      ctx.moveTo(spPos.x, spPos.y);
      ctx.lineTo(pos.x, pos.y);
      ctx.setLineDash([]);

      if (tcolor) {
        if (isNewThisRound && secondaryParentOnFront) {
          ctx.strokeStyle = hexToRgba(tcolor, 0.7);
          ctx.lineWidth = 2.5;
        } else if (isNewThisRound) {
          ctx.strokeStyle = hexToRgba(tcolor, 0.55);
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = hexToRgba(tcolor, 0.28);
          ctx.lineWidth = 1;
        }
      } else {
        if (isNewThisRound && secondaryParentOnFront) {
          ctx.strokeStyle = 'rgba(0,229,255,0.6)';
          ctx.lineWidth = 2.5;
        } else if (isNewThisRound) {
          ctx.strokeStyle = 'rgba(148,163,184,0.55)';
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = 'rgba(100,116,139,0.28)';
          ctx.lineWidth = 1;
        }
      }
      ctx.stroke();
    }

    if (!c.parent) {
      // Unknown parent — draw dashed line from a midpoint above
      const ghostY = pos.y - BAND_HEIGHT * 0.45;
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      ctx.lineTo(pos.x, ghostY);
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = 'rgba(74,85,104,0.45)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw "?" marker
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(74,85,104,0.5)';
      ctx.fillText('?', pos.x, ghostY - 6);
    }
  });

  ctx.setLineDash([]);

  // ── Base node ──
  {
    const pos = nodePositions['base'];
    const isHighlighted = highlight === 'base' || hoveredVersion === 'base';
    const r = 7;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
    ctx.fillStyle = isHighlighted ? 'rgba(148,163,184,0.4)' : 'rgba(148,163,184,0.15)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(148,163,184,0.5)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.font = '500 8.5px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(148,163,184,0.6)';
    ctx.fillText('base', pos.x, pos.y + r + 3);
  }

  // ── Nodes ──
  filteredCandidates.forEach(c => {
    const pos = nodePositions[c.version];
    if (!pos) return;

    const isHighlighted = c.version === highlight || c.version === hoveredVersion;
    const isSelected = c.version === selectedVersion;
    const isOnFront = frontAtIteration.has(c.version);
    const isNewThisRound = c.iteration === activeIteration && isFiltering;
    const isOlder = isFiltering && c.iteration < activeIteration;
    const r = nodeRadius(c.score);
    const nc = trajectoryColor(c);

    // "New this round" dashed ring
    if (isNewThisRound) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r + 8, 0, Math.PI * 2);
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = 'rgba(118,255,3,0.65)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Glow for elite nodes
    if (isOnFront) {
      const glowR = r + 5;
      const grad = ctx.createRadialGradient(pos.x, pos.y, r * 0.3, pos.x, pos.y, glowR);
      if (nc) {
        grad.addColorStop(0, hexToRgba(nc, 0.35));
        grad.addColorStop(1, hexToRgba(nc, 0));
      } else {
        grad.addColorStop(0, 'rgba(0,229,255,0.35)');
        grad.addColorStop(1, 'rgba(0,229,255,0)');
      }
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, glowR, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.globalAlpha = isOlder ? 0.5 : 1.0;
      ctx.fill();
      ctx.globalAlpha = 1.0;
    }

    // Highlight ring for hovered/selected
    if (isHighlighted || isSelected) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r + 4, 0, Math.PI * 2);
      if (nc) {
        ctx.strokeStyle = hexToRgba(nc, 0.7);
      } else {
        ctx.strokeStyle = isOnFront ? 'rgba(0,229,255,0.7)' : 'rgba(255,145,0,0.7)';
      }
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Node fill
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
    if (nc) {
      ctx.fillStyle = nc;
      ctx.globalAlpha = isOlder ? (isOnFront ? 0.5 : 0.25) : (isHighlighted || isSelected ? 1.0 : (isOnFront ? 0.85 : 0.42));
    } else if (isOnFront) {
      ctx.fillStyle = '#00e5ff';
      ctx.globalAlpha = isOlder ? 0.5 : (isHighlighted || isSelected ? 1.0 : 0.85);
    } else {
      ctx.fillStyle = '#ff9100';
      ctx.globalAlpha = isOlder ? 0.25 : (isHighlighted || isSelected ? 0.75 : 0.42);
    }
    ctx.fill();
    ctx.globalAlpha = 1.0;

    // Node border
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
    if (nc) {
      ctx.strokeStyle = nc;
    } else {
      ctx.strokeStyle = isOnFront ? '#00e5ff' : '#ff9100';
    }
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = isOnFront ? (isOlder ? 0.5 : 0.9) : (isOlder ? 0.3 : 0.5);
    ctx.stroke();
    ctx.globalAlpha = 1.0;

    // Label
    ctx.font = '500 8.5px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    if (nc) {
      ctx.fillStyle = hexToRgba(nc, 0.75);
    } else {
      ctx.fillStyle = isOnFront ? 'rgba(0,229,255,0.75)' : 'rgba(255,145,0,0.6)';
    }
    ctx.globalAlpha = isOlder ? 0.45 : (isHighlighted || isSelected ? 1.0 : 0.8);
    ctx.fillText(c.version, pos.x, pos.y + r + 3);
    ctx.globalAlpha = 1.0;
  });
}

function resizeTree() {
  drawTree(hoveredVersion);
}

// ─────────────────────────────────────────────
//  SCATTER CANVAS
// ─────────────────────────────────────────────
const scatterCanvas = document.getElementById('scatterCanvas');
const scatterCtx = scatterCanvas.getContext('2d');
const scatterWrap = document.getElementById('scatterWrap');

// Scatter positions in canvas coords (populated after layout)
const scatterPositions = {}; // version -> {x, y}

const S_MARGIN = { top: 24, right: 24, bottom: 52, left: 58 };

function getScatterBounds() {
  const oc = DATA.oracle_ceiling;
  if (scatterMode === 'absolute') {
    const absQ = DATA.candidates.map(c => c.abs_quality);
    const absC = DATA.candidates.map(c => c.abs_cost);
    let qMin = Math.min(...absQ); let qMax = Math.max(...absQ);
    let cMin = Math.min(...absC); let cMax = Math.max(...absC);
    const targets = DATA.user_targets;
    if (targets) {
        if (targets.cost_abs != null) { cMin = Math.min(cMin, targets.cost_abs); cMax = Math.max(cMax, targets.cost_abs); }
        if (targets.quality_abs != null) { qMin = Math.min(qMin, targets.quality_abs); qMax = Math.max(qMax, targets.quality_abs); }
    }
    // Use oracle ceiling as bounds (cost_abs is lower bound, quality_abs is upper bound)
    if (oc && oc.cost_abs != null) { cMin = Math.min(cMin, oc.cost_abs); }
    if (oc && oc.quality_abs != null) { qMax = Math.max(qMax, oc.quality_abs); }
    const qPad = (qMax - qMin) * 0.06 || 0.015;
    const cPad = (cMax - cMin) * 0.06 || 0.04;
    return { xMin: cMin - cPad, xMax: cMax + cPad, yMin: qMin - qPad, yMax: qMax + qPad };
  }
  const costs = DATA.candidates.map(c => c.cost);
  let cMin = Math.min(...costs); let cMax = Math.max(...costs);
  let qMin = scoreMin; let qMax = scoreMax;
  const targets = DATA.user_targets;
  if (targets) {
      if (targets.cost_delta != null) { cMin = Math.min(cMin, targets.cost_delta); cMax = Math.max(cMax, targets.cost_delta); }
      if (targets.quality_delta != null) { qMin = Math.min(qMin, targets.quality_delta); qMax = Math.max(qMax, targets.quality_delta); }
  }
  // Use oracle ceiling as bounds (cost_delta is lower bound, quality_delta is upper bound)
  if (oc && oc.cost_delta != null) { cMin = Math.min(cMin, oc.cost_delta); }
  if (oc && oc.quality_delta != null) { qMax = Math.max(qMax, oc.quality_delta); }
  const cPad = (cMax - cMin) * 0.06 || 0.04;
  const qPad = (qMax - qMin) * 0.06 || 0.015;
  return { xMin: cMin - cPad, xMax: cMax + cPad, yMin: qMin - qPad, yMax: qMax + qPad };
}

function toScatterCoords(score, cost, W, H, bounds) {
  const b = bounds || getScatterBounds();
  // X flipped: most negative cost (biggest reduction) on the right
  const px = S_MARGIN.left + (1 - (cost - b.xMin) / (b.xMax - b.xMin)) * (W - S_MARGIN.left - S_MARGIN.right);
  const py = S_MARGIN.top + (1 - (score - b.yMin) / (b.yMax - b.yMin)) * (H - S_MARGIN.top - S_MARGIN.bottom);
  return { x: px, y: py };
}

function drawScatter(highlight) {
  const rect = scatterWrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const W = rect.width;
  const H = rect.height;
  scatterCanvas.width = W * dpr;
  scatterCanvas.height = H * dpr;
  scatterCanvas.style.width = W + 'px';
  scatterCanvas.style.height = H + 'px';
  scatterCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const ctx = scatterCtx;
  ctx.clearRect(0, 0, W, H);

  const plotW = W - S_MARGIN.left - S_MARGIN.right;
  const plotH = H - S_MARGIN.top - S_MARGIN.bottom;

  const bounds = getScatterBounds();
  const isAbsolute = scatterMode === 'absolute';
  const xAxisLabel = isAbsolute ? 'cost ($)' : 'cost change';
  const yAxisLabel = isAbsolute ? 'quality score' : 'quality change';

  // ── Grid ──
  const nXTicks = 5, nYTicks = 5;
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= nXTicks; i++) {
    const x = S_MARGIN.left + (i / nXTicks) * plotW;
    ctx.beginPath(); ctx.moveTo(x, S_MARGIN.top); ctx.lineTo(x, S_MARGIN.top + plotH); ctx.stroke();
  }
  for (let i = 0; i <= nYTicks; i++) {
    const y = S_MARGIN.top + (i / nYTicks) * plotH;
    ctx.beginPath(); ctx.moveTo(S_MARGIN.left, y); ctx.lineTo(S_MARGIN.left + plotW, y); ctx.stroke();
  }

  // ── Axis lines ──
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(S_MARGIN.left, S_MARGIN.top);
  ctx.lineTo(S_MARGIN.left, S_MARGIN.top + plotH);
  ctx.lineTo(S_MARGIN.left + plotW, S_MARGIN.top + plotH);
  ctx.stroke();

  // ── Axis labels ──
  ctx.font = '9.5px "JetBrains Mono", monospace';
  ctx.fillStyle = 'rgba(100,116,139,0.7)';
  ctx.textAlign = 'center';
  for (let i = 0; i <= nXTicks; i++) {
    // Flipped: leftmost tick = xMax (least reduction / highest cost), rightmost = xMin
    const v = bounds.xMax - i / nXTicks * (bounds.xMax - bounds.xMin);
    const x = S_MARGIN.left + (i / nXTicks) * plotW;
    ctx.fillText(v.toFixed(2), x, S_MARGIN.top + plotH + 16);
  }
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= nYTicks; i++) {
    const v = bounds.yMin + (1 - i / nYTicks) * (bounds.yMax - bounds.yMin);
    const y = S_MARGIN.top + (i / nYTicks) * plotH;
    ctx.fillText(v.toFixed(3), S_MARGIN.left - 8, y);
  }

  // Axis titles
  ctx.font = '9px "DM Sans", sans-serif';
  ctx.fillStyle = 'rgba(100,116,139,0.55)';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText(xAxisLabel, S_MARGIN.left + plotW / 2, H - 4);

  ctx.save();
  ctx.translate(12, S_MARGIN.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(yAxisLabel, 0, 0);
  ctx.restore();

  // ── Target region ──
  const targets = DATA.user_targets;
  if (targets) {
    const tq = isAbsolute ? targets.quality_abs : targets.quality_delta;
    const tc = isAbsolute ? targets.cost_abs : targets.cost_delta;

    if (tq !== null || tc !== null) {
      const yTop = S_MARGIN.top;
      const yBot = S_MARGIN.top + plotH;
      const xLeft = S_MARGIN.left;
      const xRight = S_MARGIN.left + plotW;

      let regionTop = yTop;
      let regionBot = yBot;
      let regionLeft = xLeft;
      let regionRight = xRight;

      if (tq !== null && tq >= bounds.yMin && tq <= bounds.yMax) {
        // Quality >= tq means above this line (lower pixel y)
        const p = toScatterCoords(tq, bounds.xMin, W, H, bounds);
        regionBot = p.y;
      }
      if (tc !== null && tc >= bounds.xMin && tc <= bounds.xMax) {
        // Cost <= tc means to the left of tc in data space, which is to the RIGHT in pixel space (x is flipped)
        const p = toScatterCoords(bounds.yMin, tc, W, H, bounds);
        regionLeft = p.x;
      }

      // Clip to plot area
      regionTop = Math.max(regionTop, yTop);
      regionBot = Math.min(regionBot, yBot);
      regionLeft = Math.max(regionLeft, xLeft);
      regionRight = Math.min(regionRight, xRight);

      if (regionBot > regionTop && regionRight > regionLeft) {
        // Fill
        ctx.fillStyle = 'rgba(76, 175, 80, 0.06)';
        ctx.fillRect(regionLeft, regionTop, regionRight - regionLeft, regionBot - regionTop);

        // Dashed border
        ctx.strokeStyle = 'rgba(76, 175, 80, 0.25)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(regionLeft, regionTop, regionRight - regionLeft, regionBot - regionTop);
        ctx.setLineDash([]);

        // Label
        ctx.font = '8px "DM Sans", sans-serif';
        ctx.fillStyle = 'rgba(76, 175, 80, 0.5)';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'top';
        ctx.fillText('target', regionRight - 4, regionTop + 3);
      }

      // Draw crosshair at exact target point if both dimensions present
      if (tq !== null && tc !== null) {
        const tp = toScatterCoords(tq, tc, W, H, bounds);
        if (tp.x >= xLeft && tp.x <= xRight && tp.y >= yTop && tp.y <= yBot) {
          ctx.strokeStyle = 'rgba(76, 175, 80, 0.5)';
          ctx.lineWidth = 1;
          const sz = 5;
          ctx.beginPath();
          ctx.moveTo(tp.x - sz, tp.y); ctx.lineTo(tp.x + sz, tp.y);
          ctx.moveTo(tp.x, tp.y - sz); ctx.lineTo(tp.x, tp.y + sz);
          ctx.stroke();

          // Small diamond
          ctx.beginPath();
          ctx.moveTo(tp.x, tp.y - 3);
          ctx.lineTo(tp.x + 3, tp.y);
          ctx.lineTo(tp.x, tp.y + 3);
          ctx.lineTo(tp.x - 3, tp.y);
          ctx.closePath();
          ctx.fillStyle = 'rgba(76, 175, 80, 0.4)';
          ctx.fill();
          ctx.strokeStyle = 'rgba(76, 175, 80, 0.6)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }
  }

  // ── Compute scatter positions (filtered candidates only; axes use ALL candidates) ──
  filteredCandidates.forEach(c => {
    const scoreVal = isAbsolute ? c.abs_quality : c.score;
    const costVal  = isAbsolute ? c.abs_cost   : c.cost;
    const p = toScatterCoords(scoreVal, costVal, W, H, bounds);
    scatterPositions[c.version] = p;
  });

  const isFiltering = activeIteration < maxIteration;

  // ── Elite frontier line ──
  const frontNodes = filteredCandidates.filter(c => frontAtIteration.has(c.version)).sort((a, b) => {
    const aCost = isAbsolute ? a.abs_cost : a.cost;
    const bCost = isAbsolute ? b.abs_cost : b.cost;
    return aCost - bCost;
  });
  if (frontNodes.length > 1) {
    ctx.beginPath();
    frontNodes.forEach((c, i) => {
      const p = scatterPositions[c.version];
      if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
    });
    ctx.strokeStyle = 'rgba(0,229,255,0.35)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── Dots — dominated first (behind) ──
  filteredCandidates.filter(c => !frontAtIteration.has(c.version)).forEach(c => {
    const p = scatterPositions[c.version];
    const isH = c.version === highlight || c.version === hoveredVersion;
    const isS = c.version === selectedVersion;
    const isNewThisRound = c.iteration === activeIteration && isFiltering;
    const isOlder = isFiltering && c.iteration < activeIteration;
    const r = nodeRadius(c.score) + 1;

    if (isNewThisRound) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 6, 0, Math.PI * 2);
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = 'rgba(118,255,3,0.6)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = '#ff9100';
    ctx.globalAlpha = isOlder ? 0.2 : (isH || isS ? 0.85 : (isNewThisRound ? 0.8 : 0.38));
    ctx.fill();
    ctx.globalAlpha = 1;

    if (isH || isS) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,145,0,0.7)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  });

  // ── Dots — elite set on top ──
  filteredCandidates.filter(c => frontAtIteration.has(c.version)).forEach(c => {
    const p = scatterPositions[c.version];
    const isH = c.version === highlight || c.version === hoveredVersion;
    const isS = c.version === selectedVersion;
    const isNewThisRound = c.iteration === activeIteration && isFiltering;
    const isOlder = isFiltering && c.iteration < activeIteration;
    const r = nodeRadius(c.score) + 1;

    if (isNewThisRound) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 7, 0, Math.PI * 2);
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = 'rgba(118,255,3,0.65)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Glow
    const glowR = r + 6;
    const grad = ctx.createRadialGradient(p.x, p.y, r * 0.2, p.x, p.y, glowR);
    grad.addColorStop(0, 'rgba(0,229,255,0.4)');
    grad.addColorStop(1, 'rgba(0,229,255,0)');
    ctx.beginPath();
    ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.globalAlpha = isOlder ? 0.4 : 1.0;
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = '#00e5ff';
    ctx.globalAlpha = isOlder ? 0.5 : (isH || isS ? 1.0 : 0.85);
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = '#00e5ff';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    if (isH || isS) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 5, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0,229,255,0.7)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Version label
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = 'rgba(0,229,255,0.7)';
    ctx.globalAlpha = isOlder ? 0.4 : 0.9;
    ctx.fillText(c.version, p.x, p.y - r - 2);
    ctx.globalAlpha = 1;
  });
}

function resizeScatter() {
  drawScatter(hoveredVersion);
}

// ─────────────────────────────────────────────
//  TIMELINE CANVAS
// ─────────────────────────────────────────────
const tlCanvas = document.getElementById('timelineCanvas');
const tlCtx = tlCanvas.getContext('2d');

function drawTimeline() {
  const dpr = window.devicePixelRatio || 1;
  const rect = tlCanvas.parentElement.getBoundingClientRect();
  const W = rect.width;
  const H = 80;
  tlCanvas.width = W * dpr;
  tlCanvas.height = H * dpr;
  tlCanvas.style.width = W + 'px';
  tlCanvas.style.height = H + 'px';
  tlCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const ctx = tlCtx;
  const n = DATA.iterations.length;
  const ML = 32, MR = 20, MT = 8, MB = 24;
  const barW = (W - ML - MR) / n;
  const maxBarH = H - MT - MB - 18; // reserve space for front_size line

  // ── Bar color ──
  function barColor() {
    return 'rgba(0,180,120,0.7)';
  }

  const maxNewElite = Math.max(...DATA.iterations.map(r => r.new_elite), 1);
  const maxFrontSize = Math.max(...DATA.iterations.map(r => r.front_size));
  const minFrontSize = Math.min(...DATA.iterations.map(r => r.front_size));
  const isFiltering = activeIteration < maxIteration;

  DATA.iterations.forEach((rd, ri) => {
    const bx = ML + ri * barW;
    const bh = rd.new_elite / maxNewElite * maxBarH;
    const by = MT + maxBarH - bh;
    const isFuture = rd.iteration > activeIteration;
    const isActive = rd.iteration === activeIteration;

    // Active iteration highlight
    if (isActive && isFiltering) {
      ctx.fillStyle = 'rgba(0,229,255,0.08)';
      ctx.fillRect(bx, 0, barW, H);

      // Triangle indicator
      ctx.fillStyle = 'rgba(0,229,255,0.7)';
      ctx.beginPath();
      ctx.moveTo(bx + barW / 2 - 5, 2);
      ctx.lineTo(bx + barW / 2 + 5, 2);
      ctx.lineTo(bx + barW / 2, 8);
      ctx.closePath();
      ctx.fill();
    }

    // Bar
    ctx.fillStyle = barColor();
    ctx.globalAlpha = isFuture ? 0.15 : 1.0;
    ctx.fillRect(bx + 2, by + 16, barW - 4, bh);
    ctx.globalAlpha = 1;

    // Iteration label
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = isActive && isFiltering
      ? 'rgba(0,229,255,0.9)'
      : (isFuture ? 'rgba(100,116,139,0.25)' : 'rgba(100,116,139,0.7)');
    ctx.fillText(`I${rd.iteration}`, bx + barW / 2, H - MB + 10);

    // New elite count on top of bar
    if (rd.new_elite > 0 && !isFuture) {
      ctx.fillStyle = 'rgba(0,229,255,0.7)';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.fillText('+' + rd.new_elite, bx + barW / 2, by + 14);
    }
  });

  // ── Front size line (only up to activeIteration) ──
  const visibleIterations = DATA.iterations.filter(r => r.iteration <= activeIteration);
  if (visibleIterations.length > 0) {
    ctx.beginPath();
    visibleIterations.forEach((rd, i) => {
      const ri = DATA.iterations.indexOf(rd);
      const bx = ML + ri * barW + barW / 2;
      const t = maxFrontSize > minFrontSize ? (rd.front_size - minFrontSize) / (maxFrontSize - minFrontSize) : 0.5;
      const ly = MT + 6 + (1 - t) * (maxBarH - 4);
      if (i === 0) ctx.moveTo(bx, ly); else ctx.lineTo(bx, ly);
    });
    ctx.strokeStyle = 'rgba(0,229,255,0.5)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    visibleIterations.forEach(rd => {
      const ri = DATA.iterations.indexOf(rd);
      const bx = ML + ri * barW + barW / 2;
      const t = maxFrontSize > minFrontSize ? (rd.front_size - minFrontSize) / (maxFrontSize - minFrontSize) : 0.5;
      const ly = MT + 6 + (1 - t) * (maxBarH - 4);
      ctx.beginPath();
      ctx.arc(bx, ly, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#00e5ff';
      ctx.fill();
    });
  }

  // Legend
  ctx.font = '8.5px "JetBrains Mono", monospace';
  ctx.fillStyle = 'rgba(100,116,139,0.55)';
  ctx.textAlign = 'left';
  ctx.fillText('bars: new elite additions per iteration   line: elite set size   click bar to jump', ML, H - 2);
}

// ─────────────────────────────────────────────
//  TOOLTIP & INFO PANEL
// ─────────────────────────────────────────────
const tooltip = document.getElementById('tooltip');
const ttVersion = document.getElementById('ttVersion');
const ttScore = document.getElementById('ttScore');
const ttCost = document.getElementById('ttCost');
const ttRound = document.getElementById('ttRound');
const ttParent = document.getElementById('ttParent');

function formatParents(c) {
  const parts = [];
  if (c.parent) parts.push(c.parent);
  if (c.secondary_parent && c.secondary_parent !== c.parent) parts.push(c.secondary_parent);
  return parts.length ? parts.join(', ') : '(unknown)';
}

function showTooltip(c, mx, my) {
  ttVersion.textContent = c.version;
  ttScore.textContent = (c.score >= 0 ? '+' : '') + c.score.toFixed(4);
  ttCost.textContent = (c.cost >= 0 ? '+' : '') + c.cost.toFixed(4);
  ttRound.textContent = c.iteration;
  ttParent.textContent = formatParents(c);
  tooltip.classList.add('visible');
  positionTooltip(mx, my);
}

function positionTooltip(mx, my) {
  const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
  let lx = mx + 14, ly = my - th / 2;
  if (lx + tw > window.innerWidth - 10) lx = mx - tw - 14;
  if (ly < 4) ly = 4;
  if (ly + th > window.innerHeight - 4) ly = window.innerHeight - th - 4;
  tooltip.style.left = lx + 'px';
  tooltip.style.top = ly + 'px';
}

function hideTooltip() {
  tooltip.classList.remove('visible');
}

const infoPanel = document.getElementById('infoPanel');
const infoPanelVersion = document.getElementById('infoPanelVersion');
const infoPanelScore = document.getElementById('infoPanelScore');
const infoPanelCost = document.getElementById('infoPanelCost');
const infoPanelRound = document.getElementById('infoPanelRound');
const infoPanelParent = document.getElementById('infoPanelParent');
const infoPanelBadge = document.getElementById('infoPanelBadge');

function showInfoPanel(ver) {
  const c = byVersion[ver];
  if (!c) { infoPanel.classList.remove('visible'); return; }
  infoPanelVersion.textContent = c.version;
  infoPanelScore.textContent = (c.score >= 0 ? '+' : '') + c.score.toFixed(4);
  infoPanelCost.textContent = (c.cost >= 0 ? '+' : '') + c.cost.toFixed(4);
  infoPanelRound.textContent = `iteration ${c.iteration}`;
  infoPanelParent.textContent = formatParents(c);
  const isOnFront = frontAtIteration.has(c.version);
  const badgeClass = isOnFront ? 'badge-elite' : 'badge-dominated';
  const badgeText = DATA.use_trajectory_highlight
    ? (isOnFront ? 'trajectory current' : 'not current')
    : (isOnFront ? 'elite set' : 'not in elite set');
  const isNewThisRound = c.iteration === activeIteration && activeIteration < maxIteration;
  const newStyle = 'background:rgba(118,255,3,0.1);color:rgba(118,255,3,0.9);'
    + 'border:1px solid rgba(118,255,3,0.3);margin-left:4px';
  const newBadge = isNewThisRound
    ? `<span class="info-badge" style="${newStyle}">new this iteration</span>`
    : '';
  infoPanelBadge.innerHTML = `<span class="info-badge ${badgeClass}">${badgeText}</span>${newBadge}`;
  infoPanel.classList.add('visible');
}

// ─────────────────────────────────────────────
//  HIT TESTING
// ─────────────────────────────────────────────
function hitTestTree(canvasX, canvasY) {
  for (const c of filteredCandidates) {
    const pos = nodePositions[c.version];
    if (!pos) continue;
    const r = nodeRadius(c.score) + 4;
    const dx = canvasX - pos.x, dy = canvasY - pos.y;
    if (dx * dx + dy * dy <= r * r) return c.version;
  }
  return null;
}

function hitTestScatter(canvasX, canvasY) {
  for (const c of filteredCandidates) {
    const pos = scatterPositions[c.version];
    if (!pos) continue;
    const r = nodeRadius(c.score) + 1 + 5;
    const dx = canvasX - pos.x, dy = canvasY - pos.y;
    if (dx * dx + dy * dy <= r * r) return c.version;
  }
  return null;
}

function getCanvasCoords(canvas, evt) {
  const rect = canvas.getBoundingClientRect();
  return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
}

// ─────────────────────────────────────────────
//  EVENT LISTENERS
// ─────────────────────────────────────────────
treeCanvas.addEventListener('mousemove', evt => {
  const {x, y} = getCanvasCoords(treeCanvas, evt);
  const hit = hitTestTree(x, y);
  if (hit !== hoveredVersion) {
    hoveredVersion = hit;
    treeCanvas.style.cursor = hit ? 'pointer' : 'default';
    drawTree(null);
    drawScatter(null);
  }
  if (hit) {
    showTooltip(byVersion[hit], evt.clientX, evt.clientY);
  } else {
    hideTooltip();
  }
});

treeCanvas.addEventListener('mouseleave', () => {
  hoveredVersion = null;
  hideTooltip();
  drawTree(null);
  drawScatter(null);
});

treeCanvas.addEventListener('click', evt => {
  const {x, y} = getCanvasCoords(treeCanvas, evt);
  const hit = hitTestTree(x, y);
  if (hit) {
    selectedVersion = selectedVersion === hit ? null : hit;
    if (selectedVersion) showInfoPanel(selectedVersion);
    else infoPanel.classList.remove('visible');
    drawTree(null);
    drawScatter(null);
  }
});

scatterCanvas.addEventListener('mousemove', evt => {
  const {x, y} = getCanvasCoords(scatterCanvas, evt);
  const hit = hitTestScatter(x, y);
  if (hit !== hoveredVersion) {
    hoveredVersion = hit;
    scatterCanvas.style.cursor = hit ? 'pointer' : 'default';
    drawTree(null);
    drawScatter(null);
  }
  if (hit) {
    showTooltip(byVersion[hit], evt.clientX, evt.clientY);
  } else {
    hideTooltip();
  }
});

scatterCanvas.addEventListener('mouseleave', () => {
  hoveredVersion = null;
  hideTooltip();
  drawTree(null);
  drawScatter(null);
});

scatterCanvas.addEventListener('click', evt => {
  const {x, y} = getCanvasCoords(scatterCanvas, evt);
  const hit = hitTestScatter(x, y);
  if (hit) {
    selectedVersion = selectedVersion === hit ? null : hit;
    if (selectedVersion) showInfoPanel(selectedVersion);
    else infoPanel.classList.remove('visible');
    drawTree(null);
    drawScatter(null);
  }
});

// Dismiss info panel on click-outside
document.addEventListener('click', evt => {
  if (!treeCanvas.contains(evt.target) && !scatterCanvas.contains(evt.target)) {
    selectedVersion = null;
    infoPanel.classList.remove('visible');
    drawTree(null);
    drawScatter(null);
  }
});

// Timeline click — jump to iteration
tlCanvas.addEventListener('click', evt => {
  const rect = tlCanvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const n = DATA.iterations.length;
  const ML = 32, MR = 20;
  const barW = (rect.width - ML - MR) / n;
  const ri = Math.floor((x - ML) / barW);
  if (ri >= 0 && ri < n) {
    updateIterationFilter(DATA.iterations[ri].iteration);
  }
});
tlCanvas.style.cursor = 'pointer';

// ─────────────────────────────────────────────
//  INIT & RESIZE
// ─────────────────────────────────────────────
function initAll() {
  const slider = document.getElementById('iterationSlider');
  slider.min = DATA.iterations.length > 0 ? DATA.iterations[0].iteration : 1;
  slider.max = maxIteration;
  slider.value = maxIteration;
  updateIterationFilter(maxIteration);
}

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => updateIterationFilter(activeIteration), 60);
});

// Wait for fonts to load before first render
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(initAll);
} else {
  setTimeout(initAll, 200);
}
</script>
</body>
</html>
"""
