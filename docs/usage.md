# Usage

## Basic Example

The following example builds a network for all airports reachable within two hops of Winnipeg (YWG):

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN.result_processing_network import (
    create_outbound_connections_list,
    run_two_pass_iata_extraction,
    create_outbound_adjacency_matrix,
)

# 1. Crawl Wikipedia
iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

# 2. Build connections list
create_outbound_connections_list(verbose=True)

# 3. Recover missing IATA codes
run_two_pass_iata_extraction(batch_size=50, delay=0.5, verbose=True)

# 4. Re-run connections with enriched mapping
create_outbound_connections_list(verbose=True)

# 5. Export adjacency matrix
create_outbound_adjacency_matrix(symmetric=False, verbose=True)
```

## Global Crawl

To perform a full global crawl (this may take several hours):

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_empty
iterate_search_until_empty("YWG", delay=0.5, verbose=True)
```
