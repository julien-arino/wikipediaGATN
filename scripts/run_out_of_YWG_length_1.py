"""
Test script that crawls exactly one level out from YWG (Winnipeg), explicitly verifying handling of known tricky URLs like MSP and YUL.
"""

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
)

from wikipediaGATN.wikipedia_network_level import (
    clean_output_directory,
    iterate_search_until_distance_N,
)

if __name__ == "__main__":
    # Define verbosity
    verbose = True
    # Example: Get Wikipedia link for an airport, which we use as seed later
    test_IATA = "YWG"
    test_link = get_wikipedia_airport_page_link(test_IATA, verbose=verbose)

    # Start clean: wipe everything in the output directory
    clean_output_directory(verbose=verbose)

    # Now run for a distance of 1
    print("Running for a distance of 1...")
    iterate_search_until_distance_N(
        seed_iata=test_IATA, dist=1, delay=0.5, verbose=verbose
    )
