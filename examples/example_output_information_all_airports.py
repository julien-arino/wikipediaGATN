import json

from wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from wikipediaGATN.result_processing import (
    export_all_airport_data
)

if __name__ == "__main__":
    # Example: Export the information of all airports to a csv file
    export_all_airport_data()
