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
# Network graph exports (GraphML / GEXF / DOT)
# ---------------------------------------------------------------------------


class TestNetworkExports:

    def test_directed_network_files_unsuffixed(self, public_dir):
        """Directed build writes the unsuffixed graph files."""
        _write_connections(
            public_dir,
            [{"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"}],
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        assert (public_dir / "global-air-pax-network.graphml").exists()
        assert (public_dir / "global-air-pax-network.gexf").exists()
        assert (public_dir / "global-air-pax-network.dot").exists()

    def test_symmetric_network_files_get_sym_suffix(self, public_dir):
        """Symmetric build writes ``_sym`` graph files for every format."""
        _write_connections(
            public_dir,
            [{"origin": "YWG", "nb_outlinks": 1, "outlinks": "YYZ"}],
        )
        create_outbound_adjacency_matrix(symmetric=True, verbose=False)
        assert (public_dir / "global-air-pax-network_sym.graphml").exists()
        assert (public_dir / "global-air-pax-network_sym.gexf").exists()
        assert (public_dir / "global-air-pax-network_sym.dot").exists()

    def test_symmetric_does_not_overwrite_directed_graphs(self, public_dir):
        """A symmetric build must not clobber the directed graph files.

        Regression test: the ``_sym`` suffix used to be applied only to the
        ``.npz``/``.txt`` outputs, so the symmetric network export overwrote the
        directed ``.graphml``/``.gexf``/``.dot`` in place.
        """
        import networkx as nx

        _write_connections(
            public_dir,
            [{"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"}],
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        create_outbound_adjacency_matrix(symmetric=True, verbose=False)

        directed = nx.read_graphml(public_dir / "global-air-pax-network.graphml")
        symmetric = nx.read_graphml(public_dir / "global-air-pax-network_sym.graphml")
        # The directed graph still has the single directed edge; the symmetric
        # one has both directions.
        assert directed.number_of_edges() == 1
        assert symmetric.number_of_edges() == 2

    def test_node_code_type_attribute(self, public_dir):
        """Each exported node carries a ``code_type`` of IATA (3) or ICAO (4)."""
        import networkx as nx

        _write_connections(
            public_dir,
            [{"origin": "YWG", "nb_outlinks": 1, "outlinks": "CYAL"}],
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        G = nx.read_graphml(public_dir / "global-air-pax-network.graphml")
        assert G.nodes["YWG"]["code_type"] == "IATA"
        assert G.nodes["CYAL"]["code_type"] == "ICAO"

    def test_airlines_reliable_node_attribute(self, public_dir):
        """Nodes flagged ``airlines_nlp_fallback`` export ``airlines_reliable=False``."""
        import json

        import networkx as nx

        _write_connections(
            public_dir,
            [
                {"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"},
                {"origin": "BBB", "nb_outlinks": 1, "outlinks": "AAA"},
            ],
        )
        airport_data = public_dir / "airport_data"
        airport_data.mkdir()
        (airport_data / "AAA.json").write_text(
            json.dumps({"iata": "AAA", "airlines_nlp_fallback": True}),
            encoding="utf-8",
        )
        (airport_data / "BBB.json").write_text(
            json.dumps({"iata": "BBB", "airlines_nlp_fallback": False}),
            encoding="utf-8",
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        G = nx.read_graphml(public_dir / "global-air-pax-network.graphml")
        assert G.nodes["AAA"]["airlines_reliable"] is False
        assert G.nodes["BBB"]["airlines_reliable"] is True

    def test_seasonal_edge_attribute(self, public_dir):
        """The ``seasonal`` column becomes a per-edge ``seasonal`` graph attribute."""
        import networkx as nx

        csv_path = public_dir / "global-air-pax-network.csv"
        pd.DataFrame(
            [
                {
                    "origin": "AAA",
                    "nb_outlinks": 2,
                    "outlinks": "BBB CCC",
                    "weights": "1 1",
                    "seasonal": "1 0",
                }
            ]
        ).to_csv(csv_path, index=False)
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        G = nx.read_graphml(public_dir / "global-air-pax-network.graphml")
        assert G["AAA"]["BBB"]["seasonal"] == 1
        assert G["AAA"]["CCC"]["seasonal"] == 0

    def test_seasonal_column_absent_defaults_to_zero(self, public_dir):
        """With no seasonal column, every edge is year-round (seasonal=0)."""
        import networkx as nx

        _write_connections(
            public_dir,
            [{"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"}],
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False)
        G = nx.read_graphml(public_dir / "global-air-pax-network.graphml")
        assert G["AAA"]["BBB"]["seasonal"] == 0

    def test_airlines_reliable_absent_from_cargo_graph(self, public_dir):
        """The reliability flag is passenger-only (cargo is never fallback)."""
        import json

        import networkx as nx

        csv_path = public_dir / "global-air-cargo-network.csv"
        pd.DataFrame(
            [{"origin": "AAA", "nb_outlinks": 1, "outlinks": "BBB"}],
            columns=["origin", "nb_outlinks", "outlinks"],
        ).to_csv(csv_path, index=False)
        airport_data = public_dir / "airport_data"
        airport_data.mkdir()
        (airport_data / "AAA.json").write_text(
            json.dumps({"iata": "AAA", "airlines_nlp_fallback": True}),
            encoding="utf-8",
        )
        create_outbound_adjacency_matrix(symmetric=False, verbose=False, is_cargo=True)
        G = nx.read_graphml(public_dir / "global-air-cargo-network.graphml")
        assert "airlines_reliable" not in G.nodes["AAA"]


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
