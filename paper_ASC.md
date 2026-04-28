---
title: 'wikipediaGATN: A Python package to compute the global air transportation network from Wikipedia'
tags:
  - Python
  - transportation
  - global air transportation network
  - network analysis
  - epidemiology
  - graph theory
  - social networks
  - web scraping
authors:
  - name: Julien Arino
    orcid: 0000-0001-6409-5027
    equal-contrib: true
    affiliation: 1
  - name: Adriana-Stefania Ciupeanu
    orcid: 0000-0003-0833-2176
    equal-contrib: true
    affiliation: 1
affiliations:
  - name: University of Manitoba, Winnipeg, Manitoba, Canada
    index: 1
date: 17 February 2026
bibliography: paper.bib
---

# Summary

The global air transportation network (GATN) is a critical infrastructure that connects the world's population and facilitates the movement of people, goods, and services across international boundaries. Understanding the structure and dynamics of this network is essential for research spanning diverse fields including epidemiology, public health, geography, economics, urban planning, and climate science. The GATN has proven particularly important during global health emergencies, where air travel patterns directly influence the geographic spread of infectious diseases.

`wikipediaGATN` is a Python package that constructs a computational representation of the global air transportation network by leveraging publicly available data from Wikipedia. The package automatically scrapes information from airport Wikipedia pages to extract airport codes (IATA and ICAO), identify airline routes, and build directed networks representing air connections between airports. The resulting network data can be exported in multiple formats suitable for analysis using standard graph theory and network analysis tools.

This package democratizes access to GATN data for researchers who lack resources to purchase expensive commercial aviation databases. It has been successfully applied to real-world problems including pandemic preparedness and response, and is suitable for both research and educational purposes.

# Statement of need

## The Data Access Problem

The structure of the global air transportation network is fundamental to understanding numerous real-world phenomena. Commercial data providers such as IATA, OAG (Official Airline Guide), and Sabre maintain comprehensive databases of flight routes, aircraft types, airlines, and passenger volumes. However, access to these datasets is restricted to paying customers and carries significant licensing costs that can range from thousands to hundreds of thousands of dollars annually. This pricing structure creates a significant barrier for:

- Researchers in developing countries and under-resourced institutions
- Academics in early career stages with limited research budgets
- Educators seeking real-world network data for teaching
- Interdisciplinary teams lacking dedicated funding for data acquisition

While other sources of GATN data exist (e.g., FlightRadar24, OpenFlights), these either require API licenses, have restricted commercial use terms, or provide incomplete route information.

## Why Wikipedia?

Wikipedia has evolved into an unexpectedly rich source of structured data about global aviation infrastructure. The Wikipedia community has standardized the format of airport information pages, resulting in:

1. **Consistent information structure**: Nearly all airport pages follow the same format with standardized infoboxes containing airport codes and geographic information
2. **Detailed airline route information**: Most airport pages include comprehensive tables listing airlines operating from that airport and their destinations
3. **Open access**: All content is freely available under open licenses
4. **Reasonable coverage**: Over 2,900 airport pages covering most airports with commercial service
5. **Community maintenance**: Errors are generally corrected by the Wikipedia community

This combination makes Wikipedia a viable alternative data source for constructing a reasonable approximation of the GATN structure, albeit without information on flight frequencies or passenger volumes.

## Research and Educational Applications

`wikipediaGATN` addresses a real need in multiple research communities:

**Epidemiology and Public Health**: An earlier version of this package was used during the COVID-19 pandemic response. The authors were contracted by the Public Health Agency of Canada to create daily summaries of likely geographic locations for emerging COVID-19 cases. The network structure was essential for projecting disease spread pathways and identifying high-risk regions requiring enhanced surveillance. As international travel resumed post-lockdown, accurate GATN data was crucial for modeling pandemic evolution and informing public health policy.

**Network Science Education**: Students learning graph theory, social network analysis, and complex systems benefit from real-world networks with meaningful structure. The GATN is an ideal teaching example: it is large enough to demonstrate meaningful network properties (small-world characteristics, hub structures, community detection), yet simple enough to understand intuitively. The package enables instructors to provide students with hands-on experience analyzing real transportation networks.

**Transportation Research**: Academic research on aviation systems, route optimization, hub identification, and transportation resilience requires network data. The package provides a foundation for such research without data licensing barriers.

**Geographic and Mobility Studies**: Research on human mobility patterns, international connectivity, and geographic inequality can leverage the network structure provided by this package.

## Filling a Gap

While the GATN structure available from `wikipediaGATN` is necessarily incomplete (lacking flight frequency information), it provides sufficient information to:
- Identify connected components and accessibility patterns
- Locate hub airports and key connectors
- Study macro-scale network topology
- Model disease transmission pathways
- Teach network analysis concepts

For many research questions, especially those focused on geometric network structure rather than flow volumes, this data is adequate and invaluable.

# Methods

## Data Source and Acquisition

Wikipedia airport pages represent a semi-structured data source with consistent but not fully standardized formatting. The acquisition process involves:

1. **Airport page identification**: Starting with Wikipedia's list of airports, the package identifies airport pages for airports with commercial service
2. **Information extraction**: Using BeautifulSoup, the package parses HTML content to extract:
   - IATA codes (3-letter airport identifiers used internationally)
   - ICAO codes (4-letter identifiers)
   - Airport name and location
3. **Route table parsing**: Most airport pages include one or more tables detailing airlines and their destinations from that airport
4. **Destination normalization**: Extracted destination names are normalized and matched to known airport codes using fuzzy string matching

## Technical Architecture

### Core Modules

The package consists of several specialized modules:

**`connections.py`**: Responsible for extracting airline route information from airport Wikipedia pages. This module:
- Normalizes URLs and airport page identifiers
- Extracts airport codes from Wikipedia page content
- Performs fuzzy matching to resolve airport name variations
- Builds bidirectional mappings between URLs and IATA codes
- Manages the construction of the outbound connections list

**`extract_iata_from_wikipedia.py`**: Handles extraction of IATA codes from destination names on airport pages. This module:
- Scrapes Wikipedia airport pages for the infobox containing airport codes
- Uses regex pattern matching and natural language processing to identify codes
- Implements confidence scoring for extracted codes
- Provides batch processing for efficient extraction
- Manages caching to minimize API calls

**`adjacency.py`**: Constructs sparse matrix representations of the network. This module:
- Creates adjacency matrices from the connections data
- Supports both directed (asymmetric) and undirected (symmetric) representations
- Uses scipy sparse matrix formats for memory efficiency
- Exports network data in multiple formats
- Computes basic network statistics

**`paths.py`**: Manages file paths and data organization, providing a consistent interface for locating data files and output directories across different systems.

**`result_processing.py`**: Post-processes extracted network data, handles data cleaning, and exports results in various formats suitable for downstream analysis.

**`visualise_adjacency_matrix.py`**: Provides visualization utilities for network structure exploration and presentation.

### Data Flow

The typical workflow proceeds as follows:

1. **Network Construction Phase**: The package identifies all major airports and iteratively retrieves their Wikipedia pages
2. **Information Extraction Phase**: For each airport, the package extracts outbound connections using web scraping and pattern matching
3. **Mapping and Normalization Phase**: Destination names are normalized and mapped to standardized airport codes
4. **Network Representation Phase**: The cleaned connection data is converted into graph/network representations
5. **Output Phase**: Results are exported in multiple formats (adjacency matrices, edge lists, etc.)

## Handling Challenges

### Incomplete and Inconsistent Data

Wikipedia pages vary in completeness and structure. The package employs several strategies:

- **Fuzzy matching**: Uses string similarity metrics to handle airport name variations
- **Confidence scoring**: Rates confidence in extracted codes based on match quality
- **Manual override capability**: Allows users to provide manual mappings for difficult cases
- **Validation**: Checks extracted codes against known airport code lists

### Network Incompleteness

The Wikipedia-derived network necessarily underrepresents some connections. The package acknowledges this through:
- Documentation of data limitations
- Confidence metrics for each connection
- Clear distinction between actual flight frequency (unavailable) and route existence (available)

### Temporal Changes

Airport routes change over time. The package provides:
- Timestamping of extracted data
- Version control capabilities
- Support for constructing networks at different time points

# Features

- **Zero Cost**: Built on free, publicly available Wikipedia data with no API licensing required
- **Minimal Dependencies**: Uses only standard Python scientific packages (pandas, numpy, scipy, requests, beautifulsoup4)
- **Easy Installation**: Simple pip installation with automatic dependency resolution
- **Multiple Export Formats**: Supports adjacency matrices, edge lists, and node lists
- **Network Flexibility**: Supports both directed and undirected network representations
- **Fuzzy Matching**: Handles airport name variations through intelligent string matching
- **Batch Processing**: Efficient extraction for thousands of airports
- **Extensible Design**: Clear module structure allowing customization and extension

# Implementation

## Key Algorithms

### IATA Code Extraction

The extraction of IATA codes from Wikipedia content employs regular expression matching combined with confidence scoring. The algorithm:
1. Searches for patterns matching IATA format (3 uppercase letters in parentheses or after "IATA:")
2. Validates candidates against known IATA code lists
3. Assigns confidence scores based on match context and proximity to airport name
4. Returns highest-confidence matches with associated confidence metrics

### Fuzzy Destination Matching

Destination names extracted from route tables frequently contain variations (e.g., "Toronto Pearson" vs "Pearson International"). The package uses:
1. Levenshtein distance for string similarity calculation
2. Thresholding to accept matches above confidence thresholds
3. Fallback to manual mapping for low-confidence matches

### Network Construction

The adjacency matrix construction:
1. Creates a node list of all identified airports (sorted for consistency)
2. For each edge (origin airport to destination), places a 1 in the corresponding matrix position
3. Optionally symmetrizes the matrix for undirected network analysis
4. Stores matrices in sparse format (scipy CSR) for memory efficiency with large networks


# Use Cases and Applications

## Pandemic Preparedness and Response

During the COVID-19 pandemic, this package supported the Public Health Agency of Canada's efforts to:
- Identify geographic areas at elevated risk of disease importation
- Project transmission pathways based on air travel patterns
- Allocate testing and surveillance resources
- Monitor disease spread at international borders


# Acknowledgements

We acknowledge discussions with Stephanie Portet. JA acknowledges years of fruitful collaboration with Kamran Khan, CEO of Bluedot.global, through whom he had access to much more extensive data. We also acknowledge the Wikipedia community for maintaining comprehensive airport information that makes this work possible. 

# References