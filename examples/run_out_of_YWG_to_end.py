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
    # Start clean
    clean_output_directory(verbose=True)

    # Run the search from YWG to the end
    test_IATA = "YWG"
    iterate_search_until_empty(test_IATA, delay=0.5, verbose=True)
    