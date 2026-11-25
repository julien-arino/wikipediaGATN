#!/usr/bin/env python3
"""Guardrail for the automated weekly data refresh.

The weekly workflow re-scrapes Wikipedia and rebuilds the published networks.
A scrape can regress for reasons that have nothing to do with real-world
changes: Wikipedia markup drifts, a parser edge case breaks, the NLP model
behaves differently, or a transient network error empties a hub's destination
table.  Committing such a result straight to ``main`` would silently corrupt the
published data.

This script compares a freshly built network (the *candidate*) against the
currently committed network (the *baseline*) and **fails** when the difference
looks like a regression rather than a genuine update.  The workflow runs it
between building the data and opening the refresh pull request, so a suspicious
rebuild aborts the job instead of being published.

What it checks (per network, passenger and cargo)
--------------------------------------------------
* **Node count** must not drop by more than a fraction of the baseline.
* **Edge count** must not drop by more than a fraction of the baseline.
* **Top-N hubs** (the busiest airports in the baseline) must each keep at
  least some outbound routes — none may collapse to zero — and must not lose
  more than a fraction of their out-degree.
* **Zero-out-degree airports** (nodes with no outbound routes) must not spike:
  a sudden jump usually means destination tables failed to parse.

The thresholds are deliberately permissive — genuine weekly churn is small, so
the guardrail only trips on the kind of large, structural loss a scrape
regression produces.  Growth is always allowed.

The comparison logic is kept as pure functions operating on
:class:`NetworkSummary` objects so it is unit-tested without any files.  The CLI
is a thin layer that reads the per-node out-degree straight from the network
edge-list CSV (the ``nb_outlinks`` column), so no graph library is required.

Usage
-----
::

    python scripts/validate_refresh.py \\
        --baseline-dir /tmp/baseline/public \\
        --candidate-dir data/public

Exit status is ``0`` when every network passes (or is skipped because no
baseline exists yet) and ``1`` when any check fails.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Tolerances for the refresh guardrail.

    All fractions are expressed as "how much of the baseline may be lost".
    Growth is never penalised.
    """

    #: Reject if the candidate has fewer nodes than this fraction of the
    #: baseline removed (0.10 -> a >10% drop in airports fails).
    max_node_drop_frac: float = 0.10
    #: Same, for the number of directed edges (routes).
    max_edge_drop_frac: float = 0.15
    #: How many of the baseline's busiest airports to guard individually.
    hub_top_n: int = 25
    #: Only guard a top-N node as a "hub" if it had at least this many outbound
    #: routes in the baseline; a tiny leaf going quiet is ordinary churn, not a
    #: hub collapse, and should not trip the guardrail.
    min_hub_outdegree: int = 10
    #: Reject if any guarded hub loses more than this fraction of its
    #: out-degree (and always reject a hub that drops to zero).
    max_hub_outdegree_drop_frac: float = 0.50
    #: Reject if the count of zero-out-degree airports grows by more than this
    #: fraction of the baseline count *and* by more than the absolute allowance
    #: below (both must be exceeded, so tiny baselines are not over-sensitive).
    max_zero_outdegree_increase_frac: float = 0.25
    max_zero_outdegree_increase_abs: int = 50


# ---------------------------------------------------------------------------
# Network summary (the pure data the checks operate on)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkSummary:
    """A minimal, comparable summary of one directed network.

    Holds only each node's out-degree, which is all the guardrail needs and is
    exactly the ``nb_outlinks`` column of the published edge-list CSV.
    """

    out_degree: Dict[str, int]

    @property
    def n_nodes(self) -> int:
        return len(self.out_degree)

    @property
    def n_edges(self) -> int:
        return sum(self.out_degree.values())

    def n_zero_out_nodes(self) -> int:
        return sum(1 for d in self.out_degree.values() if d == 0)

    def top_hubs(self, n: int) -> List[Tuple[str, int]]:
        """The ``n`` highest-out-degree nodes, ties broken by node id.

        Sorting by ``(-degree, node)`` makes the result deterministic so the
        same hubs are guarded run to run.
        """
        ranked = sorted(self.out_degree.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:n]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Outcome of comparing one network."""

    label: str
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures


# ---------------------------------------------------------------------------
# Pure comparison logic
# ---------------------------------------------------------------------------


def compare(
    baseline: NetworkSummary,
    candidate: NetworkSummary,
    thresholds: Optional[Thresholds] = None,
    *,
    label: str = "network",
) -> ValidationResult:
    """Compare a candidate network against a baseline.

    Returns a :class:`ValidationResult` whose ``failures`` list is empty iff the
    candidate passes every guardrail.  A baseline with no nodes is treated as
    "nothing to compare against": the result is a pass with a warning, so the
    very first refresh (or an empty fixture) does not spuriously fail.
    """
    thresholds = thresholds or Thresholds()
    result = ValidationResult(label=label)

    result.stats.update(
        {
            "baseline_nodes": baseline.n_nodes,
            "candidate_nodes": candidate.n_nodes,
            "baseline_edges": baseline.n_edges,
            "candidate_edges": candidate.n_edges,
            "baseline_zero_out": baseline.n_zero_out_nodes(),
            "candidate_zero_out": candidate.n_zero_out_nodes(),
        }
    )

    if baseline.n_nodes == 0:
        result.warnings.append(
            f"[{label}] baseline is empty; skipping comparison "
            "(first refresh or missing baseline)."
        )
        return result

    # --- node count -------------------------------------------------------
    min_nodes = baseline.n_nodes * (1.0 - thresholds.max_node_drop_frac)
    if candidate.n_nodes < min_nodes:
        result.failures.append(
            f"[{label}] node count dropped from {baseline.n_nodes} to "
            f"{candidate.n_nodes} "
            f"(>{thresholds.max_node_drop_frac:.0%} loss; floor "
            f"{min_nodes:.0f})."
        )

    # --- edge count -------------------------------------------------------
    if baseline.n_edges > 0:
        min_edges = baseline.n_edges * (1.0 - thresholds.max_edge_drop_frac)
        if candidate.n_edges < min_edges:
            result.failures.append(
                f"[{label}] edge count dropped from {baseline.n_edges} to "
                f"{candidate.n_edges} "
                f"(>{thresholds.max_edge_drop_frac:.0%} loss; floor "
                f"{min_edges:.0f})."
            )

    # --- top-N hubs -------------------------------------------------------
    collapsed: List[str] = []
    shrank: List[str] = []
    for node, base_deg in baseline.top_hubs(thresholds.hub_top_n):
        if base_deg < thresholds.min_hub_outdegree:
            continue
        cand_deg = candidate.out_degree.get(node, 0)
        if cand_deg <= 0:
            collapsed.append(f"{node} ({base_deg}->0)")
        elif cand_deg < base_deg * (1.0 - thresholds.max_hub_outdegree_drop_frac):
            shrank.append(f"{node} ({base_deg}->{cand_deg})")
    if collapsed:
        result.failures.append(
            f"[{label}] {len(collapsed)} top-{thresholds.hub_top_n} hub(s) lost "
            f"all outbound routes: {', '.join(collapsed)}."
        )
    if shrank:
        result.failures.append(
            f"[{label}] {len(shrank)} top-{thresholds.hub_top_n} hub(s) lost "
            f">{thresholds.max_hub_outdegree_drop_frac:.0%} of out-degree: "
            f"{', '.join(shrank)}."
        )

    # --- zero-out-degree spike -------------------------------------------
    base_zero = baseline.n_zero_out_nodes()
    cand_zero = candidate.n_zero_out_nodes()
    increase = cand_zero - base_zero
    allowed_frac = base_zero * thresholds.max_zero_outdegree_increase_frac
    if (
        increase > thresholds.max_zero_outdegree_increase_abs
        and increase > allowed_frac
    ):
        result.failures.append(
            f"[{label}] airports with no outbound routes spiked from "
            f"{base_zero} to {cand_zero} (+{increase}); likely destination "
            "tables that failed to parse."
        )

    return result


# ---------------------------------------------------------------------------
# IO layer
# ---------------------------------------------------------------------------

#: Network edge-list CSVs, keyed by the ``--networks`` short name.
NETWORK_CSVS: Dict[str, str] = {
    "pax": "global-air-pax-network.csv",
    "cargo": "global-air-cargo-network.csv",
}


def summarize_csv(path: Path) -> NetworkSummary:
    """Build a :class:`NetworkSummary` from a network edge-list CSV.

    Reads the ``origin`` and ``nb_outlinks`` columns; ``nb_outlinks`` is the
    node's out-degree.  Rows with a blank or non-integer count are treated as
    zero so a malformed file degrades to "looks like a regression" rather than
    crashing.
    """
    out_degree: Dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            origin = (row.get("origin") or "").strip()
            if not origin:
                continue
            raw = (row.get("nb_outlinks") or "").strip()
            try:
                out_degree[origin] = int(raw)
            except ValueError:
                out_degree[origin] = 0
    return NetworkSummary(out_degree)


def validate_dirs(
    baseline_dir: Path,
    candidate_dir: Path,
    networks: List[str],
    thresholds: Optional[Thresholds] = None,
) -> List[ValidationResult]:
    """Compare every requested network between two ``data/public`` directories.

    A network whose candidate CSV is missing fails loudly (the rebuild should
    have produced it).  A network whose *baseline* CSV is missing is skipped
    with a warning (nothing to compare against yet).
    """
    thresholds = thresholds or Thresholds()
    results: List[ValidationResult] = []
    for name in networks:
        filename = NETWORK_CSVS[name]
        base_csv = baseline_dir / filename
        cand_csv = candidate_dir / filename

        if not cand_csv.exists():
            res = ValidationResult(label=name)
            res.failures.append(
                f"[{name}] candidate network file is missing: {cand_csv}."
            )
            results.append(res)
            continue

        candidate = summarize_csv(cand_csv)

        if not base_csv.exists():
            res = ValidationResult(label=name)
            res.warnings.append(
                f"[{name}] no baseline at {base_csv}; skipping comparison."
            )
            res.stats.update(
                {
                    "candidate_nodes": candidate.n_nodes,
                    "candidate_edges": candidate.n_edges,
                }
            )
            results.append(res)
            continue

        baseline = summarize_csv(base_csv)
        results.append(compare(baseline, candidate, thresholds, label=name))

    return results


# ---------------------------------------------------------------------------
# Reporting / CLI
# ---------------------------------------------------------------------------


def format_report(results: List[ValidationResult]) -> str:
    """Render a human-readable report of all network results."""
    lines: List[str] = []
    for res in results:
        status = "PASS" if res.ok else "FAIL"
        lines.append(f"[{status}] {res.label}")
        if res.stats:
            nodes = res.stats.get("candidate_nodes")
            edges = res.stats.get("candidate_edges")
            b_nodes = res.stats.get("baseline_nodes")
            b_edges = res.stats.get("baseline_edges")
            if b_nodes is not None:
                lines.append(
                    f"    nodes: {b_nodes} -> {nodes}    "
                    f"edges: {b_edges} -> {edges}    "
                    f"zero-out: {res.stats.get('baseline_zero_out')} -> "
                    f"{res.stats.get('candidate_zero_out')}"
                )
            else:
                lines.append(f"    nodes: {nodes}    edges: {edges}")
        for warn in res.warnings:
            lines.append(f"    WARN  {warn}")
        for fail in res.failures:
            lines.append(f"    FAIL  {fail}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a freshly refreshed network against the committed "
            "baseline and fail on a likely scrape regression."
        )
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        required=True,
        help="Directory holding the committed (baseline) network CSVs.",
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        required=True,
        help="Directory holding the freshly rebuilt (candidate) network CSVs.",
    )
    parser.add_argument(
        "--networks",
        nargs="+",
        choices=sorted(NETWORK_CSVS),
        default=sorted(NETWORK_CSVS),
        help="Which networks to validate (default: all).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    results = validate_dirs(
        args.baseline_dir,
        args.candidate_dir,
        list(args.networks),
    )
    print(format_report(results))
    if any(not res.ok for res in results):
        print("\nRefresh validation FAILED; not publishing the rebuilt data.")
        return 1
    print("\nRefresh validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
