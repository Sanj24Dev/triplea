import pandas as pd
import matplotlib.pyplot as plt

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder

FOLDER = f"{main_folder}/metrics"
COMBAT_CSV = f"{FOLDER}/combat_quality.csv"
OUTCOME_CSV = f"{FOLDER}/game_outcome.csv"  # Adjust filename

df_combat = pd.read_csv(COMBAT_CSV)
df_outcome = pd.read_csv(OUTCOME_CSV)

df_combat["pu_gain"] = df_combat.groupby("game")["pu_after"].diff()
df_combat["pu_gain"] = df_combat["pu_gain"].fillna(0) 
df_combat["terr_gain"] = df_combat["territories_after"] - df_combat["territories_before"]

# Merge with outcomes
df = df_combat.merge(df_outcome, on="game", how="left")

# Plot 1: Separate line per game
fig, axes = plt.subplots(2, 2, figsize=(15, 10))

# Territory gains over time, colored by outcome
for game_num in df["game"].unique():
    game_data = df[df["game"] == game_num]
    outcome = game_data["outcome"].iloc[0]  # 'win' or 'loss'
    color = 'green' if outcome == 'won' else 'red'
    alpha = 0.6
    
    axes[0, 0].plot(game_data["round"], game_data["terr_gain"], 
                    color=color, alpha=alpha, linewidth=1)

axes[0, 0].set_xlabel("Round")
axes[0, 0].set_ylabel("Territories Gained")
axes[0, 0].set_title("Territory Gains per Combat (Green=Win, Red=Loss)")
axes[0, 0].axhline(y=0, color='black', linestyle='--', linewidth=0.5)
axes[0, 0].grid(True, alpha=0.3)

# PU gains over time
for game_num in df["game"].unique():
    game_data = df[df["game"] == game_num]
    outcome = game_data["outcome"].iloc[0]
    color = 'green' if outcome == 'won' else 'red'
    
    axes[0, 1].plot(game_data["round"], game_data["pu_gain"], 
                    color=color, alpha=0.6, linewidth=1)

axes[0, 1].set_xlabel("Round")
axes[0, 1].set_ylabel("PU Gained")
axes[0, 1].set_title("PU Gains per Combat")
axes[0, 1].axhline(y=0, color='black', linestyle='--', linewidth=0.5)
axes[0, 1].grid(True, alpha=0.3)

# Cumulative territories over time
for game_num in df["game"].unique():
    game_data = df[df["game"] == game_num].sort_values("round")
    outcome = game_data["outcome"].iloc[0]
    color = 'green' if outcome == 'won' else 'red'
    
    axes[1, 0].plot(game_data["round"], game_data["territories_after"], 
                    color=color, alpha=0.6, linewidth=1.5)

axes[1, 0].set_xlabel("Round")
axes[1, 0].set_ylabel("Total Territories Controlled")
axes[1, 0].set_title("Territory Control Trajectory")
axes[1, 0].grid(True, alpha=0.3)

# Cumulative PU over time
for game_num in df["game"].unique():
    game_data = df[df["game"] == game_num].sort_values("round")
    outcome = game_data["outcome"].iloc[0]
    color = 'green' if outcome == 'won' else 'red'
    
    axes[1, 1].plot(game_data["round"], game_data["pu_after"], 
                    color=color, alpha=0.6, linewidth=1.5)

axes[1, 1].set_xlabel("Round")
axes[1, 1].set_ylabel("Total PUs")
axes[1, 1].set_title("PU Balance Trajectory")
axes[1, 1].grid(True, alpha=0.3)

# Add legend
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], color='green', lw=2, label='Won Games'),
    Line2D([0], [0], color='red', lw=2, label='Lost Games')
]
fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98))

plt.tight_layout()
plt.savefig(f"{FOLDER}/combat_quality_trajectories.png", dpi=300, bbox_inches='tight')
plt.close()
print(f"Plot saved {FOLDER}/combat_quality_trajectories.png")

import numpy as np

EPS = 1e-6
metrics = []

for game, gdf in df.groupby("game"):
    gdf = gdf.sort_values("round")

    terr_gains = gdf["terr_gain"]
    pu_gains = gdf["pu_gain"]

    avg_terr_gain = terr_gains.mean()
    avg_pu_gain = pu_gains.mean()

    tgc = terr_gains.std() / (abs(avg_terr_gain) + EPS)

    total_positive_gain = terr_gains.clip(lower=0).sum()
    net_gain = gdf["territories_after"].iloc[-1] - gdf["territories_before"].iloc[0]
    srr = net_gain / total_positive_gain if total_positive_gain > 0 else 0.0

    metrics.append({
        "game": game,
        "outcome": gdf["outcome"].iloc[0] if not pd.isna(gdf["outcome"].iloc[0]) else "lost",
        "avg_territory_gain": avg_terr_gain,
        "avg_pu_gain": avg_pu_gain,
        "territory_gain_consistency": tgc,
        "strategic_retention_ratio": srr
    })

df_metrics = pd.DataFrame(metrics)
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

metrics_to_plot = [
    ("avg_territory_gain", "Avg Territory Gain"),
    ("avg_pu_gain", "Avg PU Gain"),
    ("territory_gain_consistency", "Territory Gain Consistency (CV)"),
    ("strategic_retention_ratio", "Strategic Retention Ratio")
]

for ax, (col, title) in zip(axes.flatten(), metrics_to_plot):
    df_metrics.boxplot(
        column=col,
        by="outcome",
        ax=ax,
        grid=False
    )
    ax.set_title(title)
    ax.set_xlabel("Outcome")
    ax.set_ylabel(col)
    
plt.suptitle("Combat Quality Metrics by Game Outcome", fontsize=16)
plt.tight_layout()
plt.savefig(f"{FOLDER}/combat_quality_metrics.png", dpi=300, bbox_inches='tight')
plt.close()
print(f"Plot saved {FOLDER}/combat_quality_metrics.png")


TXT_OUT = f"{FOLDER}/combat_quality_averages.txt"

with open(TXT_OUT, "w") as f:
    f.write("=== Combat Quality Metric Averages ===\n\n")

    for outcome, odf in df_metrics.groupby("outcome"):
        f.write(f"Outcome: {outcome.upper()}\n")
        f.write(f"  Avg Territory Gain: {odf['avg_territory_gain'].mean():.3f}\n")
        f.write(f"  Avg PU Gain: {odf['avg_pu_gain'].mean():.3f}\n")
        f.write(f"  Territory Gain Consistency: {odf['territory_gain_consistency'].mean():.3f}\n")
        f.write(f"  Strategic Retention Ratio: {odf['strategic_retention_ratio'].mean():.3f}\n")
        f.write("\n")

print(f"Averages written to {TXT_OUT}")