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
try:
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
except ImportError:
    # Handle cases where dependencies are missing during test collection
    create_outbound_connections_list = None
    create_outbound_adjacency_matrix = None
    extract_iata_from_unmapped_destinations = None
    create_manual_mapping_from_scraped_data = None
    export_all_airport_data = None
    check_duplicated_iata_codes = None
    run_two_pass_iata_extraction = None

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
