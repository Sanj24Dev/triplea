import pickle, os
import matplotlib.pyplot as plt
import networkx as nx
from ctf_graph import CaptureTheFlag, OWNER_COLORS

def render_snapshots(snap_path, model_name, depths=None):
    with open(snap_path, "rb") as f:
        data = pickle.load(f)

    template_data = data["template"]
    snapshots = data["snapshots"]

    if template_data is None:
        print("No template data in snapshot.")
        return

    # Reconstruct the networkx graph from saved edges/nodes/pos
    G = nx.Graph()
    G.add_nodes_from(template_data["nodes"])
    G.add_edges_from(template_data["edges"])
    pos = template_data["pos"]

    for snap in snapshots:
        if depths is not None and snap["depth"] not in depths:
            continue

        fig, ax = plt.subplots(figsize=(10, 8))
        try:
            colors = [
                OWNER_COLORS.get(snap["territories"][node]["owner"], "lightgray")
                for node in G.nodes
            ]
            nx.draw_networkx_nodes(G, pos, ax=ax, node_color=colors, node_size=800)
            nx.draw_networkx_edges(G, pos, ax=ax)
            nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)

            for node in G.nodes:
                t = snap["territories"][node]
                if not t["units"]:
                    continue
                unit_lines = "\n".join(
                    f"{u['quantity']} {u['unit_type']} ({u['owner']})" for u in t["units"]
                )
                x, y = pos[node]
                ax.text(x, y + 0.08, unit_lines, fontsize=8, ha="left", va="center")

            ax.set_title(
                f"game {snap['game_num']} round {snap['round']} "
                f"iter {snap['iter']} depth {snap['depth']} "
                f"player {snap['current_player']}",
                fontsize=10
            )
            img_file = (f"{model_name}/move_sim/"
                        f"graph_g{snap['game_num']}_r{snap['round']}"
                        f"_iter{snap['iter']}_d{snap['depth']}.png")
            os.makedirs(os.path.dirname(img_file), exist_ok=True)
            fig.savefig(img_file, dpi=300, bbox_inches="tight")
            print(f"Saved {img_file}")
        finally:
            plt.close(fig)

import glob
for path in glob.glob("mcts_heuristic_v2/snapshots/g4_r21*.pkl"):
    render_snapshots(path, "mcts_heuristic_v2")


# path = "mcts_heuristic_v2/snapshots/g4_r16_iter1.pkl"
# render_snapshots(path, "mcts_heuristic_v2")