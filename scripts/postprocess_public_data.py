"""
Refreshes the public airport data in-place.

This script scans the existing JSON files in 'data/public/airport_data',
applies metadata improvements (geographic inference, link resolution, etc.),
and regenerates the master 'airports_information.csv'.

It does NOT copy data from the temporary sweep directory.
"""

from wikipediaGATN.result_processing_airports import export_all_airport_data

if __name__ == "__main__":
    print("Post-processing public airport data in-place...")
    # use_new_data=False ensures we process the public folder itself
    export_all_airport_data(use_new_data=False, verbose=True)
    print("\nPublic data refresh complete.")
