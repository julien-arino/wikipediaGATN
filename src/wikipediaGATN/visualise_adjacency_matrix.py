import networkx as nx
from scipy.sparse import load_npz
from .paths import PUBLIC_DATA_DIR
import plotly.graph_objects as go

def visualize_graph_plotly():
    matrix_path = PUBLIC_DATA_DIR + "/adjacency_matrix.npz"
    nodes_path = PUBLIC_DATA_DIR + "/nodes.txt"

    matrix = load_npz(matrix_path)

    with open(nodes_path, "r", encoding="utf-8") as f:
        nodes = [line.strip() for line in f]

    G = nx.from_scipy_sparse_array(matrix, create_using=nx.DiGraph)
    mapping = {i: code for i, code in enumerate(nodes)}
    G = nx.relabel_nodes(G, mapping)

    pos = nx.spring_layout(G, k=0.15, iterations=20)

    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines')

    node_x = []
    node_y = []
    node_text = []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=node_text,
        textposition="top center",
        hoverinfo='text',
        marker=dict(
            showscale=False,
            color='blue',
            size=10,
            line_width=1))

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title='Airport Outbound Connections',
                        title_x=0.5,
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20,l=5,r=5,t=40),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                   )
    output_file = PUBLIC_DATA_DIR + "/airport_graph_plotly.html"
    fig.write_html(output_file)
    print(f"Interactive Plotly graph saved to {output_file}")

if __name__ == "__main__":
    visualize_graph_plotly()
