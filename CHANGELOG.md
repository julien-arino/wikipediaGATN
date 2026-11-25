# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Graph semantics** (model clarifications raised in review):
  - Exported graph **nodes** now carry a `code_type` attribute (`IATA` or
    `ICAO`), since a minority of nodes are 4-letter ICAO codes for airports with
    no IATA code.
  - Exported graph **edges** now carry a `seasonal` attribute (`1` for a
    seasonal-only or not-yet-started route, `0` for a year-round one), parsed
    from the Wikipedia airline/destination tables and `{{Airport-dest-list}}`
    wikitext and threaded through a new `seasonal` column in the network CSVs.
  - Passenger graph nodes carry an `airlines_reliable` attribute; airports whose
    airline/destination data came from the unreliable spaCy **NLP fallback** no
    longer publish their inflated airline counts (fallback passenger edges get
    weight 1 and the airport's `nb_airlines` is dropped). Provenance is tracked
    from the scraper through the airport JSON (`airlines_nlp_fallback`).
  - The `symmetric` adjacency build now writes the `_sym` suffix on the
    `.graphml`/`.gexf`/`.dot` files too (previously only `.npz`/`.txt`), so a
    symmetric build no longer overwrites the directed graph files in place.

  These take effect on the next data rebuild/refresh; the currently published
  data is unchanged until then.
- The PyPI wheel now **bundles the pre-built global networks** (passenger and
  cargo `.graphml`/`.gexf`/`.dot`/`.csv`, the `.npz` adjacency matrices,
  `nodes_*.txt`, and `airports_information.csv`), mapped into the package via
  hatch `force-include` with no duplication in the source tree. `PUBLIC_DATA_DIR`
  gains a fourth resolution tier that falls back to this bundled copy when no
  local `data/public` exists, so `pip install wikipediaGATN` can read the
  published networks without a prior crawl or checkout — fixing the
  `FileNotFoundError` reviewers hit in quickstart Tutorial 2. The interactive
  Plotly HTML and `ourairports.csv` are intentionally not bundled, keeping the
  wheel at ~2.4 MB (the graph files compress well). The bundled snapshot is
  read-only; set `WIKIPEDIAGATN_DATA_DIR` to a writable directory to run a crawl.

### Changed
- The weekly data refresh no longer pushes straight to `main`. It now snapshots
  the committed data, rebuilds the networks, **validates** the result against
  that baseline with the new `scripts/validate_refresh.py` guardrail, and only
  then opens (or updates) a pull request with the refreshed data — so a scrape
  regression is caught and reviewed instead of silently corrupting the published
  networks. The guardrail fails the run if a network loses more than 10% of its
  nodes or 15% of its routes, if any top-25 hub loses all or more than half of
  its outbound routes, or if the count of airports with no outbound routes
  spikes. The pull-request step is dormant until a `REFRESH_DATA_PAT` repository
  secret is configured (a PAT is required because PRs opened with the default
  token do not trigger CI); see [Data Maintenance](docs/maintenance.md).
- Dropped end-of-life Python 3.10 (EOL 2026-10-01) and added 3.13 and 3.14.
  `requires-python` is now `>=3.11`; the classifiers, CI test matrix, weekly
  refresh workflow, and ruff/black target versions were updated to match.

### Fixed
- Windows: airport codes that collide with reserved device names (AUX, NUL, PRN,
  and the CON/COM#/LPT# family) are now stored with a trailing underscore on disk
  (`AUX.json` -> `AUX_.json`) and un-escaped when read, so `git clone` and a full
  crawl both work on Windows. The three affected files (Araguaína, Nulato,
  Pristina) were renamed, preserving the data. Removed a stray `MagicMock` test
  artefact that a test had written into `data/public`.

### Tests
- The integration tests for the pipeline (`export_all_airport_data`,
  `check_duplicated_iata_codes`, `create_outbound_connections_list`) now run
  offline against a small committed fixture dataset via the new
  `isolated_data_dir` fixture, instead of requiring a prior live crawl and
  writing into the real `data/public`. They are no longer `network`-marked or
  skipped in CI, which raises coverage of the pipeline modules. Added
  `tests/test_paths.py` for the reserved-code escaping helpers.
- Added offline unit tests for the Wikipedia **parsers** — the code that does
  the actual extraction — against small committed wikitext/HTML fixtures
  (`tests/fixtures/wikitext`, `tests/fixtures/html`): `test_parsers.py` covers
  infobox/airline/destination parsing from wikitext and HTML (passenger and
  cargo, coordinate and ISO-3166-2 resolution, the maintenance-box skip and the
  table-less fallbacks), and `test_refresh_airport_data.py` covers
  `check_needs_refresh` with the Wikipedia API mocked. This roughly doubles
  coverage of `airport_level_functions.py` (29% -> 56%), takes
  `refresh_airport_data.py` from 0% to 23%, and raises total coverage to 53%.
- Added `tests/test_validate_refresh.py` covering the weekly-refresh guardrail:
  the pure node/edge/hub/zero-out-degree comparison logic and the CSV IO layer.

- Consolidated every Wikipedia/Wikimedia request behind a single shared
  `User-Agent` with a real contact address and the actual package version,
  replacing the placeholder `julien.arino@example.com` and stale-version strings.
- `__version__` is now read from the installed package metadata, so it can no
  longer drift from `pyproject.toml` (previously reported `0.1.1`).
- Replaced emoji/Unicode glyphs in printed messages with ASCII tags to avoid
  `UnicodeEncodeError` on Windows consoles using the cp1252 code page.
- Create the destination directory before writing the cached `ourairports.csv`,
  fixing a first-run `FileNotFoundError` on a fresh data folder.

### Removed
- Dropped the unused `click` runtime dependency.
- Removed the vestigial `setup.py` and the `[tool.setuptools.packages.find]`
  block left over from a setuptools build (the project builds with hatchling).
- Removed the editable `git+ssh://` self-install line from `requirements.txt`,
  which failed for anyone without push access to the repository.

### Documentation
- Added a **"Network structure and semantics"** section to the README and an
  "Interpreting the networks" section to the usage docs, documenting what the
  nodes, edges and weights mean: edge weights are **airline counts** (so summing
  a row is not a node's out-degree), nodes may be IATA **or** ICAO codes
  (`code_type`), the `seasonal` edge attribute and NLP-fallback
  `airlines_reliable` flag, the directed-vs-symmetric `_sym` build and its
  **max-weight** rule, and the **partial cargo** coverage. Added current
  node/edge/ICAO/bidirectional counts and clarified what the PyPI wheel bundles
  vs. what only lives in the repository.
- Documented the `data/public/` edge-list CSV columns (including the new
  `seasonal` column) and the graph node/edge attributes, replaced the stale
  hard-coded extraction date, and added a **licensing & attribution** section
  (Wikipedia CC BY-SA 4.0 + OurAirports public domain).
- Enabled MyST heading anchors so in-page cross-document links resolve.
- Added `CITATION.cff` and this changelog.

## [0.1.4]

- Baseline release reviewed for the pyOpenSci / JOSS submission.
