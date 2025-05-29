import json

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    extract_airlines_from_airport,
    extract_destinations_from_airport,
    extract_airlines_destinations_from_airport
)

if __name__ == "__main__":
    # Set the airport we want to play with.
    test_IATA = "YQT"  # Thunder Bay Airport, Canada

    # Example: get information by first grabbing a wikipedia link for an airport using its IATA code
    test_link = get_wikipedia_airport_page_link(test_IATA, verbose=True)
    print(f"Wikipedia link for {test_IATA}: {test_link}")

    # Example: Extract airport information
    if test_link:
        airport_details = extract_airport_information(link=test_link)
        print("Airport details:")
        print(json.dumps(airport_details, indent=2, ensure_ascii=False))


    # Example: Extract airlines and destinations
    # if test_link:
    #     airlines = extract_airlines_from_airport(test_link)
    #     print(f"Airlines at {test_IATA}: {sorted(list(airlines))}")

    #     destinations = extract_destinations_from_airport(test_link)
    #     print(f"Destinations at {test_IATA}: {sorted(list(destinations))}")

    #     airlines_dests = extract_airlines_destinations_from_airport(test_link)
    #     # Convert sets to lists for pretty printing
    #     airlines_dests_serializable = {k: sorted(list(v)) for k, v in airlines_dests.items()}
    #     print(f"Airlines/Destinations at {test_IATA}: {json.dumps(airlines_dests_serializable, indent=2, ensure_ascii=False)}")

    # Get information using a IATA code directly
    airport_details = extract_airport_information(identifier=test_IATA, verbose=True)    