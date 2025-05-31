def create_outbound_adjacency_matrix(symmetric=False, verbose=False):
    """
    Create a sparse adjacency matrix of outbound airport connections using outbound_connections.csv.

    Each airport is a node in the graph; an edge from node i to j indicates a direct outbound connection.

    Parameters:
    - symmetric (bool): If True, assumes bidirectional links (useful when destination data is incomplete).
    - verbose (bool): If True, prints status updates.

    Outputs:
    - adjacency_matrix(.npz): Sparse matrix file (1 indicates connection, 0 otherwise).
    - nodes.txt: List of IATA codes, one per line, matching the order of rows/columns in the matrix.
    - adjacency_matrix(.csv): Optional dense matrix output with IATA labels (for inspection).
    """
    import pandas as pd
    import numpy as np
    from scipy.sparse import csr_matrix, save_npz
    import os
    from .paths import PUBLIC_DATA_DIR

    # Load outbound connection data from the standard location
    input_file = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    # Define output filenames based on whether the matrix should be symmetric
    if symmetric:
        output_matrix = os.path.join(PUBLIC_DATA_DIR, "adjacency_matrix_sym.npz")
        output_nodes = os.path.join(PUBLIC_DATA_DIR, "nodes_sym.txt")
    else:
        output_matrix = os.path.join(PUBLIC_DATA_DIR, "adjacency_matrix.npz")
        output_nodes = os.path.join(PUBLIC_DATA_DIR, "nodes.txt")

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    df = pd.read_csv(input_file)

    if verbose:
        print(f"Loaded {len(df)} airport connections from {input_file}")

    # Build the set of all unique IATA codes from both origin and destination columns
    all_origins = set(df["origin"])
    all_destinations = set()

    for outlinks_str in df["outlinks"].fillna(""):
        if outlinks_str.strip():
            destinations = outlinks_str.split()
            all_destinations.update(destinations)

    # Final set of unique airports involved
    iata_codes = sorted(all_origins.union(all_destinations))

    # Create index mapping from IATA code to matrix index
    iata_to_idx = {code: i for i, code in enumerate(iata_codes)}

    if verbose:
        print(f"Found {len(iata_codes)} unique airports")
        print(f"Origins: {len(all_origins)}, Destinations: {len(all_destinations)}")

    # Initialize edge index lists for the sparse matrix
    rows, cols = [], []

    # Parse connections row-by-row
    for _, row in df.iterrows():
        origin = row["origin"]
        origin_idx = iata_to_idx.get(origin)

        if origin_idx is None:
            if verbose:
                print(f"Warning: Origin '{origin}' not found in IATA mapping")
            continue

        outlinks_str = str(row["outlinks"]) if pd.notna(row["outlinks"]) else ""
        if not outlinks_str.strip():
            continue  # Skip if no destinations listed

        for dest in outlinks_str.split():
            dest_idx = iata_to_idx.get(dest)
            if dest_idx is not None:
                # Record directed edge: origin → destination
                rows.append(origin_idx)
                cols.append(dest_idx)

                if symmetric:
                    # Add reverse edge: destination → origin
                    rows.append(dest_idx)
                    cols.append(origin_idx)
            elif verbose:
                print(f"Warning: Destination '{dest}' not found in IATA mapping")

    if verbose:
        print(f"Created {len(rows)} directed edges{' (including reverse edges)' if symmetric else ''}")

    # Remove duplicates if bidirectional edges were added
    if symmetric and rows:
        edges = set(zip(rows, cols))  # Remove duplicates
        rows, cols = zip(*edges) if edges else ([], [])
        rows, cols = list(rows), list(cols)

        if verbose:
            print(f"After removing duplicates: {len(rows)} edges")

    # Assign a value of 1 to all edges
    data = np.ones(len(rows), dtype=np.uint8)

    # Construct sparse matrix (CSR format) of shape [n_airports x n_airports]
    matrix = csr_matrix((data, (rows, cols)), shape=(len(iata_codes), len(iata_codes)))

    # Ensure output directory exists
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)

    # Save sparse matrix to .npz file
    save_npz(output_matrix, matrix)

    # Save the list of IATA codes (to match matrix row/column order)
    with open(output_nodes, "w", encoding="utf-8") as f:
        for code in iata_codes:
            f.write(code + "\n")

    # Save matrix as a dense CSV for visual inspection (optional)
    output_csv = output_matrix.replace(".npz", ".csv")
    dense_matrix = matrix.toarray()
    df_matrix = pd.DataFrame(dense_matrix, index=iata_codes, columns=iata_codes)
    df_matrix.to_csv(output_csv)

    if verbose:
        print(f"Saved adjacency matrix to {output_matrix}")
        print(f"Matrix shape: {matrix.shape}")
        print(f"Non-zero entries: {matrix.nnz}")
        print(f"Density: {matrix.nnz / (matrix.shape[0] * matrix.shape[1]):.6f}")
        print(f"Saved IATA node list to {output_nodes}")
        print(f"Absolute paths:")
        print(f"  Matrix: {os.path.abspath(output_matrix)}")
        print(f"  Nodes:  {os.path.abspath(output_nodes)}")

    return output_matrix, output_nodes


if __name__ == "__main__":
    from .paths import PUBLIC_DATA_DIR
    create_outbound_adjacency_matrix(symmetric=False, verbose=True)
