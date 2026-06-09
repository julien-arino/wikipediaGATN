"""
Identifies airports in OurAirports.csv that have scheduled service and a Wikipedia link, 
but are missing from the current GATN database. Then checks if they have active 
Airlines and destinations sections on Wikipedia.
"""

from wikipediaGATN.airport_level_functions import (
    compare_airports_with_ourairports,
    find_active_missing_airports,
)

if __name__ == "__main__":
    print("Step 1: Auditing OurAirports vs Internal Database...")
    raw_missing_csv = compare_airports_with_ourairports()
    
    print("\nStep 2: Filtering for airports with active flight sections on Wikipedia...")
    # This might take a while as it checks live Wikipedia pages
    active_missing_csv = find_active_missing_airports(input_csv=raw_missing_csv, max_workers=10)
    
    print(f"\nDone! Active missing airports list saved to: {active_missing_csv}")
    print("You can now run 'python scripts/scrape_missing_airports.py' to recover them.")
