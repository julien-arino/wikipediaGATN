

from wikipediaGATN.result_processing import (
    check_duplicated_iata_codes,
    export_all_airport_data,
)

if __name__ == "__main__":
    # Check for duplicated iata files with different distances from seed iata
    check_duplicated_iata_codes(verbose=True)
    # Export the information of all airports to a csv file
    export_all_airport_data()
