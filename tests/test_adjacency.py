"""
Tests for :mod:`wikipediaGATN.adjacency`.

All I/O is redirected to a temporary directory by monkeypatching the
module-level ``PUBLIC_DATA_DIR`` constant.  The env-var approach
(``WIKIPEDIAGATN_DATA_DIR``) cannot be used here because path constants
are bound at import time, before ``monkeypatch.setenv`` would run.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import load_npz

from wikipediaGATN.adjacency import create_outbound_adjacency_matrix

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def public_dir(tmp_path, monkeypatch):
    """
    Redirect adjacency module I/O to a temp directory and return the path.
    """
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr("wikipediaGATN.adjacency.PUBLIC_DATA_DIR", public)
    return public


def _write_connections(public_dir: Path, rows: list) -> Path:
    """Write a minimal ``global-air-pax-network.csv`` and return its path."""
    csv_path = public_dir / "global-air-pax-network.csv"
    df = pd.DataFrame(rows, columns=["origin", "nb_outlinks", "outlinks"])
    df.to_csv(csv_path, index=False)
    return csv_path


def _load_nodes(nodes_path: str) -> list:
    return [l.strip() for l in Path(nodes_path).read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrors:

    def test_raises_when_csv_missing(self, public_dir):
        """FileNotFoundError when global-air-pax-network.csv is absent."""
        with pytest.raises(FileNotFoundError, match="global-air-pax-network.csv"):
            create_outbound_adjacency_matrix(verbose=False)

    def test_raises_when_all_origins_malformed(self, public_dir):
        """ValueError when every origin row fails IATA validation."""
        _write_connections(
            public_dir,
            [
                {"origin": "TOOLONG", "nb_outlinks": 1, "outlinks": "YYZ"},
                {"origin": "12", "nb_outlinks": 1, "outlinks": "YUL"},
            ],
        )
        with pytest.raises(ValueError, match="No valid airport records"):
            create_outbound_adjacency_matrix(verbose=False)

    def test_raises_when_csv_empty(self, public_dir):
        """ValueError (or EmptyDataError) on a header-only CSV."""
        (public_dir / "global-air-pax-network.csv").write_text(
            "origin,nb_outlinks,outlinks\n"
        )
        with pytest.raises((ValueError, pd.errors.EmptyDataError)):
            create_outbound_adjacency_matrix(verbose=False)


# ---------------------------------------------------------------------------
# Directed matrix
# ---------------------------------------------------------------------------


class TestDirectedMatrix:

    def test_returns_two_strings(self, public_dir):
        """Return value is a ``(str, str)`` tuple."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        result = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(p, str) for p in result)

    def test_output_files_exist(self, public_dir):
        """Both ``.npz`` and ``.txt`` files are written."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        assert os.path.exists(matrix_path)
        assert os.path.exists(nodes_path)

    def test_output_filenames_directed(self, public_dir):
        """Directed outputs use the unsuffixed names."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        assert matrix_path.endswith("adjacency_matrix_pax.npz")
        assert nodes_path.endswith("nodes_pax.txt")

    def test_matrix_shape_matches_node_count(self, public_dir):
        """Matrix is square with side equal to the number of unique airports."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 2, "outlinks": "YYZ YVR"},
                {"origin": "YYZ", "nb_outlinks": 1, "outlinks": "YVR"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        matrix = load_npz(matrix_path)
        nodes = _load_nodes(nodes_path)
        assert matrix.shape == (len(nodes), len(nodes))

    def test_node_list_is_sorted(self, public_dir):
        """Node list file is in ascending alphabetical order."""
        _write_connections(
            public_dir,
            [
                {"origin": "YYZ", "nb_outlinks": 1, "outlinks": "YWG"},
                {"origin": "YVR", "nb_outlinks": 1, "outlinks": "YWG"},
                {"origin": "AAA", "nb_outlinks": 1, "outlinks": "ZZZ"},
            ],
        )
        _, nodes_path = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        nodes = _load_nodes(nodes_path)
        assert nodes == sorted(nodes)

    def test_directed_edge_present_reverse_absent(self, public_dir):
        """A->B = 1, B->A = 0 when only A->B is listed."""
        _write_connections(
            public_dir,
            [
                {"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        matrix = load_npz(matrix_path)
        nodes = _load_nodes(nodes_path)
        a, b = nodes.index("AAA"), nodes.index("BBB")
        assert matrix[a, b] == 1, "A->B should be 1"
        assert matrix[b, a] == 0, "B->A should be 0 in directed mode"

    def test_default_weights_are_one(self, public_dir):
        """No weights column in CSV defaults to weight 1."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 3, "outlinks": "YYZ YVR YYC"},
                {"origin": "YYZ", "nb_outlinks": 1, "outlinks": "YWG"},
            ],
        )
        matrix_path, _ = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        assert load_npz(matrix_path).data.max() == 1

    def test_weighted_edges(self, public_dir):
        """Matrix entries reflect the weights in the CSV."""
        df = pd.DataFrame(
            [
                {
                    "origin": "YWG",
                    "nb_outlinks": 2,
                    "outlinks": "YYZ YYC",
                    "weights": "5 3",
                },
            ]
        )
        df.to_csv(public_dir / "global-air-pax-network.csv", index=False)

        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        matrix = load_npz(matrix_path)
        nodes = _load_nodes(nodes_path)

        iwg = nodes.index("YWG")
        iyz = nodes.index("YYZ")
        iyc = nodes.index("YYC")

        assert matrix[iwg, iyz] == 5
        assert matrix[iwg, iyc] == 3

    def test_self_loops_excluded(self, public_dir):
        """An airport listed as its own destination produces no self-loop."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 2, "outlinks": "YWG YYZ"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        matrix = load_npz(matrix_path)
        nodes = _load_nodes(nodes_path)
        idx = nodes.index("YWG")
        assert matrix[idx, idx] == 0

    def test_malformed_destination_tokens_silently_dropped(self, public_dir):
        """Non-IATA tokens in the outlinks column are silently ignored."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 2, "outlinks": "YYZ TOOLONG"},
            ],
        )
        _, nodes_path = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        assert "TOOLONG" not in _load_nodes(nodes_path)

    def test_nan_origin_rows_dropped(self, public_dir):
        """Rows with NaN origin are silently filtered without crashing."""
        csv_path = public_dir / "global-air-pax-network.csv"
        pd.DataFrame(
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
                {"origin": float("nan"), "nb_outlinks": 1, "outlinks": "YVR"},
            ]
        ).to_csv(csv_path, index=False)
        _, nodes_path = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        nodes = _load_nodes(nodes_path)
        assert "YWG" in nodes
        assert "YYZ" in nodes

    def test_destination_only_airport_appears_in_nodes(self, public_dir):
        """Airports that only appear as destinations are still included in nodes."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "ZZZ"},
            ],
        )
        _, nodes_path = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        assert "ZZZ" in _load_nodes(nodes_path)

    def test_single_self_loop_node(self, public_dir):
        """A single node with only a self-loop is included in nodes but has no edges."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YWG"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=False, verbose=False
        )
        nodes = _load_nodes(nodes_path)
        assert nodes == ["YWG"]
        matrix = load_npz(matrix_path)
        assert matrix.shape == (1, 1)
        assert matrix.nnz == 0


# ---------------------------------------------------------------------------
# Symmetric matrix
# ---------------------------------------------------------------------------


class TestSymmetricMatrix:

    def test_output_filenames_symmetric(self, public_dir):
        """Symmetric outputs use the ``_sym`` suffix."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=True, verbose=False
        )
        assert matrix_path.endswith("adjacency_matrix_pax_sym.npz")
        assert nodes_path.endswith("nodes_pax_sym.txt")

    def test_symmetric_adds_reverse_edge(self, public_dir):
        """A->B listed once yields both A->B and B->A in symmetric mode."""
        _write_connections(
            public_dir,
            [
                {"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"},
            ],
        )
        matrix_path, nodes_path = create_outbound_adjacency_matrix(
            symmetric=True, verbose=False
        )
        matrix = load_npz(matrix_path)
        nodes = _load_nodes(nodes_path)
        a, b = nodes.index("AAA"), nodes.index("BBB")
        assert matrix[a, b] == 1
        assert matrix[b, a] == 1, "Reverse edge should be present in symmetric mode"

    def test_symmetric_matrix_equals_transpose(self, public_dir):
        """M == M.T for every entry."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 2, "outlinks": "YYZ YVR"},
                {"origin": "YYZ", "nb_outlinks": 1, "outlinks": "YVR"},
            ],
        )
        matrix_path, _ = create_outbound_adjacency_matrix(symmetric=True, verbose=False)
        M = load_npz(matrix_path).toarray()
        assert np.array_equal(M, M.T)

    def test_symmetric_nnz_ge_directed(self, public_dir):
        """Symmetric matrix has at least as many non-zeros as the directed one."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 2, "outlinks": "YYZ YVR"},
                {"origin": "YYZ", "nb_outlinks": 1, "outlinks": "YVR"},
            ],
        )
        mat_dir, _ = create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        mat_sym, _ = create_outbound_adjacency_matrix(symmetric=True, verbose=False)
        assert load_npz(mat_sym).nnz >= load_npz(mat_dir).nnz


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


class TestCsvExport:

    def test_csv_not_written_by_default(self, public_dir):
        """Dense CSV is NOT written unless ``export_csv=True``."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        assert not (public_dir / "adjacency_matrix_pax.csv").exists()

    def test_csv_written_when_requested(self, public_dir):
        """Dense CSV IS written when ``export_csv=True``."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        create_outbound_adjacency_matrix(
            symmetric=False, export_csv=True, verbose=False
        )
        assert (public_dir / "adjacency_matrix_pax.csv").exists()

    def test_csv_has_iata_row_and_column_labels(self, public_dir):
        """Dense CSV uses IATA codes as both row index and column headers."""
        _write_connections(
            public_dir,
            [
                {"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"},
            ],
        )
        create_outbound_adjacency_matrix(
            symmetric=False, export_csv=True, verbose=False
        )
        df = pd.read_csv(public_dir / "adjacency_matrix_pax.csv", index_col=0)
        assert "YWG" in df.index
        assert "YYZ" in df.columns
