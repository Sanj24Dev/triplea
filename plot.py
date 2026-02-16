import pandas as pd
import matplotlib.pyplot as plt

# Load CSV file
# Example: data.csv with columns: game, round, num_iterations, value
df = pd.read_csv("multi_front_attack/metrics/mcts_efficiency.csv")

# Check columns
print(df.head())

# Plot each game separately
games = df["game"].unique()

for game in games:
    game_df = df[df["game"] == game].sort_values(by="round")

    plt.figure()
    plt.plot(game_df["round"], game_df["value"])
    plt.xlabel("Round")
    plt.ylabel("Value")
    plt.title(f"Round vs Value - {game}")
    plt.grid(True)
    plt.show()

# Optional: Plot all games on one figure
plt.figure()
for game in games:
    game_df = df[df["game"] == game].sort_values(by="round")
    plt.plot(game_df["round"], game_df["value"], label=game)

plt.xlabel("Round")
plt.ylabel("Value")
plt.title("Round vs Value (All Games)")
plt.legend()
plt.grid(True)
plt.show()
