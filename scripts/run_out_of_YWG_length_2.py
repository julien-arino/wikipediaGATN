"""
Test script that crawls two levels out from YWG (Winnipeg) starting from a clean slate.
"""

from wikipediaGATN.wikipedia_network_level import (
    clean_output_directory,
    iterate_search_until_distance_N,
)

if __name__ == "__main__":
    # Define the IATA code for the airport we want to start from
    test_IATA = "YWG"
    # Start clean
    clean_output_directory(verbose=True)
    # Find all airports within a distance of 2 from YWG
    iterate_search_until_distance_N(seed_iata=test_IATA, dist=2, delay=0.33, verbose=True)
