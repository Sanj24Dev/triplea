import pandas as pd
import matplotlib.pyplot as plt
import argparse
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

# -----------------------------
# Load data (one CSV per player/port)
# -----------------------------
ports = [5000, 5001, 5002, 5003]
players = ["Russians", "Italians", "Germans", "Chinese"]

dfs = []
for port, player in zip(ports, players):
    df_iter = pd.read_csv(f"{FOLDER}/mcts_efficiency_port{port}.csv")
    df_iter["player"] = player
    dfs.append(df_iter)

df = pd.concat(dfs, ignore_index=True)

# Ensure correct dtypes + sorting
df["game"] = df["game"].astype(int)
df["round"] = df["round"].astype(int)
df["num_iterations"] = pd.to_numeric(df["num_iterations"], errors="coerce")
df = df.dropna(subset=["num_iterations"])
df = df.sort_values(["player", "game", "round"])

# -----------------------------
# Aggregate by (player, round) across games
# -----------------------------
agg = (
    df.groupby(["player", "round"])["num_iterations"]
      .agg(
          mean="mean",
          p25=lambda s: s.quantile(0.25),
          p75=lambda s: s.quantile(0.75),
          n="count"
      )
      .reset_index()
)

# -----------------------------
# Plot: Iterations per Round (mean + IQR), one line per player
# -----------------------------
fig, ax = plt.subplots(figsize=(10, 6))

for player in players:
    sub = agg[agg["player"] == player].sort_values("round")
    ax.plot(sub["round"], sub["mean"], marker="o", label=f"{player} mean")
    ax.fill_between(sub["round"], sub["p25"], sub["p75"], alpha=0.2, label=f"{player} IQR")

ax.set_title("MCTS Iterations per Round (Across Games)")
ax.set_xlabel("Round")
ax.set_ylabel("Iterations")
ax.legend(ncols=2, fontsize=9)
plt.tight_layout()
plt.savefig(f"{FOLDER}/aggregate_game_summary.png")
plt.close()

print(f"Plot saved to {FOLDER}/aggregate_game_summary.png")

# -----------------------------
# Game-wise summary generation (overall + per player)
# -----------------------------
summary_lines = []
summary_lines.append("MCTS Efficiency Summary\n")
summary_lines.append("=" * 60 + "\n\n")

# Overall per game
summary_lines.append("Overall (all players combined)\n")
summary_lines.append("-" * 60 + "\n")
for game_id, gdf in df.groupby("game"):
    summary_lines.append(f"Game {game_id} | total rows={len(gdf)} | rounds={gdf['round'].nunique()}\n")
    summary_lines.append(
        f"  Iterations: mean={gdf['num_iterations'].mean():.2f}, "
        f"min={int(gdf['num_iterations'].min())}, max={int(gdf['num_iterations'].max())}\n"
    )
summary_lines.append("\n")

# Per player per game
summary_lines.append("Per player, per game\n")
summary_lines.append("-" * 60 + "\n")
for (game_id, player), gdf in df.groupby(["game", "player"]):
    summary_lines.append(f"Game {game_id} | {player} | rounds={gdf['round'].nunique()} | decisions={len(gdf)}\n")
    summary_lines.append(
        f"  Iterations: mean={gdf['num_iterations'].mean():.2f}, "
        f"min={int(gdf['num_iterations'].min())}, max={int(gdf['num_iterations'].max())}\n"
    )

summary_path = f"{FOLDER}/efficiency_summary.txt"
with open(summary_path, "w") as f:
    f.writelines(summary_lines)

print(f"Summary written to {summary_path}")
