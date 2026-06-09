# Usage

## Basic Example

The following example builds a network for all airports reachable within two hops of Winnipeg (YWG):

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN import (
    export_all_airport_data,
    create_outbound_connections_list,
    run_two_pass_iata_extraction,
    create_outbound_adjacency_matrix,
)

# 1. Crawl Wikipedia (scrapes raw JSON files to data/tmp_results/)
iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

# 2. Process and export airport data (creates public/airport_data/ and airports_information.csv)
export_all_airport_data(use_new_data=True, verbose=True)

# 3. Build connections list (creates global-air-pax-network.csv and unmapped_destinations.csv)
create_outbound_connections_list(verbose=True)

# 4. Recover missing IATA codes
run_two_pass_iata_extraction(batch_size=50, delay=0.5, verbose=True)

# 5. Re-export airport data to apply the recovered manual mappings
export_all_airport_data(use_new_data=True, verbose=True)

# 6. Re-run connections with enriched mapping
create_outbound_connections_list(verbose=True)

# 7. Export adjacency matrix
create_outbound_adjacency_matrix(symmetric=False, verbose=True)
```

## Global Crawl

To perform a full global crawl (this may take several hours):

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_empty
iterate_search_until_empty("YWG", delay=0.5, verbose=True)
```
