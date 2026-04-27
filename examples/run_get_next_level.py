import os
from wikipediaGATN.wikipedia_network_level import (
    get_connections_level_N,
    check_processed_list,
    _find_max_level,
    TEMP_RESULTS_DIR
)

if __name__ == "__main__":
    max_lvl = _find_max_level(TEMP_RESULTS_DIR)
    
    if max_lvl == -1:
        print("No valid level data found in tmp_results. Run a seed script first.")
    else:
        print(f"Current maximum depth is {max_lvl}.")
        print(f"Pushing network from Level {max_lvl} to Level {max_lvl + 1}...")
        
        get_connections_level_N(from_length=max_lvl, delay=0.33, verbose=True)
        check_processed_list(verbose=True)
        print("Done!")
