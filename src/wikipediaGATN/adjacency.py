"""
Generate sparse adjacency matrices from airport connections.

This module creates sparse matrix representations of the airport network
from outbound connection data.
"""

import os
import re
import warnings

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz

from .paths import PUBLIC_DATA_DIR

# Pre-compiled pattern for validating IATA codes (3 uppercase letters)
_IATA_RE = re.compile(r"^[A-Z]{3}$")


def _is_valid_iata(code: str) -> bool:
    """Return True if *code* is a well-formed 3-letter IATA code."""
    return bool(_IATA_RE.match(code))


def create_outbound_adjacency_matrix(
    symmetric: bool = False,
    export_csv: bool = False,
    verbose: bool = False,
) -> tuple:
    """
    Create a sparse adjacency matrix of outbound airport connections.

    Reads airport connections from ``outbound_connections.csv`` and creates a
    sparse adjacency matrix where each airport is a node and edges represent
    direct outbound connections.  Can optionally create a symmetric matrix to
    account for incomplete destination data from smaller airports.

    Parameters
    ----------
    symmetric : bool, optional
        If True, assumes all links are bidirectional.  Use this option when
        destination data is incomplete (small airports may not list all their
        outbound flights on Wikipedia).  Default is False (directed graph).
    export_csv : bool, optional
        If True, also writes a dense ``adjacency_matrix[_sym].csv`` alongside
        the ``.npz`` file.  This file can be very large for global-scale
        networks (≥ 4 000 nodes → > 100 MB), so it is **off by default** and
        intended only for small-scale inspection.  Default is False.
    verbose : bool, optional
        If True, prints status messages about processing.  Default is False.

    Returns
    -------
    tuple of (str, str)
        Paths to the output files:

        - ``output_matrix`` – path to the sparse matrix file (``.npz``).
        - ``output_nodes``  – path to the node-list file (``.txt``).

    Output files
    ------------
    When ``symmetric=False``:

    * ``adjacency_matrix.npz``  – sparse adjacency matrix
      (1 = connection exists, 0 otherwise).
    * ``nodes.txt``             – sorted list of IATA codes (one per line).
    * ``adjacency_matrix.csv``  – dense matrix with IATA labels
      *(only written when* ``export_csv=True`` *)*.

    When ``symmetric=True``:

    * ``adjacency_matrix_sym.npz``
    * ``nodes_sym.txt``
    * ``adjacency_matrix_sym.csv``  *(only when* ``export_csv=True`` *)*.

    Notes
    -----
    The matrix is stored in CSR (Compressed Sparse Row) format for efficient
    storage and computation.  The node list ensures row/column indices match
    the IATA codes in alphabetical order.

    When ``symmetric=True``, if an edge A → B exists but B → A does not, both
    directions are added.  This is useful when working with data that under-
    reports small-airport outbound routes.

    Malformed IATA tokens (not matching ``[A-Z]{3}``) and self-loops are
    silently skipped with a warning.

    Examples
    --------
    >>> # doctest: +SKIP
    >>> matrix_path, nodes_path = create_outbound_adjacency_matrix()
    >>> from scipy.sparse import load_npz
    >>> matrix = load_npz(matrix_path)
    >>> with open(nodes_path) as f:
    ...     nodes = [line.strip() for line in f]
    >>> print(f"Matrix shape: {matrix.shape}, Airports: {len(nodes)}")
    """

    # ------------------------------------------------------------------
    # Load outbound connection data
    # ------------------------------------------------------------------
    input_file = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    if not os.path.exists(input_file):
        raise FileNotFoundError(
            f"Input file not found: {input_file}\n"
            "Run create_outbound_connections_list() first to generate "
            "outbound_connections.csv"
        )

    df = pd.read_csv(input_file)

    if verbose:
        print(f"Loaded {len(df)} airport records from {input_file}")

    # ------------------------------------------------------------------
    # Validate & clean the origin column
    # ------------------------------------------------------------------
    # Drop rows with missing or malformed origin codes
    n_before = len(df)
    df = df.dropna(subset=["origin"])
    df = df[df["origin"].apply(lambda x: _is_valid_iata(str(x).strip()))]

    if len(df) < n_before and verbose:
        print(
            f"Dropped {n_before - len(df)} rows with missing/malformed origin codes"
        )

    if df.empty:
        raise ValueError(
            "No valid airport records found after filtering.  "
            "Check outbound_connections.csv for correct IATA codes."
        )

    # ------------------------------------------------------------------
    # Build sorted list of all unique airports
    # ------------------------------------------------------------------
    all_origins = set(df["origin"].str.strip())

    # Vectorised extraction of all destination tokens
    all_dest_tokens: set = set()
    for outlinks_str in df["outlinks"].fillna(""):
        for token in str(outlinks_str).split():
            token = token.strip()
            if _is_valid_iata(token):
                all_dest_tokens.add(token)
            else:
                warnings.warn(
                    f"Skipping malformed destination token: {token!r}",
                    UserWarning,
                    stacklevel=2,
                )

    iata_codes = sorted(all_origins | all_dest_tokens)

    if not iata_codes:
        raise ValueError("No valid IATA codes found in outbound_connections.csv.")

    iata_to_idx: dict = {code: i for i, code in enumerate(iata_codes)}

    if verbose:
        print(f"Unique airports: {len(iata_codes)}")
        print(
            f"  Origins: {len(all_origins)}  |  "
            f"Destinations: {len(all_dest_tokens)}"
        )

    # ------------------------------------------------------------------
    # Build edge lists (vectorised where possible)
    # ------------------------------------------------------------------
    rows_list: list = []
    cols_list: list = []
    skipped_self_loops = 0
    skipped_unknown_dest = 0

    for _, row in df.iterrows():
        origin = row["origin"].strip()
        origin_idx = iata_to_idx[origin]  # always present after filter above

        outlinks_str = str(row["outlinks"]) if pd.notna(row["outlinks"]) else ""
        if not outlinks_str.strip():
            continue

        for dest in outlinks_str.split():
            dest = dest.strip()
            if not _is_valid_iata(dest):
                continue  # already warned during token collection

            dest_idx = iata_to_idx.get(dest)
            if dest_idx is None:
                skipped_unknown_dest += 1
                continue

            # Drop self-loops
            if dest_idx == origin_idx:
                skipped_self_loops += 1
                continue

            rows_list.append(origin_idx)
            cols_list.append(dest_idx)

            if symmetric:
                rows_list.append(dest_idx)
                cols_list.append(origin_idx)

    if verbose:
        print(f"Raw directed edges collected: {len(rows_list)}")
        if skipped_self_loops:
            print(f"  Self-loops removed: {skipped_self_loops}")
        if skipped_unknown_dest:
            print(f"  Unknown destinations skipped: {skipped_unknown_dest}")

    # ------------------------------------------------------------------
    # Deduplicate edges
    # ------------------------------------------------------------------
    # Always deduplicate: csr_matrix *sums* duplicate (row, col) pairs, which
    # would produce values > 1 for any duplicated edges in the CSV.
    if rows_list:
        unique_edges = list(set(zip(rows_list, cols_list)))
        rows_arr, cols_arr = zip(*unique_edges)
    else:
        rows_arr, cols_arr = [], []

    if verbose and symmetric:
        print(f"Edges after deduplication: {len(rows_arr)}")

    # ------------------------------------------------------------------
    # Create sparse matrix
    # ------------------------------------------------------------------
    n = len(iata_codes)
    data = np.ones(len(rows_arr), dtype=np.uint8)
    matrix = csr_matrix((data, (rows_arr, cols_arr)), shape=(n, n))

    # Verify no stray values > 1 survived (sanity check)
    if matrix.data.max() > 1:  # pragma: no cover
        warnings.warn(
            "Adjacency matrix contains entries > 1 after deduplication. "
            "Check outbound_connections.csv for duplicate rows.",
            UserWarning,
            stacklevel=2,
        )
        matrix.data[:] = 1

    # ------------------------------------------------------------------
    # Define output filenames
    # ------------------------------------------------------------------
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)

    suffix = "_sym" if symmetric else ""
    output_matrix = os.path.join(PUBLIC_DATA_DIR, f"adjacency_matrix{suffix}.npz")
    output_nodes  = os.path.join(PUBLIC_DATA_DIR, f"nodes{suffix}.txt")
    output_csv    = os.path.join(PUBLIC_DATA_DIR, f"adjacency_matrix{suffix}.csv")

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------
    save_npz(output_matrix, matrix)

    with open(output_nodes, "w", encoding="utf-8") as f:
        f.write("\n".join(iata_codes) + "\n")

    if export_csv:
        if n > 5_000:
            warnings.warn(
                f"export_csv=True with {n} nodes will write a "
                f"{n * n:,}-cell CSV (≈ {n * n // 1_000_000} MB). "
                "This may be very slow.",
                UserWarning,
                stacklevel=2,
            )
        dense_matrix = matrix.toarray()
        df_matrix = pd.DataFrame(dense_matrix, index=iata_codes, columns=iata_codes)
        df_matrix.to_csv(output_csv)
        if verbose:
            print(f"Saved dense matrix CSV to {output_csv}")

    if verbose:
        print(f"\nSaved sparse matrix : {os.path.abspath(output_matrix)}")
        print(f"Saved node list      : {os.path.abspath(output_nodes)}")
        print(f"Matrix shape         : {matrix.shape}")
        print(f"Non-zero entries     : {matrix.nnz:,}")
        if n > 0:
            density = matrix.nnz / (n * n)
            print(f"Density              : {density:.6f}")

    return output_matrix, output_nodes