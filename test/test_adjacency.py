"""Test adjacency matrix creation"""

from src.wikipediaGATN.result_processing_improved import create_outbound_adjacency_matrix
from src.wikipediaGATN.paths import PUBLIC_DATA_DIR
import os

print("=" * 60)
print("Creating adjacency matrix (non-symmetric)")
print("=" * 60)

try:
    matrix_path, nodes_path = create_outbound_adjacency_matrix(
        symmetric=False,
        verbose=True
    )

    print(f"\n✓ Matrix saved to: {matrix_path}")
    print(f"✓ Nodes saved to: {nodes_path}")

    # Verify the nodes
    with open(nodes_path, 'r') as f:
        nodes = [line.strip() for line in f.readlines()]

    print(f"\nNodes file:")
    print(f"  Total airports: {len(nodes)}")
    print(f"  First 5: {nodes[:5]}")
    print(f"  Last 5: {nodes[-5:]}")

    # Load and check the matrix
    import numpy as np
    from scipy.sparse import load_npz

    matrix = load_npz(matrix_path)
    print(f"\nMatrix properties:")
    print(f"  Shape: {matrix.shape}")
    print(f"  Non-zero entries: {matrix.nnz}")
    print(f"  Density: {matrix.nnz / (matrix.shape[0] * matrix.shape[1]) * 100:.2f}%")

    # Spot check: YWG (should be first alphabetically? or find it)
    if 'YWG' in nodes:
        idx = nodes.index('YWG')
        row = matrix.getrow(idx)
        connections = row.nonzero()[1]
        connected_to = [nodes[i] for i in connections]
        print(f"\n  YWG connects to {len(connections)} airports:")
        print(f"    {connected_to}")

    print("\n✓ Non-symmetric adjacency matrix works!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback

    traceback.print_exc()

# Now test symmetric version
print("\n" + "=" * 60)
print("Creating adjacency matrix (symmetric)")
print("=" * 60)

try:
    matrix_path_sym, nodes_path_sym = create_outbound_adjacency_matrix(
        symmetric=True,
        verbose=True
    )

    print(f"\n✓ Symmetric matrix saved to: {matrix_path_sym}")

    # Compare
    from scipy.sparse import load_npz

    matrix_nonsym = load_npz(os.path.join(PUBLIC_DATA_DIR, "adjacency_matrix.npz"))
    matrix_sym = load_npz(matrix_path_sym)

    print(f"\nComparison:")
    print(f"  Non-symmetric edges: {matrix_nonsym.nnz}")
    print(f"  Symmetric edges: {matrix_sym.nnz}")
    print(f"  Increase: {matrix_sym.nnz - matrix_nonsym.nnz} edges")

    print("\n✓ Symmetric adjacency matrix works!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback

    traceback.print_exc()