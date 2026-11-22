# API Reference

This page documents the public modules and functions in `wikipediaGATN`.

The names re-exported at the top level of the package (see `wikipediaGATN.__all__`) are the
recommended entry points:

- {func}`~wikipediaGATN.connections.create_outbound_connections_list`
- {func}`~wikipediaGATN.adjacency.create_outbound_adjacency_matrix`
- {func}`~wikipediaGATN.result_processing_airports.export_all_airport_data`
- {func}`~wikipediaGATN.result_processing_airports.check_duplicated_iata_codes`
- {func}`~wikipediaGATN.result_processing_network.run_two_pass_iata_extraction`
- {func}`~wikipediaGATN.extract_iata_from_wikipedia.extract_iata_from_unmapped_destinations`
- {func}`~wikipediaGATN.extract_iata_from_wikipedia.create_manual_mapping_from_scraped_data`

## Network-level crawling

```{eval-rst}
.. automodule:: wikipediaGATN.wikipedia_network_level
   :members:
   :undoc-members:
   :show-inheritance:
```

## Airport-level parsing

```{eval-rst}
.. automodule:: wikipediaGATN.airport_level_functions
   :members:
   :undoc-members:
   :show-inheritance:
```

## Connections

```{eval-rst}
.. automodule:: wikipediaGATN.connections
   :members:
   :undoc-members:
   :show-inheritance:
```

## Adjacency matrices

```{eval-rst}
.. automodule:: wikipediaGATN.adjacency
   :members:
   :undoc-members:
   :show-inheritance:
```

## IATA recovery

```{eval-rst}
.. automodule:: wikipediaGATN.extract_iata_from_wikipedia
   :members:
   :undoc-members:
   :show-inheritance:
```

## Result processing — airports

```{eval-rst}
.. automodule:: wikipediaGATN.result_processing_airports
   :members:
   :undoc-members:
   :show-inheritance:
```

## Result processing — network pipeline

```{eval-rst}
.. automodule:: wikipediaGATN.result_processing_network
   :members:
   :undoc-members:
   :show-inheritance:
```

## Visualisation

```{eval-rst}
.. automodule:: wikipediaGATN.visualise_gatn
   :members:
   :undoc-members:
   :show-inheritance:
```

## Data refresh

```{eval-rst}
.. automodule:: wikipediaGATN.refresh_airport_data
   :members:
   :undoc-members:
   :show-inheritance:
```

## Paths

```{eval-rst}
.. automodule:: wikipediaGATN.paths
   :members:
   :undoc-members:
   :show-inheritance:
```
