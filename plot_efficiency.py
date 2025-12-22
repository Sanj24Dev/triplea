import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("smart_root_dumb_tree/metrics/mcts_efficiency.csv")


fig, axs = plt.subplots(2, 2, figsize=(10, 8))

axs[0,0].plot(df["round"], df["num_iterations"], marker='o')
axs[0,0].set_title("Iterations per Round")

axs[0,1].plot(df["round"], df["root_node_visits"], label="Root")
axs[0,1].plot(df["round"], df["best_node_visits"], label="Best")
axs[0,1].set_title("Visits")
axs[0,1].legend()

axs[1,0].plot(df["round"], df["best_node_value"], marker='o')
axs[1,0].set_title("Best Node Value")

# check
df["efficiency"] = df["best_node_visits"] / df["num_iterations"]
axs[1,1].plot(df["round"], df["efficiency"], marker='o')
axs[1,1].set_title("Efficiency")

plt.tight_layout()
plt.savefig("smart_root_dumb_tree/metrics/efficiency_plot.png")


summary_lines = []

summary_lines.append("MCTS Efficiency Summary\n")
summary_lines.append("=" * 30 + "\n")

summary_lines.append(f"Total rounds: {df['round'].nunique()}\n")

summary_lines.append(
    f"Iterations per round:\n"
    f"  Mean: {df['num_iterations'].mean():.2f}\n"
    f"  Min : {df['num_iterations'].min()}\n"
    f"  Max : {df['num_iterations'].max()}\n\n"
)

summary_lines.append(
    f"Efficiency (best_node_visits / num_iterations):\n"
    f"  Mean: {df['efficiency'].mean():.4f}\n"
    f"  Min : {df['efficiency'].min():.4f}\n"
    f"  Max : {df['efficiency'].max():.4f}\n\n"
)

best_round = df.loc[df["efficiency"].idxmax(), "round"]
summary_lines.append(
    f"Peak efficiency of {df['efficiency'].max():.4f} "
    f"observed at round {best_round}\n\n"
)

# Write to file
summary_path = "smart_root_dumb_tree/metrics/efficiency_summary.txt"
with open(summary_path, "w") as f:
    f.writelines(summary_lines)

print(f"Summary written to {summary_path}")
