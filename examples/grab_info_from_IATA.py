import sys
import json

import mwparserfromhell
import wikitextparser as wtp

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    get_wikipedia_airport_page_wikitext,
    parse_infobox_from_wikitext,
    extract_airlines_destinations_from_wikitext,
    extract_airlines_from_airlines_dest_dict,
    extract_destinations_from_airlines_dest_dict,
    convert_sets_to_lists
)


if __name__ == "__main__":
    # Set the airport we want to play with.
    if len(sys.argv) > 1:
        test_IATA = sys.argv[1]
    else:
        test_IATA = "YWG"

    # Example: get information by first grabbing a wikipedia link for an airport using its IATA code
    test_link = get_wikipedia_airport_page_link(test_IATA, verbose=False)
    # print(f"Wikipedia link for {test_IATA}: {test_link}")

    # Example: Extract airport information
    if test_link:
        airport_details = extract_airport_information(link=test_link)
        print("Airport details:")
        airport_details = convert_sets_to_lists(airport_details)  # <-- Add this line
        print(json.dumps(airport_details, indent=2, ensure_ascii=False))


    # Go the wikitext way
    if test_link:
        wikitext = get_wikipedia_airport_page_wikitext(test_link, verbose=False)
        print("Raw wikitext data:")
        print(wikitext)

        infobox = parse_infobox_from_wikitext(wikitext, verbose=False)
        print("\n\nParsed infobox from wikitext:")
        print(json.dumps(infobox, indent=2, ensure_ascii=False))

        # Get airlines and destinations from wikitext
        airlines_dest = extract_airlines_destinations_from_wikitext(wikitext, verbose=False)
        print("\n\nAirlines and destinations from wikitext:")
        print(json.dumps(airlines_dest, indent=2, ensure_ascii=False))
        airlines = extract_airlines_from_airlines_dest_dict(airlines_dest)
        dests = extract_destinations_from_airlines_dest_dict(airlines_dest)
        print("\nAirlines from wikitext:")
        print(json.dumps(airlines, indent=2, ensure_ascii=False))
        print("\nDestinations from wikitext:")
        dests  = convert_sets_to_lists(dests)
        print(json.dumps(dests, indent=2, ensure_ascii=False))