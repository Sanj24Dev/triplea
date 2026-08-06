import pandas as pd
import matplotlib.pyplot as plt
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

INPUT=f"{FOLDER}/game_outcome.csv"
DEMOGRAPHICS_CSV = f"{FOLDER}/player_info.csv"

df = pd.read_csv(INPUT)

df_demo = pd.read_csv(DEMOGRAPHICS_CSV)

outcome_counts = df['outcome'].value_counts()
plt.figure(figsize=(6,4))
plt.bar(outcome_counts.index, outcome_counts.values, color=['green','red'])
plt.ylabel("Number of games")
plt.title("Game Outcomes")
plt.savefig(f"{FOLDER}/win_vs_lost.png")
plt.close()
print(f"Plot saved {FOLDER}/win_vs_lost.png")

plt.figure(figsize=(8,5))
for outcome, color in zip(['won','lost'], ['green','red']):
    subset = df[df['outcome'] == outcome]
    plt.scatter(subset['game'], subset['rounds_played'], label=outcome, color=color)

plt.xlabel("Game")
plt.ylabel("Rounds played")
plt.title("Rounds Played per Game by Outcome")
plt.legend()
plt.savefig(f"{FOLDER}/outcome_vs_rounds.png")
plt.close()
print(f"Plot saved {FOLDER}/outcome_vs_rounds.png")




df = df.merge(df_demo, on="game")
player_colors = {
    "Russians": "brown",
    "Italians": "green",
    "Germans": "grey",
    "Chinese": "purple",
}

plt.figure(figsize=(8, 5))

# If you want games on x-axis but colored by player:
for player, color in player_colors.items():
    subset = df[df["player"] == player]
    if subset.empty:
        continue
    plt.scatter(subset["game"], subset["rounds_played"], label=player, color=color)

plt.xlabel("Game")
plt.ylabel("Rounds played")
plt.title("Rounds Played per Game by Player")
plt.legend(title="Player")
plt.savefig(f"{FOLDER}/player_vs_rounds.png", dpi=300, bbox_inches="tight")
plt.close()
print(f"Plot saved {FOLDER}/player_vs_rounds.png")



df["win"] = (df["outcome"] == "won").astype(int)

summary = (
    df.groupby("player")
      .agg(
          games=("win", "count"),
          wins=("win", "sum"),
          win_rate=("win", "mean")
      )
)

ax = summary["win_rate"].plot(kind="bar", figsize=(7,5))
ax.set_ylim(0,1)
ax.set_ylabel("Win Rate")
# ax.set_title("Win Rate by Player (n varies)")

for i, (idx, row) in enumerate(summary.iterrows()):
    ax.text(i, row.win_rate + 0.02, f"n={row.games}", ha="center")
plt.xticks(rotation=30)   
plt.savefig(f"{FOLDER}/outcome_vs_demographics.png")
plt.close()
print(f"Plot saved {FOLDER}/outcome_vs_demographics.png")


