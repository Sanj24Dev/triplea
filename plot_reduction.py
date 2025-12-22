import pandas as pd
import matplotlib.pyplot as plt

INPUT_FILE = "smart_root_dumb_tree/metrics/reduction.csv"
OUTPUT_FILE = "smart_root_dumb_tree/metrics/reduction_summary.txt"

df = pd.read_csv(INPUT_FILE)

# === COMPUTE METRICS ===
df["reduction"] = (df["total_moves"] - df["pruned_moves"])/ df["total_moves"]
df["reduction_percent"] = df["reduction"] * 100

# Summary per game
game_summary = df.groupby("game").agg(
    avg_total_moves=("total_moves", "mean"),
    avg_pruned=("pruned_moves", "mean"),
    avg_reduction=("reduction", "mean"),
    avg_reduction_percent=("reduction_percent", "mean")
).reset_index()

text_output = []
text_output.append("=== Overall Data ===")
text_output.append(df.to_string(index=False))
text_output.append("\n=== Game Summary ===")
text_output.append(game_summary.to_string(index=False))
text_output_str = "\n".join(text_output)

# Print to console
# print(text_output_str)

# Save to text file
with open(OUTPUT_FILE, "w") as f:
    f.write(text_output_str)


# === PLOTS ===

# 1. Reduction per round (per game)
plt.figure()
for g, gdf in df.groupby("game"):
    plt.plot(gdf["round"], gdf["reduction_percent"], marker="o", label=f"Game {g}")

plt.xlabel("Round")
plt.ylabel("Reduction (%)")
plt.title("Pruned Moves Reduction per Round")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/reduction_per_round.png")
# plt.show()

# 2. Avg reduction per game
plt.figure()
plt.bar(game_summary["game"], game_summary["avg_reduction_percent"])
plt.xlabel("Game")
plt.ylabel("Average Reduction (%)")
plt.title("Average Move Reduction Across Games")
plt.grid(True, axis="y")
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/avg_reduction_per_game.png")
# plt.show()

# 3. Total vs Pruned Moves (optional)
plt.figure()
plt.plot(df["round"], df["total_moves"], marker="o", label="Total moves")
plt.plot(df["round"], df["pruned_moves"], marker="o", label="Pruned moves")
plt.xlabel("Round")
plt.ylabel("Moves")
plt.title("Total vs Pruned Moves")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/total_vs_pruned.png")
plt.show()

