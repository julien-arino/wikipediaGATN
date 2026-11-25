# Test fixtures

Small, committed fixtures that let the test suite run **fully offline and
deterministically** — no live Wikipedia crawl and no network access.

## `airport_data/`, `ourairports.csv`

A minimal seeded `data/public` tree (three airports plus a three-row
OurAirports cache) used by the `isolated_data_dir` fixture in
[`../conftest.py`](../conftest.py) to exercise the high-level pipeline functions
(`export_all_airport_data`, `create_outbound_connections_list`, …).

## `wikitext/`, `html/` — parser fixtures

These drive the Wikipedia *parser* tests (`../test_parsers.py`), which are the
code paths that actually extract airlines and destinations.

They are **not** full page dumps. A real airport article is ~0.5–1 MB of HTML,
most of it navigation, scripts and styling the parser never looks at, and the
project is already trying to keep repository history small. Instead each fixture
is a compact file that faithfully reproduces the *specific* markup the parser
targets, so the real parsing code runs against realistic input:

| File | Models | Exercises |
| --- | --- | --- |
| `wikitext/winnipeg_sample.wikitext` | `{{Infobox airport}}` + `{{Airport-dest-list}}` templates (passenger and cargo), `{{coord\|...\|region:CA-MB}}` coordinates | `parse_infobox_from_wikitext`, `parse_wikitext_airlines_destinations` |
| `html/airlines_destinations.html` | The "Airlines and destinations" `wikitable`, a maintenance `ambox` to skip, and a `Cargo` sub-section | `fetch_wikipedia_airlines`, `fetch_wikipedia_destinations`, `fetch_wikipedia_airlines_destinations` |
| `html/prose_no_table.html` | A table-less article (IATA/ICAO/coords in prose) | `fallback_fetch_wikipedia_airport_info`, `parse_fallback_nlp_airlines_destinations` |

All names (airports, airlines) are fictional/illustrative; the markup structure
mirrors the current English Wikipedia conventions the scraper was written
against. If Wikipedia changes that structure and the scraper is updated, update
these fixtures to match.
