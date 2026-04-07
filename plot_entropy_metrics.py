import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"


# need to copy ythe contents to this file, as the main file keeps getting modified during the training
metrics_df = pd.read_csv("for_plot_entropy.csv")       # your first file
elim_df    = pd.read_csv("for_plot_value.csv")   # your second file


DEPTH = 1
ROLLING_WINDOW = 3   # small window given limited data; increase with more data

# Z_META = {
#      1.0:  {"color": "#E24B4A", "label": "z=1.0  (winner)"},
#      0.333:{"color": "#EF9F27", "label": "z=0.33 (2nd)"},
#     -0.333:{"color": "#378ADD", "label": "z=−0.33 (3rd)"},
#     -1.0:  {"color": "#888780", "label": "z=−1.0  (4th)"},
# }

Z_META = {
     1.0:  {"color": "#E24B4A", "label": "z=1.0  (winner)"},
    -1.0:  {"color": "#888780", "label": "z=−1.0  (4th)"},
}

METRICS = ["entropy_ratio", "q_spread", "concentration"]


avg_rounds = metrics_df.groupby("game")["round"].max().mean()
metrics_df["global_round"] = (
    (metrics_df["game"] - 1) * avg_rounds + metrics_df["round"]
)

# elim_df has one row per (game, player) with their z value
elim_lookup = elim_df[["game", "player", "z"]].copy()
elim_lookup["z_rounded"] = elim_lookup["z"].round(3)

metrics_df = metrics_df.merge(
    elim_lookup[["game", "player", "z", "z_rounded"]],
    left_on=["game", "port"],
    right_on=["game", "player"],
    how="left",
)

df_d1 = metrics_df[metrics_df["depth"] == DEPTH].copy()

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle(f"MCTS search metrics over time  (depth={DEPTH})", fontsize=13, y=1.01)

for z_val, meta in Z_META.items():
    color = meta["color"]
    subset = df_d1[df_d1["z_rounded"] == round(z_val, 3)].sort_values("global_round")

    for ax, metric in zip(axes, METRICS):
        ax.scatter(
            subset["global_round"], subset[metric],
            color=color, alpha=0.35, s=20, zorder=2,
        )
        if len(subset) >= 2:
            rolled = (
                subset.set_index("global_round")[metric]
                .rolling(ROLLING_WINDOW, min_periods=1)
                .mean()
            )
            ax.plot(rolled, color=color, linewidth=1.8, zorder=3)

for ax, metric in zip(axes, METRICS):
    ax.set_ylabel(metric, fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)

axes[-1].set_xlabel("global round", fontsize=11)

handles = [
    mlines.Line2D([], [], color=meta["color"], linewidth=2, label=meta["label"])
    for meta in Z_META.values()
]
axes[0].legend(handles=handles, fontsize=9, framealpha=0.3)

plt.tight_layout()
plt.savefig(f"{FOLDER}/mcts_metrics.png", dpi=150, bbox_inches="tight")
plt.close()