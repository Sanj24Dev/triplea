import pandas as pd
import matplotlib.pyplot as plt
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

INPUT=f"{FOLDER}/game_outcome.csv"

df = pd.read_csv(INPUT)

plt.figure(figsize=(8, 5))

summary = (
    df.groupby("winner")
      .agg(
          wins=("winner", "count")
      )
)
summary["win_rate"] = summary["wins"] / len(df)


fig, ax = plt.subplots(figsize=(6,5))

bottom = 0
for player, row in summary.iterrows():
    ax.bar(
        "All Games",               # single x label
        row["win_rate"],
        bottom=bottom,
        label=f"{player} (r={row['win_rate']*100}%)"
    )
    bottom += row["win_rate"]

ax.set_ylim(0, 1)
ax.set_ylabel("Win Rate")
ax.legend()
plt.savefig(f"{FOLDER}/outcome_vs_demographics.png")
plt.close()

print(f"Plot saved {FOLDER}/outcome_vs_demographics.png")
