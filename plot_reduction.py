import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

INPUT_FILE = "smart_root_dumb_tree/metrics/reduction.csv"
OUTPUT_FILE = "smart_root_dumb_tree/metrics/reduction_summary.txt"

df = pd.read_csv(INPUT_FILE)

# === COMPUTE ROUND-WISE METRICS ===
df["reduction"] = np.where(
    df["total_moves"] == 0,
    0,
    (df["total_moves"] - df["pruned_moves"]) / df["total_moves"]
)
df["reduction_percent"] = df["reduction"] * 100

# === GAME-WISE SUMMARY (AVG OF ROUND-WISE REDUCTION) ===
game_summary = (
    df.groupby("game")
      .agg(
          rounds=("round", "count"),
          avg_round_reduction=("reduction", "mean"),
          avg_round_reduction_percent=("reduction_percent", "mean")
      )
      .reset_index()
)
# Compute overall averages (across all games)
overall_row = pd.DataFrame([{
    "game": "OVERALL",
    "rounds": game_summary["rounds"].mean(),  # or sum(), depending on intent
    "avg_round_reduction": game_summary["avg_round_reduction"].mean(),
    "avg_round_reduction_percent": game_summary["avg_round_reduction_percent"].mean()
}])

# Append to summary
game_summary = pd.concat([game_summary, overall_row], ignore_index=True)

# Identify game with highest avg round-wise reduction
best_game = game_summary.loc[
    game_summary["avg_round_reduction_percent"].idxmax(), "game"
]

df_best = df[df["game"] == best_game].copy()

text_output = []

text_output.append("=== Round-wise Reduction Data ===\n")
text_output.append(df[[
    "game", "round", "total_moves", "pruned_moves", "reduction_percent"
]].to_string(index=False))

text_output.append("\n\n=== Game-wise Summary (Avg of Round-wise Reduction) ===\n")
text_output.append(game_summary.to_string(index=False))

# text_output.append(
#     f"\n\nGame with highest average round-wise reduction: "
#     f"Game {best_game} "
#     f"({game_summary.loc[game_summary['game']==best_game, 'avg_round_reduction_percent'].values[0]:.2f}%)\n"
# )

with open(OUTPUT_FILE, "w") as f:
    f.write("\n".join(text_output))

plt.figure()
plt.plot(
    df_best["round"],
    df_best["reduction_percent"],
    marker="o"
)

plt.xlabel("Round")
plt.ylabel("Reduction (%)")
plt.title(f"Round-wise Action Space Reduction (Game {best_game})")
plt.grid(True)
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/reduction_per_round.png")
plt.close()

plt.figure()
plt.plot(df_best["round"], df_best["total_moves"], marker="o", label="Total moves")
plt.plot(df_best["round"], df_best["pruned_moves"], marker="o", label="Pruned moves")

plt.xlabel("Round")
plt.ylabel("Moves")
plt.title(f"Total vs Pruned Moves (Game {best_game})")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/total_vs_pruned.png")
plt.close()
