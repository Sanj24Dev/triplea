import pandas as pd
import matplotlib.pyplot as plt

FOLDER="smart_root_dumb_tree/metrics"
INPUT=f"{FOLDER}/game_outcome.csv"

df = pd.read_csv(INPUT)

outcome_counts = df['outcome'].value_counts()
plt.figure(figsize=(6,4))
plt.bar(outcome_counts.index, outcome_counts.values, color=['red','green'])
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
