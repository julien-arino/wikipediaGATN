import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_wikipedia import get_wikipedia_airport_page_html, extract_iata_icao_from_html

def main(iata_code):
    html = get_wikipedia_airport_page_html(iata_code)
    if not html:
        print(f"Could not fetch page for {iata_code}")
        return
    iata, icao = extract_iata_icao_from_html(html)
    print(f"IATA: {iata}")
    print(f"ICAO: {icao}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_extract_iata_icao.py <IATA_CODE>")
    else:
        main(sys.argv[1])

#get_length_1_connections("YWG", clean_output=True)
#get_multi_path_length_connections("YWG", path_length=2, clean_output=True)

if __name__ == "__main__":
    # Example: Get Wikipedia link for an airport
    # test_IATA = "YWG"
    # test_link = get_wikipedia_airport_page_link(test_IATA, verbose=True)
    # print(f"Wikipedia link for {test_IATA}: {test_link}")

    # Example: Extract airport information and save it
    # if test_link:
    #     airport_details = extract_airport_information(test_link)
    #     print("Airport details:")
    #     print(json.dumps(airport_details, indent=2, ensure_ascii=False))
    #     save_airport_info(airport_details, level=0, verbose=True)

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

    # Example: Get connections level N
    # clean_output_directory(levels=[1, 2], verbose=True)
    # get_connections_level_N(from_length=0, delay=0.5, verbose=True)
    # get_connections_level_N(from_length=1, delay=0.5, verbose=True)    
    get_connections_level_N(from_length=2, delay=0.5, verbose=True)    
    