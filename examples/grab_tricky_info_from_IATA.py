import json

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    extract_airlines_from_airport,
    extract_destinations_from_airport,
    extract_airlines_destinations_from_airport,
    extract_iata_icao
)

if __name__ == "__main__":
    # Set the airport we want to play with.
    test_IATA = "YWG"  # Winnipeg James Armstrong Richardson International Airport

    # Get the list of destinations
    dests = extract_destinations_from_airport(identifier=test_IATA, verbose=True)
    
    # Find the Minneapolis-Saint Paul International Airport link
    msp_link = None
    for title, url in dests:
        if "Minneapolis-Saint Paul International Airport" in title:
            msp_title = title
            msp_link = url
            break
    print("MSP Wikipedia link:", msp_link)

    # Get information using the link
    print("\nExtract information for MSP using the link...")
    airport_details = extract_airport_information(link=msp_link, verbose=True)    

    # Get information using the name
    print("\nGet link for MSP using the airport name, then use the link...")
    msp_link = get_wikipedia_airport_page_link(identifier=msp_title, verbose=True)
    airport_details = extract_airport_information(link=msp_link, verbose=True)

    # Get information using the IATA code
    print("\nGet information using the IATA code...")
    airport_details = extract_airport_information(identifier="MSP", verbose=True)    