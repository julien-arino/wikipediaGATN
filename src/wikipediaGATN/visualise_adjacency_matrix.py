"""
Interactive visualisation of the airport network adjacency matrix.

Reads a sparse adjacency matrix and its node list from ``PUBLIC_DATA_DIR``
and writes an interactive Plotly HTML graph.

Two layout strategies are supported:

* **Geographic** (default when coordinate data is available): nodes are
  placed at their real-world longitude/latitude.  Requires
  ``airports_information.csv`` to be present.
* **Spring** (fallback): force-directed layout via
  :func:`networkx.spring_layout`.  Slow for large graphs (> 500 nodes) and
  non-deterministic unless *seed* is fixed — use the *seed* parameter to get
  reproducible figures.

.. warning::
   Spring layout on the full global network (~4 000 nodes) can take several
   minutes and produces a spatially meaningless result.  Geographic layout
   is strongly preferred for publication figures.
"""

import warnings
from pathlib import Path
import json

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
from scipy.sparse import load_npz

from .paths import PUBLIC_DATA_DIR

__all__ = ["visualize_graph_plotly"]


def visualize_graph_plotly(
    symmetric: bool = True,
    output_path: Path | str | None = None,
    seed: int = 42,
    layout: str = "geographic",
    geographic: bool | None = None,
    verbose: bool = False,
) -> str:
    """
    Build and save an interactive Plotly HTML graph of the airport network.

    Parameters
    ----------
    symmetric : bool, optional
        If True (default), loads ``adjacency_matrix_sym.npz`` and
        ``nodes_sym.txt`` and creates an undirected :class:`networkx.Graph`.
        If False, loads the directed versions and creates a
        :class:`networkx.DiGraph`.
    output_path : path-like or None, optional
        Destination for the HTML file.  Defaults to
        ``PUBLIC_DATA_DIR/airport_graph_plotly[_sym].html``.
    seed : int, optional
        Random seed passed to :func:`networkx.spring_layout` for
        reproducible layouts.  Ignored when *geographic* is True and
        coordinate data is available.  Default: 42.
    geographic : bool, optional
        If True (default), attempt to place nodes at their real-world
        longitude/latitude by reading ``airports_information.csv``.
        Falls back to spring layout if the file is missing or coordinates
        are unavailable.
    verbose : bool, optional
        If True, prints progress messages.  Default: False.

    Returns
    -------
    str
        Absolute path to the saved HTML file.

    Raises
    ------
    FileNotFoundError
        If the matrix or node-list file does not exist.  Run
        :func:`~.adjacency.create_outbound_adjacency_matrix` first.
    """
    if geographic is not None:
        warnings.warn("The 'geographic' parameter is deprecated. Use layout='geographic' or layout='spring'.", DeprecationWarning, stacklevel=2)
        layout = "geographic" if geographic else "spring"
        
    suffix = "_sym" if symmetric else ""

    # ------------------------------------------------------------------
    # Resolve input paths
    # ------------------------------------------------------------------
    matrix_path = PUBLIC_DATA_DIR / f"adjacency_matrix{suffix}.npz"
    nodes_path  = PUBLIC_DATA_DIR / f"nodes{suffix}.txt"

    for p in (matrix_path, nodes_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Required file not found: {p}\n"
                "Run create_outbound_adjacency_matrix() first."
            )

    # ------------------------------------------------------------------
    # Load matrix and node list
    # ------------------------------------------------------------------
    if verbose:
        print(f"Loading matrix from {matrix_path}…")

    matrix = load_npz(matrix_path)

    # Filter empty strings that can appear if nodes file has a trailing newline
    nodes = [line for line in nodes_path.read_text(encoding="utf-8").splitlines()
             if line.strip()]

    n = matrix.shape[0]
    if len(nodes) != n:
        raise ValueError(
            f"Node list length ({len(nodes)}) does not match "
            f"matrix dimension ({n}).  Files may be out of sync."
        )

    # ------------------------------------------------------------------
    # Build NetworkX graph
    # ------------------------------------------------------------------
    graph_type = nx.Graph if symmetric else nx.DiGraph
    G = nx.from_scipy_sparse_array(matrix, create_using=graph_type)
    G = nx.relabel_nodes(G, {i: code for i, code in enumerate(nodes)})

    if verbose:
        print(f"Graph: {G.number_of_nodes():,} nodes, "
              f"{G.number_of_edges():,} edges")

    # ------------------------------------------------------------------
    # Node layout
    # ------------------------------------------------------------------
    pos = None

    if layout in ("geographic", "globe"):
        coord_path = PUBLIC_DATA_DIR / "airports_information.csv"
        if coord_path.exists():
            try:
                df = pd.read_csv(coord_path, dtype=str)
                df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
                df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
                coord_df = df.dropna(subset=["iata", "latitude", "longitude"])
                coord_map = dict(zip(coord_df["iata"],
                                     zip(coord_df["longitude"], coord_df["latitude"])))
                # Only use geographic layout if we have coords for most nodes
                coverage = sum(1 for n in G.nodes() if n in coord_map)
                if coverage >= 0.8 * G.number_of_nodes():
                    pos = {n: coord_map[n] for n in G.nodes() if n in coord_map}
                    # Nodes without coordinates fall back to (0, 0)
                    for node in G.nodes():
                        if node not in pos:
                            pos[node] = (0.0, 0.0)
                    if verbose:
                        print(f"Using geographic layout "
                              f"({coverage:,}/{G.number_of_nodes():,} nodes with coords)")
                else:
                    if verbose:
                        print(f"Geographic coverage too low ({coverage}/{G.number_of_nodes()})"
                              " — falling back to spring layout")
                    layout = "spring"
            except Exception as exc:
                warnings.warn(
                    f"Could not load geographic coordinates: {exc}. "
                    "Falling back to spring layout.",
                    UserWarning, stacklevel=2,
                )
        else:
            if verbose:
                print("airports_information.csv not found — using spring layout")
            layout = "spring"

    if pos is None:
        if G.number_of_nodes() > 500:
            warnings.warn(
                f"Spring layout on {G.number_of_nodes():,} nodes may be very slow. "
                "Consider using geographic=True or a subgraph.",
                UserWarning, stacklevel=2,
            )
        if verbose:
            print(f"Computing spring layout (seed={seed})…")
        pos = nx.spring_layout(G, k=0.15, iterations=20, seed=seed)

    # ------------------------------------------------------------------
    # Build Plotly traces
    # ------------------------------------------------------------------

    # --- Edge trace ---
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    if layout == "globe":
        edge_trace = go.Scattergeo(
            lon=edge_x, lat=edge_y,
            mode="lines",
            line=dict(width=0.4, color="#aaa"),
            hoverinfo="none",
        )
    else:
        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=0.4, color="#aaa"),
            hoverinfo="none",
        )

    # --- Node trace — colour by degree, text on hover only ---
    node_x, node_y, node_text, node_degree = [], [], [], []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(f"{node}<br>Degree: {G.degree(node)}")
        node_degree.append(G.degree(node))

    if layout == "globe":
        node_trace = go.Scattergeo(
            lon=node_x, lat=node_y,
            mode="markers",
            hovertext=node_text,
            hoverinfo="text",
            marker=dict(
                showscale=True,
                colorscale="Viridis",
                color=node_degree,
                size=4,
                colorbar=dict(
                    thickness=12,
                    title="Degree",
                    xanchor="left",
                ),
                line_width=0.5,
            ),
        )
    else:
        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode="markers",          # text labels off by default — too cluttered at scale
            hovertext=node_text,
            hoverinfo="text",
            marker=dict(
                showscale=True,
                colorscale="Viridis",
                color=node_degree,
                size=6,
                colorbar=dict(
                    thickness=12,
                    title="Degree",
                    xanchor="left",
                ),
                line_width=0.5,
            ),
        )

    # ------------------------------------------------------------------
    # Assemble figure
    # ------------------------------------------------------------------
    direction    = "Undirected" if symmetric else "Directed"

    fig_layout = go.Layout(
        title=dict(
            text=f"Global Airport Network ({direction}, {layout.capitalize()} layout)",
            x=0.5,
        ),
        showlegend=False,
        hovermode="closest",
        margin=dict(b=20, l=5, r=5, t=50),
    )
    
    if layout == "globe":
        fig_layout.geo = dict(
            projection_type="orthographic",
            showland=True,
            landcolor="rgb(243, 243, 243)",
            countrycolor="rgb(204, 204, 204)",
            showocean=True,
            oceancolor="rgba(10, 20, 30, 0.1)"
        )
    else:
        fig_layout.xaxis = dict(showgrid=False, zeroline=False, showticklabels=False)
        fig_layout.yaxis = dict(showgrid=False, zeroline=False, showticklabels=False)

    if layout == "globe":
        hl_edge = go.Scattergeo(lon=[], lat=[], mode="lines", line=dict(width=2, color="red"), hoverinfo="none")
        hl_node = go.Scattergeo(lon=[], lat=[], mode="markers", marker=dict(color="red", size=8), hoverinfo="none")
    else:
        hl_edge = go.Scatter(x=[], y=[], mode="lines", line=dict(width=2, color="red"), hoverinfo="none")
        hl_node = go.Scatter(x=[], y=[], mode="markers", marker=dict(color="red", size=8), hoverinfo="none")

    fig = go.Figure(
        data=[edge_trace, node_trace, hl_edge, hl_node],
        layout=fig_layout,
    )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    if output_path is None:
        if layout == "geographic":
            output_path = PUBLIC_DATA_DIR / f"global-air-transportation-network-plotly-geographic{suffix}.html"
        elif layout == "globe":
            output_path = PUBLIC_DATA_DIR / f"global-air-transportation-network-plotly-globe{suffix}.html"
        else:
            output_path = PUBLIC_DATA_DIR / f"global-air-transportation-network-plotly-graph{suffix}.html"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # --- Custom JavaScript Injection for click-to-highlight ---
    node_list = list(G.nodes())
    node_idx = {n: i for i, n in enumerate(node_list)}
    adj = {i: [node_idx[v] for v in G.neighbors(n)] for i, n in enumerate(node_list)}
    coords = {i: pos[n] for i, n in enumerate(node_list)}
    
    coord_keys = "['lon', 'lat']" if layout == "globe" else "['x', 'y']"
    
    # We use plot_id as a placeholder. Plotly replaces {plot_id} when rendering the HTML.
    custom_js = f"""
    const adj = {json.dumps(adj)};
    const coords = {json.dumps(coords)};
    const coord_keys = {coord_keys};
    
    var graphDiv = document.getElementById('{{plot_id}}');
    
    graphDiv.on('plotly_click', function(data) {{
        if (data.points[0].curveNumber !== 1) return; // Only process clicks on the main node trace
        
        let clicked_idx = data.points[0].pointIndex;
        let neighbors = adj[clicked_idx] || [];
        let [cx, cy] = coords[clicked_idx];
        
        let e_x = [], e_y = [];
        let n_x = [cx], n_y = [cy]; // Highlight the clicked node itself
        
        for (let i = 0; i < neighbors.length; i++) {{
            let n_idx = neighbors[i];
            let [nx, ny] = coords[n_idx];
            e_x.push(cx, nx, null);
            e_y.push(cy, ny, null);
            n_x.push(nx);
            n_y.push(ny);
        }}
        
        let update = {{}};
        update[coord_keys[0]] = [e_x, n_x];
        update[coord_keys[1]] = [e_y, n_y];
        
        Plotly.restyle(graphDiv, update, [2, 3]);
    }});
    
    graphDiv.on('plotly_doubleclick', function() {{
        let update = {{}};
        update[coord_keys[0]] = [[], []];
        update[coord_keys[1]] = [[], []];
        Plotly.restyle(graphDiv, update, [2, 3]);
    }});
    """

    fig.write_html(str(output_path), post_script=custom_js)

    if verbose:
        print(f"Interactive Plotly graph saved to {output_path.resolve()}")

    return str(output_path.resolve())


if __name__ == "__main__":
    visualize_graph_plotly(verbose=True)
