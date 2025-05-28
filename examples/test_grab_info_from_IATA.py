import json

from wikipediaGATN.airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    extract_airlines_from_airport,
    extract_destinations_from_airport,
    extract_airlines_destinations_from_airport
)

if __name__ == "__main__":
    # Example: Get Wikipedia link for an airport
    test_IATA = "YWG"
    test_link = get_wikipedia_airport_page_link(test_IATA, verbose=True)
    print(f"Wikipedia link for {test_IATA}: {test_link}")

    # Example: Extract airport information
    if test_link:
        airport_details = extract_airport_information(test_link)
        print("Airport details:")
        print(json.dumps(airport_details, indent=2, ensure_ascii=False))

    # Example: Extract airlines and destinations
    if test_link:
        airlines = extract_airlines_from_airport(test_link)
        print(f"Airlines at {test_IATA}: {sorted(list(airlines))}")

        destinations = extract_destinations_from_airport(test_link)
        print(f"Destinations at {test_IATA}: {sorted(list(destinations))}")

        airlines_dests = extract_airlines_destinations_from_airport(test_link)
        # Convert sets to lists for pretty printing
        airlines_dests_serializable = {k: sorted(list(v)) for k, v in airlines_dests.items()}
        print(f"Airlines/Destinations at {test_IATA}: {json.dumps(airlines_dests_serializable, indent=2, ensure_ascii=False)}")

    # Example: Get connections level N
    # clean_output_directory(levels=[1, 2], verbose=True)
    # get_connections_level_N(from_length=0, delay=0.5, verbose=True)
    # get_connections_level_N(from_length=1, delay=0.5, verbose=True)    
    # get_connections_level_N(from_length=2, delay=0.5, verbose=True)    
    