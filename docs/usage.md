# Usage

## Using Pre-built Data & Network Analysis

The global network data in `data/public/` is automatically updated weekly via GitHub Actions. **You do not need to run your own crawl to use this data.** You can clone this repository (or download the `data/` folder) and immediately load the provided sparse matrices to perform graph analysis.

Here is an end-to-end example showing how to load the passenger network from the pre-built `.npz` file and analyze it with `networkx`:

```python
import numpy as np
import scipy.sparse
import networkx as nx

# 1. Load the node labels (IATA codes)
with open('data/public/nodes_pax.txt', 'r') as f:
    iata_codes = [line.strip() for line in f]

# 2. Load the sparse adjacency matrix
matrix = scipy.sparse.load_npz('data/public/outbound_adjacency_pax.npz')

# 3. Create a NetworkX directed graph
G = nx.from_scipy_sparse_array(matrix, create_using=nx.DiGraph)

# 4. Map node indices to their actual IATA codes
mapping = {i: code for i, code in enumerate(iata_codes)}
nx.relabel_nodes(G, mapping, copy=False)

print(f"Network has {G.number_of_nodes()} airports and {G.number_of_edges()} routes.")

# 5. Basic analysis: find the airport with the most incoming flights
in_degrees = dict(G.in_degree())
most_connected = max(in_degrees, key=in_degrees.get)
print(f"Most connected destination: {most_connected} ({in_degrees[most_connected]} incoming routes)")
```

## Basic Scraping Example

Note: If you run this script locally and the `data/public/` directory does not exist, `export_all_airport_data` will raise a FileNotFoundError. Make sure to run your scripts from the root directory of the repository where the `.venv` directory usually resides, or explicitly provide a path to the functions if running from outside the project directory.

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
