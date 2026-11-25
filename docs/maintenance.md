# Data Maintenance & Weekly Refresh

`wikipediaGATN` is designed to provide an up-to-date view of the global air transportation network. To achieve this, the repository includes automated processes for refreshing the data and re-generating network analysis files.

## Automated Weekly Refresh

A GitHub Action, defined in `.github/workflows/refresh_data.yml`, runs automatically every **Sunday at 00:00 UTC**.

This workflow performs the following steps:
1. **Snapshot the baseline**: It copies the currently committed `data/public/` aside so the rebuild can be compared against it.
2. **Incremental Update**: It runs `python -m wikipediaGATN.refresh_airport_data --target all`, which checks the "last modified" timestamp of every airport page on Wikipedia against the local version. Only pages that have changed since the last crawl are re-fetched.
3. **Network Re-generation**: It runs `python -m wikipediaGATN.result_processing_network` to rebuild the global connection lists, sparse adjacency matrices, and graph-theoretic export files (GraphML, GEXF, DOT).
4. **Visualisation Update**: It runs `python -m wikipediaGATN.visualise_gatn` to update the interactive Plotly HTML maps and globes.
5. **Validation (hard gate)**: It runs `python scripts/validate_refresh.py` to compare the rebuilt passenger and cargo networks against the baseline. The job **fails and stops** if the rebuild looks like a scrape regression rather than a genuine update (see below).
6. **Open a pull request**: If the data changed and validation passed, it opens (or updates) a pull request on the `automated/weekly-data-refresh` branch via [`peter-evans/create-pull-request`](https://github.com/peter-evans/create-pull-request) rather than pushing straight to `main`. CI runs on the PR like any other change, and the refreshed data is reviewed before it is published.

### Why a pull request instead of a direct push?

Earlier versions committed the refreshed data directly to `main`. A re-scrape can regress for reasons unrelated to real-world changes — Wikipedia markup drifts, a destination table fails to parse, or a transient error empties a hub — and a direct push would silently corrupt the published data. Routing the refresh through a validated pull request means a bad rebuild is caught by `scripts/validate_refresh.py` and never lands, while a genuine update still flows through automatically.

### What `validate_refresh.py` checks

For both the passenger and cargo networks it compares the rebuild against the committed baseline and fails if:

- the **node count** drops by more than 10%;
- the **edge (route) count** drops by more than 15%;
- any of the **top-25 hubs** (airports with the most outbound routes) loses *all* of its routes or more than 50% of its out-degree;
- the number of airports with **no outbound routes** spikes (which usually means destination tables failed to parse).

Growth is always allowed; the thresholds only trip on the kind of large, structural loss a regression produces. The checks are unit-tested in `tests/test_validate_refresh.py`. You can run the validator locally against two `data/public`-style directories:

```bash
python scripts/validate_refresh.py \
    --baseline-dir /path/to/old/public \
    --candidate-dir data/public
```

### Activating the automated pull-request flow

The workflow is **dormant until a token is configured**. The build-and-validate steps run on the weekly schedule, but opening the pull request requires a Personal Access Token, because pull requests opened with the default `GITHUB_TOKEN` do **not** trigger CI — so the validation and test checks would never run on them.

To activate it:

1. Create a **fine-grained Personal Access Token** scoped to this repository with **Contents: read and write** and **Pull requests: read and write** permissions.
2. Add it as a repository secret named **`REFRESH_DATA_PAT`** (Settings → Secrets and variables → Actions → New repository secret).
3. *(Optional, for hands-off merging)* In Settings → General, enable **Allow auto-merge**, and add a branch-protection rule on `main` that requires the test workflow to pass. The workflow then calls `gh pr merge --auto`, so a refresh PR merges itself once CI is green; otherwise the PR is left open for manual review.

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
