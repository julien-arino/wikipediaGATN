# Quickstart Tutorials

This page contains short tutorials to help you get started with the `wikipediaGATN` package. You will learn how to perform a local crawl and run a basic network analysis on the output, as well as how to analyze the pre-built global network data directly without scraping.

---

## Tutorial 1: End-to-End Local Crawl & Network Analysis

If you want to gather data for a small-scale airport network (e.g. Winnipeg and its 2-hop neighbors) and analyze it, you can run the following script.

```python
import os
import networkx as nx
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN.result_processing_airports import export_all_airport_data
from wikipediaGATN.connections import create_outbound_connections_list
from wikipediaGATN.adjacency import create_outbound_adjacency_matrix
from wikipediaGATN.paths import PUBLIC_DATA_DIR

# 1. Crawl Wikipedia (Winnipeg YWG and all airports reachable in 2 hops)
# This writes raw JSON files into your data/tmp_results directory.
print("Step 1: Crawling Wikipedia...")
iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

# 2. Process and consolidate raw JSONs
# Ingests raw JSONs, fills missing geography/IATA data, and exports formatted
# JSONs to public/airport_data alongside airports_information.csv.
print("\nStep 2: Processing and exporting airport metadata...")
export_all_airport_data(use_new_data=True, verbose=True)

# 3. Create outbound passenger & cargo connections CSVs
print("\nStep 3: Creating outbound connections lists...")
create_outbound_connections_list(verbose=True)

# 4. Generate sparse adjacency matrices and graph-theoretic network files
print("\nStep 4: Creating adjacency matrix and network export formats...")
matrix_path, nodes_path = create_outbound_adjacency_matrix(symmetric=False, verbose=True)

# 5. Load the resulting network with NetworkX and perform basic analysis
graphml_path = os.path.join(PUBLIC_DATA_DIR, "global-air-pax-network.graphml")
G = nx.read_graphml(graphml_path)

print("\n--- Network Characteristics ---")
print(f"Airports (nodes) in 2-hop network: {G.number_of_nodes()}")
print(f"Scheduled routes (edges):           {G.number_of_edges()}")

# Find the top 5 airports by out-degree (most destination routes)
out_degrees = sorted(G.out_degree(), key=lambda x: x[1], reverse=True)
print("\nTop 5 airports by outbound routes:")
for iata, degree in out_degrees[:5]:
    name = G.nodes[iata].get("name", "Unknown Name")
    city = G.nodes[iata].get("city_served", "Unknown City")
    print(f"  {iata} - {name} ({city}): {degree} destinations")
```

---

## Tutorial 2: Loading & Analyzing Pre-built Global Network Data

`wikipediaGATN` includes pre-built global air transportation networks under `data/public/`. You do not need to scrape Wikipedia yourself if you want to analyze the global graphs. 

Here are three different ways to load the pre-built passenger (pax) network data.

### Option A: Loading GraphML directly into NetworkX

GraphML is the recommended format because it preserves rich node attributes (e.g. coordinates, city served, country).

```python
import os
import networkx as nx
from wikipediaGATN.paths import PUBLIC_DATA_DIR

# Locate the pre-built passenger network GraphML file
graphml_path = os.path.join(PUBLIC_DATA_DIR, "global-air-pax-network.graphml")

if not os.path.exists(graphml_path):
    raise FileNotFoundError(
        f"Pre-built network file not found at: {graphml_path}\n"
        "Ensure the package was installed with pre-built data or run the update script."
    )

# Load the directed graph
G = nx.read_graphml(graphml_path)
print("--- Global Passenger Network Loaded ---")
print(f"Total Airports (nodes): {G.number_of_nodes():,}")
print(f"Total Routes (edges):   {G.number_of_edges():,}")

# Identify the top 10 global hubs by out-degree
hubs = sorted(G.out_degree(), key=lambda x: x[1], reverse=True)
print("\nTop 10 Global Hubs (Outbound Connections):")
for idx, (iata, degree) in enumerate(hubs[:10], 1):
    name = G.nodes[iata].get("name", "Unknown Name")
    city = G.nodes[iata].get("city_served", "Unknown City")
    country = G.nodes[iata].get("country_name", "Unknown Country")
    print(f"{idx:>2}. {iata} - {name} ({city}, {country}) -> {degree} destinations")
```

### Option B: Reading Connections CSV with Pandas

If you are using Pandas for data analysis, you can load the connection list CSV directly.

```python
import os
import pandas as pd
from wikipediaGATN.paths import PUBLIC_DATA_DIR

pax_csv = os.path.join(PUBLIC_DATA_DIR, "global-air-pax-network.csv")
df = pd.read_csv(pax_csv)

print("--- Passenger Connections DataFrame ---")
print(f"Loaded {len(df):,} airport records.")
print("\nColumns:", list(df.columns))

# Show the top 5 records sorted by number of outlinks
print(df.sort_values(by="nb_outlinks", ascending=False).head())
```

### Option C: Ingesting Sparse Matrix with SciPy

For mathematical modeling or graph theory computations, you can load the Compressed Sparse Row (CSR) matrix and matching node list.

```python
import os
from scipy.sparse import load_npz
from wikipediaGATN.paths import PUBLIC_DATA_DIR

matrix_npz = os.path.join(PUBLIC_DATA_DIR, "adjacency_matrix_pax.npz")
nodes_txt = os.path.join(PUBLIC_DATA_DIR, "nodes_pax.txt")

# Load CSR sparse matrix
matrix = load_npz(matrix_npz)

# Load ordered list of node labels (matching matrix rows/columns)
with open(nodes_txt, "r", encoding="utf-8") as f:
    nodes = [line.strip() for line in f]

print("--- Sparse Adjacency Matrix Loaded ---")
print(f"Matrix shape      : {matrix.shape}")
print(f"Non-zero elements : {matrix.nnz:,}")
print(f"Number of nodes   : {len(nodes):,}")
print(f"Index 0 airport   : {nodes[0]}")
```
