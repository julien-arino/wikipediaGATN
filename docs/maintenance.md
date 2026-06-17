# Data Maintenance & Weekly Refresh

`wikipediaGATN` is designed to provide an up-to-date view of the global air transportation network. To achieve this, the repository includes automated processes for refreshing the data and re-generating network analysis files.

## Automated Weekly Refresh

A GitHub Action, defined in `.github/workflows/refresh_data.yml`, runs automatically every **Sunday at 00:00 UTC**.

This workflow performs the following steps:
1. **Incremental Update**: It runs `python -m wikipediaGATN.refresh_airport_data --target all`, which checks the "last modified" timestamp of every airport page on Wikipedia against the local version. Only pages that have changed since the last crawl are re-fetched.
2. **Network Re-generation**: It runs `python -m wikipediaGATN.result_processing_network` to rebuild the global connection lists, sparse adjacency matrices, and graph-theoretic export files (GraphML, GEXF, DOT).
3. **Visualisation Update**: It runs `python -m wikipediaGATN.visualise_gatn` to update the interactive Plotly HTML maps and globes.
4. **Commit & Push**: If any data has changed, the bot automatically commits and pushes the updated files in `data/public/` back to the main branch.

## Manual Data Refresh

You can trigger a data refresh manually in two ways:

### Via GitHub Actions UI
If you have write access to the repository:
1. Navigate to the **Actions** tab on GitHub.
2. Select the **Weekly Data Refresh** workflow.
3. Click the **Run workflow** dropdown and select **Run workflow**.

### Via Command Line
If you have cloned the repository and installed the package in development mode, you can run the same pipeline locally:

```bash
# 1. Update airport metadata JSONs
python -m wikipediaGATN.refresh_airport_data --target all

# 2. Rebuild network files (CSVs, matrices, graphs)
python -m wikipediaGATN.result_processing_network

# 3. Update HTML visualisations
python -m wikipediaGATN.visualise_gatn
```

## Adding New Airports

The current global dataset was initialized from a full crawl starting from Winnipeg (YWG). If you discover a missing airport, you can add it to the network by running a local search with that airport as a seed:

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN.result_processing_airports import export_all_airport_data

# 1. Scrape the new airport and its immediate neighbors
iterate_search_until_distance_N("NEW_IATA_CODE", dist=1, verbose=True)

# 2. Integrate the new JSONs into the public repository
export_all_airport_data(use_new_data=True, verbose=True)
```

After integrating new data, follow the steps in the **Manual Data Refresh** section to rebuild the aggregate network files.
