import pandas as pd
import matplotlib.pyplot as plt
import argparse
import numpy as np
import os

# -----------------------------
# Args
# -----------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

os.makedirs(FOLDER, exist_ok=True)

# -----------------------------
# Load Combat Logs
# -----------------------------
ports = [5000, 5001, 5002, 5003]
players = ["Russians", "Italians", "Germans", "Chinese"]

dfs = []
for port, player in zip(ports, players):
    df_iter = pd.read_csv(f"{FOLDER}/combat_quality_port{port}.csv")
    df_iter["player"] = player
    dfs.append(df_iter)

df = pd.concat(dfs, ignore_index=True)

# -----------------------------
# Preprocessing
# -----------------------------
df["game"] = df["game"].astype(int)
df["round"] = df["round"].astype(int)

df = df.sort_values(["player", "game", "round"])

df["pu_gain"] = (
    df.groupby(["game", "player"])["pu_after"]
      .diff()
      .fillna(0)
)

df["terr_gain"] = df["territories_after"]

# ============================================================
# 1️⃣ Single Trajectory Figure (All Players Together)
# ============================================================

fig, axes = plt.subplots(1, 2, figsize=(10, 5))

colors = {
    "Russians": "blue",
    "Italians": "orange",
    "Germans": "green",
    "Chinese": "red"
}

for player in players:
    df_p = df[df["player"] == player]

    # Average per round across games
    agg = df_p.groupby("round").agg({
        "terr_gain": "mean",
        "pu_gain": "mean",
        "territories_after": "mean",
        "pu_after": "mean"
    }).reset_index()

    # axes[0, 0].plot(agg["round"], agg["terr_gain"], label=player, color=colors[player])
    # axes[0, 1].plot(agg["round"], agg["pu_gain"], label=player, color=colors[player])
    axes[0].plot(agg["round"], agg["territories_after"], label=player, color=colors[player])
    axes[1].plot(agg["round"], agg["pu_after"], label=player, color=colors[player])

# axes[0, 0].set_title("Avg Territory Gain per Round")
# axes[0, 1].set_title("Avg PU Gain per Round")
axes[0].set_title("Avg Territory Control")
axes[1].set_title("Avg PU Balance")

for ax in axes.flatten():
    ax.set_xlabel("Round")
    ax.grid(True, alpha=0.3)

# axes[0, 0].set_ylabel("Territory Gain")
# axes[0, 1].set_ylabel("PU Gain")
axes[0].set_ylabel("Territories")
axes[1].set_ylabel("PUs")

fig.legend(players, loc="upper right")
plt.tight_layout()
plt.savefig(f"{FOLDER}/combat_quality_trajectories.png", dpi=300)
plt.close()

print("Saved combat_quality_trajectories.png")

# ============================================================
# 2️⃣ Single Metrics Comparison Figure
# ============================================================

EPS = 1e-6
metrics = []

for (game, player), gdf in df.groupby(["game", "player"]):
    gdf = gdf.sort_values("round")

    terr_gains = gdf["terr_gain"]
    pu_gains = gdf["pu_gain"]

    avg_terr_gain = terr_gains.mean()
    avg_pu_gain = pu_gains.mean()
    max_gain = terr_gains.max()
    tgc = 1 - (terr_gains.std() / (max_gain + EPS)) if max_gain > 0 else 0

    # total_positive_gain = terr_gains.clip(lower=0).sum()
    # net_gain = (
    #     gdf["territories_after"].iloc[-1]
    #     - gdf["territories_before"].iloc[0]
    # )
    # srr = net_gain / total_positive_gain if total_positive_gain > 0 else 0.0

    max_territories = gdf["territories_after"].max()
    end_territories = gdf["territories_after"].iloc[-1]
    srr = end_territories / (max_territories + EPS)

    metrics.append({
        "game": game,
        "player": player,
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
    df_metrics.boxplot(column=col, by="player", ax=ax, grid=False)
    ax.set_title(title)
    ax.set_xlabel("Player")
    ax.set_ylabel(col)

plt.suptitle("Combat Quality Metrics Comparison", fontsize=16)
plt.tight_layout()
plt.savefig(f"{FOLDER}/combat_quality_metrics.png", dpi=300)
plt.close()

print("Saved combat_quality_metrics.png")

# ============================================================
# 3️⃣ Single Summary File
# ============================================================

TXT_OUT = f"{FOLDER}/combat_quality_averages.txt"

with open(TXT_OUT, "w") as f:
    f.write("=== Combat Quality Averages By Player ===\n\n")
    for player in players:
        pdf = df_metrics[df_metrics["player"] == player]
        f.write(f"{player}\n")
        f.write(f"  Avg Territory Gain: {pdf['avg_territory_gain'].mean():.3f}\n")
        f.write(f"  Avg PU Gain: {pdf['avg_pu_gain'].mean():.3f}\n")
        f.write(f"  Territory Gain Consistency: {pdf['territory_gain_consistency'].mean():.3f}\n")
        f.write(f"  Strategic Retention Ratio: {pdf['strategic_retention_ratio'].mean():.3f}\n\n")

print("Saved combat_quality_averages.txt")
