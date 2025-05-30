# This tests whether the code works as expected when malformed urls are present:
# out of YWG, there is an issue with MSP and YUL

import json

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
)
from wikipediaGATN.wikipedia_network_level import (
    clean_output_directory,
    get_connections_level_N,
    check_processed_list,
    iterate_search_until_distance_N,
    iterate_search_until_empty,
    continue_existing_search_one_step,
    continue_existing_search_until_empty
)

if __name__ == "__main__":
    # Define the IATA code for the airport we want to start from
    test_IATA = "YWG"
    # Start clean
    clean_output_directory(verbose=True)
    # Find all airports within a distance of 2 from YWG
    iterate_search_until_distance_N(seed_iata=test_IATA, dist=2, delay=0.33, verbose=True)
    