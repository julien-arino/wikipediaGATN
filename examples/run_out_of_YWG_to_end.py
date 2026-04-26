

from wikipediaGATN.wikipedia_network_level import (
    clean_output_directory,
    iterate_search_until_empty,
)

if __name__ == "__main__":
    # Start clean
    clean_output_directory(verbose=True)

    # Run the search from YWG to the end
    test_IATA = "YWG"
    iterate_search_until_empty(test_IATA, delay=0.5, verbose=True)
