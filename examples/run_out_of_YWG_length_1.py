# This tests whether the code works as expected when malformed urls are present:
# out of YWG, there is an issue with MSP and YUL. Running length 1 should have them
# both present in the results.

import json

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    get_wikipedia_airport_page_wikitext,
    parse_infobox_from_wikitext
)
from wikipediaGATN.wikipedia_network_level import (
    clean_output_directory,
    get_connections_level_N,
    check_processed_list,
    iterate_search_until_distance_N,
    iterate_search_until_empty,
    continue_existing_search_one_step,
    continue_existing_search_until_empty,
    convert_sets_to_lists
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
    iterate_search_until_distance_N(seed_iata=test_IATA, dist=1, delay=0.5, verbose=verbose)

    airport_info = convert_sets_to_lists(airport_info)
    json.dump(airport_info, f, ensure_ascii=False, indent=2)