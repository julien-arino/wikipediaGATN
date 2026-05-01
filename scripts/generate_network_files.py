"""
Orchestrates the full GATN generation pipeline.

This script rebuilds the global connection lists, adjacency matrices, and 
graph files (GraphML, GEXF, DOT) for both Passenger and Cargo networks.
It also performs a two-pass IATA extraction to resolve any missing destination codes.
"""

from wikipediaGATN.result_processing_network import _run_pipeline

if __name__ == "__main__":
    _run_pipeline()
