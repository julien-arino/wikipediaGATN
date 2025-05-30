def create_outbound_adjacency_matrix(symmetric=False, verbose=False):
    """
    Create a sparse adjacency matrix of outbound airport connections using the outbound_connections.csv file.

    Each airport is a node, and edges represent outbound links (flights) to other airports.

    Parameters:
    - symmetric (bool): If True, assumes all links are bidirectional.
        Useful because data from small airports is often incomplete.
    - verbose (bool): If True, prints status updates.

    Outputs:
    - adjacency_matrix.npz: sparse matrix of connections (1 for a connection, 0 otherwise)
    - nodes.txt: list of IATA codes, one per line, ordered to match matrix rows/columns
    """
    import pandas as pd
    import numpy as np
    from scipy.sparse import csr_matrix, save_npz
    import os
    from .paths import PUBLIC_DATA_DIR

    # Input CSV with outbound connection data
    input_file = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")
    output_matrix = os.path.join(PUBLIC_DATA_DIR, "adjacency_matrix.npz")
    output_nodes = os.path.join(PUBLIC_DATA_DIR, "nodes.txt")

    # Load the connection data
    df = pd.read_csv(input_file)

    # Create a sorted list of all unique IATA codes from both origin and destination columns
    # Note: destinations are in a space-separated string, so we split and flatten
    # Fill missing outlinks with empty strings to avoid errors
    iata_codes = sorted(
        set(df["origin"]).union(*df["outlinks"].fillna("").str.split())
    )

    # Map each IATA code to an index in the matrix
    iata_to_idx = {code: i for i, code in enumerate(iata_codes)}

    # Initialize row and column indices for matrix construction
    rows, cols = [], []

    # Loop over each row in the outbound connections data
    for _, row in df.iterrows():
        origin = row["origin"]
        origin_idx = iata_to_idx.get(origin)
        if origin_idx is None:
            continue

        # Get all destination airport codes from the outlinks column
        destinations = str(row["outlinks"]).split()  # Ensure it's a string before splitting
        for dest in destinations:
            dest_idx = iata_to_idx.get(dest)
            if dest_idx is not None:
                # Add link origin -> destination
                rows.append(origin_idx)
                cols.append(dest_idx)

                if symmetric:
                    # Also add link destination -> origin (to make it symmetric)
                    rows.append(dest_idx)
                    cols.append(origin_idx)

    # All edges have value 1 (indicating a connection exists)
    data = np.ones(len(rows), dtype=np.uint8)

    # Create a sparse adjacency matrix in CSR format
    matrix = csr_matrix((data, (rows, cols)), shape=(len(iata_codes), len(iata_codes)))

    # Save the matrix to disk
    save_npz(output_matrix, matrix)

    # Save the list of node IATA codes in order corresponding to the matrix
    with open(output_nodes, "w", encoding="utf-8") as f:
        for code in iata_codes:
            f.write(code + "\n")

    if verbose:
        print(f"Saved adjacency matrix to {output_matrix}")
        print(f"Saved IATA node list to {output_nodes}")

if __name__ == "__main__":
    from .paths import PUBLIC_DATA_DIR
    create_outbound_adjacency_matrix(symmetric=False, verbose=True)
