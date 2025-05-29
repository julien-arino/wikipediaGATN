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
    # Run catchup for the current N-1 level
    continue_existing_search_one_step(delay=0.33, verbose=True)
    