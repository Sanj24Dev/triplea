import pandas as pd
import matplotlib.pyplot as plt
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

# Load data
df = pd.read_csv(f"{FOLDER}/mcts_efficiency.csv")

# -----------------------------
# Select game with max iterations
# -----------------------------
game_iterations = df.groupby("game")["num_iterations"].max()
selected_game = game_iterations.idxmax()

df_game = df[df["game"] == selected_game].copy()

# -----------------------------
# Plot ONLY selected game
# -----------------------------
fig, axs = plt.subplots(2, 2, figsize=(10, 8))

axs[0, 0].plot(df_game["round"], df_game["num_iterations"], marker='o')
axs[0, 0].set_title(f"Iterations per Round (Game {selected_game})")

axs[0, 1].plot(df_game["round"], df_game["root_node_visits"], label="Root")
axs[0, 1].plot(df_game["round"], df_game["best_node_visits"], label="Best")
axs[0, 1].set_title("Visits")
axs[0, 1].legend()

axs[1, 0].plot(df_game["round"], df_game["best_node_value"], marker='o')
axs[1, 0].set_title("Best Node Value")

df_game["exploration"] = df_game["explored"] / df_game["total_actions"]
axs[1, 1].plot(df_game["round"], df_game["exploration"], marker='o')
axs[1, 1].set_title("Exploration coverage")

plt.tight_layout()
plt.savefig(f"{FOLDER}/efficiency_plot.png")
plt.close()


import numpy as np

# =============================
# Aggregate analysis across games
# =============================

# Ensure efficiency exists
df["efficiency"] = df["best_node_visits"] / df["num_iterations"]

# Aggregate by round position across games
agg = df.groupby("round")

mean_iters = agg["num_iterations"].mean()
p25_iters = agg["num_iterations"].quantile(0.25)
p75_iters = agg["num_iterations"].quantile(0.75)

mean_best_visits = agg["best_node_visits"].mean()
std_best_visits = agg["best_node_visits"].std()
median_best_visits = agg["best_node_visits"].median()

# -----------------------------
# Aggregate summary figure
# -----------------------------
fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)

# --- 1. Iterations per round (mean + IQR) ---
axs[0].plot(mean_iters.index, mean_iters.values, label="Mean", marker='o')
axs[0].fill_between(
    mean_iters.index,
    p25_iters.values,
    p75_iters.values,
    alpha=0.3,
    label="25–75 percentile"
)
axs[0].set_title("Iterations per Round (Across Games)")
axs[0].set_ylabel("Iterations")
axs[0].legend()

# --- 2. Best node visits (mean ± std, median) ---
axs[1].plot(
    mean_best_visits.index,
    mean_best_visits.values,
    label="Mean",
    marker='o'
)
axs[1].fill_between(
    mean_best_visits.index,
    mean_best_visits - std_best_visits,
    mean_best_visits + std_best_visits,
    alpha=0.3,
    label="±1 Std Dev"
)
axs[1].plot(
    median_best_visits.index,
    median_best_visits.values,
    linestyle="--",
    label="Median"
)
axs[1].set_title("Best Node Visits per Round (Across Games)")
axs[1].set_ylabel("Visits")
axs[1].legend()

# --- 3. Decision value distributions (early / mid / late) ---
rounds = sorted(df["round"].unique())
early = rounds[len(rounds) // 10]
mid = rounds[len(rounds) // 2]
late = rounds[-len(rounds) // 10 - 1]

value_data = [
    df[df["round"] == early]["best_node_value"],
    df[df["round"] == mid]["best_node_value"],
    df[df["round"] == late]["best_node_value"],
]

axs[2].boxplot(value_data, labels=[
    f"Early (r={early})",
    f"Mid (r={mid})",
    f"Late (r={late})"
])
axs[2].set_title("Best Node Value Distribution (Across Games)")
axs[2].set_ylabel("Decision Value")

axs[2].set_xlabel("Game Phase")

plt.tight_layout()
plt.savefig(f"{FOLDER}/aggregate_game_summary.png")
plt.close()

print(f"Aggregate summary plot saved to {FOLDER}/aggregate_game_summary.png")

# -----------------------------
# Game-wise summary generation
# -----------------------------
summary_lines = []
summary_lines.append("MCTS Efficiency Summary (Game-wise)\n")
summary_lines.append("=" * 40 + "\n\n")

per_game_stats = []
for game_id, gdf in df.groupby("game"):
    gdf = gdf.copy()
    gdf["exploration_coverage"] = gdf["explored"] / gdf["total_actions"]

    summary_lines.append(f"Game {game_id}\n")
    summary_lines.append("-" * 20 + "\n")

    summary_lines.append(f"Total rounds: {gdf['round'].nunique()}\n")

    summary_lines.append(
        f"Iterations per round:\n"
        f"  Mean: {gdf['num_iterations'].mean():.2f}\n"
        f"  Min : {gdf['num_iterations'].min()}\n"
        f"  Max : {gdf['num_iterations'].max()}\n"
    )

    summary_lines.append(
        f"Exploration_coverage (actions_explored / total_actions):\n"
        f"  Mean: {gdf['exploration_coverage'].mean():.4f}\n"
        f"  Min : {gdf['exploration_coverage'].min():.4f}\n"
        f"  Max : {gdf['exploration_coverage'].max():.4f}\n"
    )

    summary_lines.append(
        f"Avg Tree depth per round:\n"
        f"  Mean: {gdf['avg_depth'].mean():.4f}\n"
        f"  Min : {gdf['avg_depth'].min():.4f}\n"
        f"  Max : {gdf['avg_depth'].max():.4f}\n"
    )

    per_game_stats.append({
        "game": game_id,
        "avg_iterations": gdf["num_iterations"].mean(),
        "avg_exploration_coverage": gdf["exploration_coverage"].mean(),
        "avg_depth": gdf["avg_depth"].mean()
    })

overall_df = pd.DataFrame(per_game_stats)

overall_avg_iter = overall_df["avg_iterations"].mean()
overall_avg_exp = overall_df["avg_exploration_coverage"].mean()
overall_avg_depth = overall_df["avg_depth"].mean()

summary_lines.append("\nOVERALL AVERAGES (Across Games)\n")
summary_lines.append("=" * 30 + "\n")

summary_lines.append(
    f"Iterations per round (game-averaged):\n"
    f"  Mean: {overall_avg_iter:.2f}\n"
    f"  Min: {df["num_iterations"].min()}\n"
    f"  Max: {df["num_iterations"].max()}\n"
)

df["exploration_coverage"] = (df["explored"] / df["total_actions"])
summary_lines.append(
    f"Exploration coverage (game-averaged):\n"
    f"  Mean: {overall_avg_exp:.2f}\n"
    f"  Min: {df["exploration_coverage"].min():.2f}\n"
    f"  Max: {df["exploration_coverage"].max()}\n"
)

summary_lines.append(
    f"Avg tree depth per round (game-averaged):\n"
    f"  Mean: {overall_avg_depth:.2f}\n"
    f"  Min: {df["avg_depth"].min()}\n"
    f"  Max: {df["avg_depth"].max()}\n"
)


# -----------------------------
# Write summary
# -----------------------------
summary_path = f"{FOLDER}/efficiency_summary.txt"
with open(summary_path, "w") as f:
    f.writelines(summary_lines)

print(f"Summary written to {summary_path}")
print(f"Plots generated for Game {selected_game}")
