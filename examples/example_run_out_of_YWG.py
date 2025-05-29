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
    # Example: Get Wikipedia link for an airport, which we use as seed later
    test_IATA = "YWG"
    test_link = get_wikipedia_airport_page_link(test_IATA, verbose=True)

    # Check that the link was found
    if test_link:
        airport_details = extract_airport_information(test_link)
        print("Airport details:")
        print(json.dumps(airport_details, indent=2, ensure_ascii=False))

        # Start clean
        clean_output_directory(levels=[1, 2, 3], verbose=True)
        get_connections_level_N(from_length=0, delay=0.5, verbose=True)
        # get_connections_level_N(from_length=1, delay=0.5, verbose=True)    
        # get_connections_level_N(from_length=2, delay=0.5, verbose=True)    
    