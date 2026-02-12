"""
Generate sparse adjacency matrices from airport connections.

This module creates sparse matrix representations of the airport network
from outbound connection data.
"""

import os
import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix, save_npz

from .paths import PUBLIC_DATA_DIR


def create_outbound_adjacency_matrix(symmetric=False, verbose=False):
    """
    Create a sparse adjacency matrix of outbound airport connections.

    Reads airport connections from outbound_connections.csv and creates a sparse
    adjacency matrix where each airport is a node and edges represent direct
    outbound connections. Can optionally create a symmetric matrix to account
    for incomplete destination data from smaller airports.

    Parameters
    ----------
    symmetric : bool, optional
        If True, assumes all links are bidirectional. Use this option when
        destination data is incomplete (small airports may not list all their
        outbound flights on Wikipedia). Default is False (directed graph).
    verbose : bool, optional
        If True, prints status messages about processing. Default is False.

    Returns
    -------
    tuple of (str, str)
        Paths to the output files:
        - First element: path to sparse matrix file (.npz format)
        - Second element: path to node list file (.txt format)

    Output Files
    -----------
    When symmetric=False:
    - adjacency_matrix.npz: Sparse adjacency matrix (1 = connection exists, 0 otherwise)
    - nodes.txt: Sorted list of IATA codes (one per line)
    - adjacency_matrix.csv: Dense matrix version with IATA labels (for inspection)

    When symmetric=True:
    - adjacency_matrix_sym.npz: Sparse adjacency matrix with bidirectional links
    - nodes_sym.txt: Sorted list of IATA codes
    - adjacency_matrix_sym.csv: Dense matrix version with IATA labels

    Notes
    -----
    The matrix is stored in CSR (Compressed Sparse Row) format for efficient
    storage and computation. The node list ensures row/column indices match
    the IATA codes in alphabetical order.

    When symmetric=True, if an edge from airport A to airport B exists but the
    reverse edge does not, both A→B and B→A are added to the matrix. This is
    useful for network analysis when working with incomplete data.

    Examples
    --------
    >>> matrix_path, nodes_path = create_outbound_adjacency_matrix(symmetric=False)
    >>> print(f"Matrix saved to: {matrix_path}")
    >>> 
    >>> # Load the matrix and nodes
    >>> from scipy.sparse import load_npz
    >>> matrix = load_npz(matrix_path)
    >>> with open(nodes_path) as f:
    ...     nodes = [line.strip() for line in f]
    >>> print(f"Matrix shape: {matrix.shape}, Airports: {len(nodes)}")
    """

    # Load outbound connection data
    input_file = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    if not os.path.exists(input_file):
        raise FileNotFoundError(
            f"Input file not found: {input_file}\n"
            f"Run create_outbound_connections_list() first to generate outbound_connections.csv"
        )

    df = pd.read_csv(input_file)

    if verbose:
        print(f"Loaded {len(df)} airport connections from {input_file}")

    # ========== Build sorted list of all unique airports ==========

    all_origins = set(df["origin"])
    all_destinations = set()

    # Extract all destination codes from outlinks column
    for outlinks_str in df["outlinks"].fillna(""):
        if outlinks_str.strip():
            destinations = outlinks_str.split()
            all_destinations.update(destinations)

    # Create sorted list of all unique airports
    iata_codes = sorted(all_origins.union(all_destinations))

    # Create mapping from IATA code to matrix index
    iata_to_idx = {code: i for i, code in enumerate(iata_codes)}

    if verbose:
        print(f"Found {len(iata_codes)} unique airports")
        print(f"Origins: {len(all_origins)}, Destinations: {len(all_destinations)}")

    # ========== Build edge lists for sparse matrix ==========

    rows, cols = [], []

    # Process each airport's outbound connections
    for _, row in df.iterrows():
        origin = row["origin"]
        origin_idx = iata_to_idx.get(origin)

        if origin_idx is None:
            if verbose:
                print(f"Warning: Origin '{origin}' not found in IATA mapping")
            continue

        # Extract destination airports
        outlinks_str = str(row["outlinks"]) if pd.notna(row["outlinks"]) else ""
        if not outlinks_str.strip():
            continue  # Skip if no destinations

        # Add edge for each destination
        for dest in outlinks_str.split():
            dest_idx = iata_to_idx.get(dest)
            if dest_idx is not None:
                rows.append(origin_idx)
                cols.append(dest_idx)

                # Add reverse edge if symmetric
                if symmetric:
                    rows.append(dest_idx)
                    cols.append(origin_idx)
            elif verbose:
                print(f"Warning: Destination '{dest}' not found in IATA mapping")

    if verbose:
        edges_before_dedup = len(rows)
        print(f"Created {edges_before_dedup} directed edges" +
              (" (including reverse edges)" if symmetric else ""))

    # ========== Remove duplicate edges if symmetric ==========

    if symmetric and rows:
        edges = set(zip(rows, cols))
        rows, cols = zip(*edges) if edges else ([], [])
        rows, cols = list(rows), list(cols)

        if verbose:
            print(f"After removing duplicates: {len(rows)} edges")

    # ========== Create sparse matrix ==========

    data = np.ones(len(rows), dtype=np.uint8)
    matrix = csr_matrix(
        (data, (rows, cols)),
        shape=(len(iata_codes), len(iata_codes))
    )

    # ========== Define output filenames ==========

    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)

    suffix = "_sym" if symmetric else ""
    output_matrix = os.path.join(PUBLIC_DATA_DIR, f"adjacency_matrix{suffix}.npz")
    output_nodes = os.path.join(PUBLIC_DATA_DIR, f"nodes{suffix}.txt")
    output_csv = os.path.join(PUBLIC_DATA_DIR, f"adjacency_matrix{suffix}.csv")

    # ========== Save outputs ==========

    # Save sparse matrix
    save_npz(output_matrix, matrix)

    # Save node list (IATA codes in order matching matrix rows/columns)
    with open(output_nodes, "w", encoding="utf-8") as f:
        for code in iata_codes:
            f.write(code + "\n")

    # Save dense matrix as CSV for inspection
    dense_matrix = matrix.toarray()
    df_matrix = pd.DataFrame(dense_matrix, index=iata_codes, columns=iata_codes)
    df_matrix.to_csv(output_csv)

    if verbose:
        print(f"\nSaved sparse matrix to {output_matrix}")
        print(f"Matrix shape: {matrix.shape}")
        print(f"Non-zero entries: {matrix.nnz}")
        density = matrix.nnz / (matrix.shape[0] * matrix.shape[1])
        print(f"Density: {density:.6f}")
        print(f"Saved IATA node list to {output_nodes}")
        print(f"Saved dense matrix to {output_csv}")
        print(f"\nAbsolute paths:")
        print(f"  Matrix: {os.path.abspath(output_matrix)}")
        print(f"  Nodes: {os.path.abspath(output_nodes)}")

    return output_matrix, output_nodes
