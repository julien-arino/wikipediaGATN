"""
wikipediaGATN: Global Air Transportation Network from Wikipedia

A Python package for deriving the structure of the global air transportation network
(GATN) from information publicly available on Wikipedia.

The package provides tools to:
- Scrape airport information from Wikipedia
- Extract and map airport connections
- Build sparse adjacency matrices of the global air network
- Analyze network structure

For more information, see: https://github.com/jarino/wikipediaGATN
"""

__version__ = "0.1.0"
__author__ = "Julien Arino and Adriana-Stefania Ciupeanu"
__author_email__ = "julien.arino@umanitoba.ca, Adriana-Stefania.Ciupeanu@umanitoba.ca"
__license__ = "MIT"  # TODO: confirm licence before JOSS submission

# Import main public functions
from .connections import create_outbound_connections_list
from .adjacency import create_outbound_adjacency_matrix
from .extract_iata_from_wikipedia import (
    extract_iata_from_unmapped_destinations,
    create_manual_mapping_from_scraped_data,
)
from .result_processing import (
    export_all_airport_data,
    check_duplicated_iata_codes,
    run_two_pass_iata_extraction,
)

__all__ = [
    # Core functions
    "create_outbound_connections_list",
    "create_outbound_adjacency_matrix",
    "extract_iata_from_unmapped_destinations",
    "create_manual_mapping_from_scraped_data",
    # Utility functions
    "export_all_airport_data",
    "check_duplicated_iata_codes",
    "run_two_pass_iata_extraction",
]