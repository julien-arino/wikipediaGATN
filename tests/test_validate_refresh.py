"""Unit tests for the weekly-refresh guardrail (``scripts/validate_refresh.py``).

The script is a standalone CLI, not an installed module, so it is loaded by
path.  The pure comparison logic operates on :class:`NetworkSummary` objects and
is exercised directly, with no files; the IO layer is tested against small CSVs
written into ``tmp_path``.
"""

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load scripts/validate_refresh.py by path.
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_refresh.py"
_spec = importlib.util.spec_from_file_location("validate_refresh", _SCRIPT)
vr = importlib.util.module_from_spec(_spec)
sys.modules["validate_refresh"] = vr
assert _spec.loader is not None
_spec.loader.exec_module(vr)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: A healthy baseline: 5 hubs with decreasing out-degree + some leaf/zero nodes.
BASELINE = {
    "AAA": 100,
    "BBB": 80,
    "CCC": 60,
    "DDD": 40,
    "EEE": 20,
    "F01": 2,
    "F02": 1,
    "Z01": 0,
    "Z02": 0,
}


def _summary(degrees):
    return vr.NetworkSummary(dict(degrees))


def _write_network_csv(path, degrees):
    """Write a minimal network edge-list CSV with the given out-degrees."""
    lines = ['"origin","nb_outlinks","outlinks","weights","nb_airlines"']
    for origin, deg in degrees.items():
        lines.append(f'"{origin}","{deg}","","",""')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# NetworkSummary
# ---------------------------------------------------------------------------


class TestNetworkSummary:
    def test_counts(self):
        s = _summary(BASELINE)
        assert s.n_nodes == 9
        assert s.n_edges == 100 + 80 + 60 + 40 + 20 + 2 + 1
        assert s.n_zero_out_nodes() == 2

    def test_top_hubs_ordered_by_degree(self):
        s = _summary(BASELINE)
        hubs = s.top_hubs(3)
        assert hubs == [("AAA", 100), ("BBB", 80), ("CCC", 60)]

    def test_top_hubs_ties_broken_by_node_id(self):
        s = _summary({"B": 5, "A": 5, "C": 1})
        # Equal degree -> deterministic alphabetical order.
        assert s.top_hubs(2) == [("A", 5), ("B", 5)]

    def test_empty_summary(self):
        s = _summary({})
        assert s.n_nodes == 0
        assert s.n_edges == 0
        assert s.n_zero_out_nodes() == 0


# ---------------------------------------------------------------------------
# compare() — the core guardrail
# ---------------------------------------------------------------------------


class TestCompare:
    def test_identical_passes(self):
        res = vr.compare(_summary(BASELINE), _summary(BASELINE))
        assert res.ok
        assert res.failures == []

    def test_growth_is_allowed(self):
        grown = dict(BASELINE)
        grown["NEW"] = 50
        grown["AAA"] = 150
        res = vr.compare(_summary(BASELINE), _summary(grown))
        assert res.ok

    def test_small_churn_passes(self):
        # A couple of nodes and a few routes wobble -> fine.
        churned = dict(BASELINE)
        churned["AAA"] = 95
        churned["F02"] = 0  # a tiny leaf goes quiet
        res = vr.compare(_summary(BASELINE), _summary(churned))
        assert res.ok

    def test_empty_baseline_skipped_with_warning(self):
        res = vr.compare(_summary({}), _summary(BASELINE))
        assert res.ok
        assert res.warnings
        assert "empty" in res.warnings[0]

    def test_node_count_collapse_fails(self):
        # Keep only the hubs -> >10% of nodes gone.
        shrunk = {"AAA": 100, "BBB": 80}
        res = vr.compare(_summary(BASELINE), _summary(shrunk))
        assert not res.ok
        assert any("node count" in f for f in res.failures)

    def test_edge_count_collapse_fails(self):
        halved = {k: v // 3 for k, v in BASELINE.items()}
        res = vr.compare(_summary(BASELINE), _summary(halved))
        assert not res.ok
        assert any("edge count" in f for f in res.failures)

    def test_hub_dropping_to_zero_fails(self):
        broken = dict(BASELINE)
        broken["AAA"] = 0  # a top hub loses everything
        res = vr.compare(_summary(BASELINE), _summary(broken))
        assert not res.ok
        assert any("all outbound routes" in f for f in res.failures)
        assert any("AAA" in f for f in res.failures)

    def test_hub_missing_entirely_fails(self):
        broken = {k: v for k, v in BASELINE.items() if k != "BBB"}
        res = vr.compare(_summary(BASELINE), _summary(broken))
        assert not res.ok
        assert any("BBB" in f for f in res.failures)

    def test_hub_losing_more_than_half_fails(self):
        broken = dict(BASELINE)
        broken["CCC"] = 20  # 60 -> 20 is a 66% loss
        res = vr.compare(_summary(BASELINE), _summary(broken))
        assert not res.ok
        assert any("out-degree" in f and "CCC" in f for f in res.failures)

    def test_hub_losing_just_under_half_passes(self):
        nudged = dict(BASELINE)
        nudged["DDD"] = 21  # 40 -> 21 is a 47% loss, under the 50% floor
        res = vr.compare(_summary(BASELINE), _summary(nudged))
        assert res.ok

    def test_small_leaf_going_to_zero_is_not_a_hub_collapse(self):
        # A node with out-degree below ``min_hub_outdegree`` is not guarded as a
        # hub, so it dropping to zero is ordinary churn, not a failure.
        broken = dict(BASELINE)
        broken["F01"] = 0  # out-degree 2 -> 0
        res = vr.compare(_summary(BASELINE), _summary(broken))
        assert not any("outbound routes" in f for f in res.failures)

    def test_zero_out_spike_fails(self):
        base = {f"N{i:03d}": 5 for i in range(400)}
        cand = dict(base)
        # Zero out 120 of them: +120 absolute and a huge relative jump.
        for i in range(120):
            cand[f"N{i:03d}"] = 0
        res = vr.compare(_summary(base), _summary(cand))
        assert not res.ok
        assert any("no outbound routes" in f for f in res.failures)

    def test_zero_out_small_absolute_increase_passes(self):
        # Even a large *relative* jump passes when the absolute count is tiny,
        # so small networks are not over-sensitive.
        base = {"A": 10, "B": 10, "C": 10, "Z": 0}
        cand = {"A": 10, "B": 0, "C": 0, "Z": 0}  # +2 zeros only
        res = vr.compare(_summary(base), _summary(cand))
        # Node/edge/hub checks may or may not trip, but the zero-spike one must
        # not: +2 is under the absolute allowance.
        assert not any("no outbound routes" in f for f in res.failures)

    def test_custom_thresholds_are_honoured(self):
        strict = vr.Thresholds(max_node_drop_frac=0.0)
        slightly_smaller = {k: v for k, v in BASELINE.items() if k != "Z02"}
        res = vr.compare(_summary(BASELINE), _summary(slightly_smaller), strict)
        assert not res.ok


# ---------------------------------------------------------------------------
# summarize_csv() — the IO layer
# ---------------------------------------------------------------------------


class TestSummarizeCsv:
    def test_reads_out_degrees(self, tmp_path):
        csv_path = tmp_path / "net.csv"
        _write_network_csv(csv_path, {"AAA": 3, "BBB": 0})
        s = vr.summarize_csv(csv_path)
        assert s.out_degree == {"AAA": 3, "BBB": 0}

    def test_blank_and_bad_counts_become_zero(self, tmp_path):
        csv_path = tmp_path / "net.csv"
        csv_path.write_text(
            '"origin","nb_outlinks","outlinks","weights","nb_airlines"\n'
            '"AAA","","","",""\n'
            '"BBB","nope","","",""\n'
            '"CCC","7","","",""\n',
            encoding="utf-8",
        )
        s = vr.summarize_csv(csv_path)
        assert s.out_degree == {"AAA": 0, "BBB": 0, "CCC": 7}

    def test_blank_origin_rows_skipped(self, tmp_path):
        csv_path = tmp_path / "net.csv"
        csv_path.write_text(
            '"origin","nb_outlinks","outlinks","weights","nb_airlines"\n'
            '"","5","","",""\n'
            '"AAA","5","","",""\n',
            encoding="utf-8",
        )
        s = vr.summarize_csv(csv_path)
        assert s.out_degree == {"AAA": 5}


# ---------------------------------------------------------------------------
# validate_dirs() and the CLI
# ---------------------------------------------------------------------------


class TestValidateDirs:
    def _make_dirs(self, tmp_path, baseline, candidate, networks=("pax",)):
        base_dir = tmp_path / "baseline"
        cand_dir = tmp_path / "candidate"
        base_dir.mkdir()
        cand_dir.mkdir()
        for name in networks:
            filename = vr.NETWORK_CSVS[name]
            _write_network_csv(base_dir / filename, baseline)
            _write_network_csv(cand_dir / filename, candidate)
        return base_dir, cand_dir

    def test_passing_pair(self, tmp_path):
        base_dir, cand_dir = self._make_dirs(tmp_path, BASELINE, BASELINE)
        results = vr.validate_dirs(base_dir, cand_dir, ["pax"])
        assert all(r.ok for r in results)

    def test_regression_pair(self, tmp_path):
        broken = dict(BASELINE)
        broken["AAA"] = 0
        base_dir, cand_dir = self._make_dirs(tmp_path, BASELINE, broken)
        results = vr.validate_dirs(base_dir, cand_dir, ["pax"])
        assert not all(r.ok for r in results)

    def test_missing_candidate_fails(self, tmp_path):
        base_dir = tmp_path / "baseline"
        cand_dir = tmp_path / "candidate"
        base_dir.mkdir()
        cand_dir.mkdir()
        _write_network_csv(base_dir / vr.NETWORK_CSVS["pax"], BASELINE)
        results = vr.validate_dirs(base_dir, cand_dir, ["pax"])
        assert not results[0].ok
        assert any("missing" in f for f in results[0].failures)

    def test_missing_baseline_skipped(self, tmp_path):
        base_dir = tmp_path / "baseline"
        cand_dir = tmp_path / "candidate"
        base_dir.mkdir()
        cand_dir.mkdir()
        _write_network_csv(cand_dir / vr.NETWORK_CSVS["pax"], BASELINE)
        results = vr.validate_dirs(base_dir, cand_dir, ["pax"])
        assert results[0].ok
        assert results[0].warnings


class TestMainCli:
    def test_main_returns_zero_on_pass(self, tmp_path, capsys):
        base_dir = tmp_path / "baseline"
        cand_dir = tmp_path / "candidate"
        base_dir.mkdir()
        cand_dir.mkdir()
        for d in (base_dir, cand_dir):
            _write_network_csv(d / vr.NETWORK_CSVS["pax"], BASELINE)
            _write_network_csv(d / vr.NETWORK_CSVS["cargo"], BASELINE)
        rc = vr.main(
            [
                "--baseline-dir",
                str(base_dir),
                "--candidate-dir",
                str(cand_dir),
            ]
        )
        assert rc == 0
        assert "passed" in capsys.readouterr().out

    def test_main_returns_one_on_regression(self, tmp_path, capsys):
        base_dir = tmp_path / "baseline"
        cand_dir = tmp_path / "candidate"
        base_dir.mkdir()
        cand_dir.mkdir()
        broken = dict(BASELINE)
        broken["AAA"] = 0
        _write_network_csv(base_dir / vr.NETWORK_CSVS["pax"], BASELINE)
        _write_network_csv(cand_dir / vr.NETWORK_CSVS["pax"], broken)
        rc = vr.main(
            [
                "--baseline-dir",
                str(base_dir),
                "--candidate-dir",
                str(cand_dir),
                "--networks",
                "pax",
            ]
        )
        assert rc == 1
        assert "FAILED" in capsys.readouterr().out
