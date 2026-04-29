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
    output_path: Path | str | None = None,
    seed: int = 42,
    layout: str = "geographic",
    verbose: bool = False,
) -> str:
    """
    Build and save an interactive Plotly HTML graph of the airport network.

    Parameters
    ----------
    output_path : path-like or None, optional
        Destination for the HTML file.  Defaults to
        ``PUBLIC_DATA_DIR/airport_graph_plotly.html``.
    seed : int, optional
        Random seed passed to :func:`networkx.spring_layout` for
        reproducible layouts.  Ignored when *layout* is "geographic" or "globe".
        Default: 42.
    layout : str, optional
        Layout strategy: "geographic", "globe", or "spring". Default: "geographic".
    verbose : bool, optional
        If True, prints progress messages.  Default: False.
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
    # ------------------------------------------------------------------
    # Resolve input paths
    # ------------------------------------------------------------------
    graphml_path = PUBLIC_DATA_DIR / "global-air-transportation-network.graphml"

    if not graphml_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {graphml_path}\n"
            "Run create_outbound_adjacency_matrix() first."
        )

    # ------------------------------------------------------------------
    # Load NetworkX graph
    # ------------------------------------------------------------------
    if verbose:
        print(f"Loading matrix from {graphml_path}…")

    G = nx.read_graphml(graphml_path)

    if verbose:
        print(f"Graph: {G.number_of_nodes():,} nodes, "
              f"{G.number_of_edges():,} edges")

    # ------------------------------------------------------------------
    # Node layout
    # ------------------------------------------------------------------
    pos = None

    if layout in ("geographic", "globe"):
        pos = {}
        missing_nodes = []
        for node, data in G.nodes(data=True):
            if 'lon' in data and 'lat' in data:
                pos[node] = (float(data['lon']), float(data['lat']))
            else:
                missing_nodes.append(node)

        if missing_nodes:
            G.remove_nodes_from(missing_nodes)
            if verbose:
                print(f"Dropped {len(missing_nodes)} nodes with missing coordinates.")
        if verbose:
            print(f"Using geographic layout "
                  f"({len(pos):,}/{G.number_of_nodes() + len(missing_nodes):,} nodes with coords)")

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
    for node, data in G.nodes(data=True):
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_degree_val = G.out_degree(node)
        
        # Build rich tooltip
        airport_name = "Unknown Airport"
        if 'wikipedia_url' in data:
            airport_name = data['wikipedia_url'].split('/')[-1].replace('_', ' ')
            # Decode URL encoded characters (e.g. %27 -> ')
            import urllib.parse
            airport_name = urllib.parse.unquote(airport_name)
        elif 'city_served' in data:
            airport_name = f"{data['city_served']} Airport"

        text_lines = [f"<b>{node}</b> - {airport_name}"]
        
        location = []
        if 'city_served' in data: location.append(data['city_served'])
        if 'admin1_name' in data: location.append(data['admin1_name'])
        if 'country_name' in data: location.append(data['country_name'])
        if location:
            text_lines.append(", ".join(location))
            
        stats = [f"Outdegree: {node_degree_val}"]
        if 'number_airlines' in data:
            stats.append(f"Airlines: {int(float(data['number_airlines']))}")
        text_lines.append(" | ".join(stats))
        
        node_text.append("<br>".join(text_lines))
        node_degree.append(node_degree_val)

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
                    title="Outdegree",
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
                    title="Outdegree",
                    xanchor="left",
                ),
                line_width=0.5,
            ),
        )

    # ------------------------------------------------------------------
    # Assemble figure
    # ------------------------------------------------------------------
    fig_layout = go.Layout(
        title=dict(
            text=f"Global Airport Network ({layout.capitalize()} layout)",
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
            output_path = PUBLIC_DATA_DIR / "global-air-transportation-network-plotly-geographic.html"
        elif layout == "globe":
            output_path = PUBLIC_DATA_DIR / "global-air-transportation-network-plotly-globe.html"
        else:
            output_path = PUBLIC_DATA_DIR / "global-air-transportation-network-plotly-graph.html"

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

    fig.write_html(str(output_path), config={"scrollZoom": True}, post_script=custom_js)

    if verbose:
        print(f"Interactive Plotly graph saved to {output_path.resolve()}")

    return str(output_path.resolve())


if __name__ == "__main__":
    visualize_graph_plotly(verbose=True)
