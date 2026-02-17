"""Test with your actual data"""

from src.wikipediaGATN.result_processing_improved import export_all_airport_data, create_outbound_connections_list
from src.wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR
import os

print("="*60)
print("STEP 1: Export all airport data")
print("="*60)

# First, make sure we have data
json_files = [f for f in os.listdir(TEMP_RESULTS_DIR) if f.endswith('.json')]
print(f"Found {len(json_files)} JSON files")

if len(json_files) == 0:
    print("ERROR: No JSON files in data/tmp_results/")
    exit(1)

# Run the first function
export_all_airport_data(verbose=True)

print("\n" + "="*60)
print("STEP 2: Create outbound connections list")
print("="*60)

# Run the second function
create_outbound_connections_list(verbose=True)

# Check output
if os.path.exists(os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")):
    print("\n✓ outbound_connections.csv created successfully!")
    with open(os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")) as f:
        lines = f.readlines()
        print(f"  Total lines: {len(lines)}")
        print(f"  Header: {lines[0].strip()}")
        print(f"  First data row: {lines[1].strip()}")
else:
    print("\n✗ outbound_connections.csv NOT created")