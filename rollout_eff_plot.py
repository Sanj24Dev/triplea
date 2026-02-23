import os
import pandas as pd
import matplotlib.pyplot as plt
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"
OUT_DIR = FOLDER
os.makedirs(OUT_DIR, exist_ok=True)

COL_ATTACKS = "terr_attacked_in_round (actions taken)"

# ---------------------------------------
# Load all port files
# ---------------------------------------
ports = [5000, 5001, 5002, 5003]
players = ["Russians", "Italians", "Germans", "Chinese"]

dfs = []
for port, player in zip(ports, players):
    path = f"{FOLDER}/rollout_efficiency_port{port}.csv"
    df_iter = pd.read_csv(path)
    df_iter["player"] = player  # unify column name
    dfs.append(df_iter)

df = pd.concat(dfs, ignore_index=True)

# ---------------------------------------
# Basic hygiene
# ---------------------------------------
df["depth"] = pd.to_numeric(df["depth"], errors="coerce")
df[COL_ATTACKS] = pd.to_numeric(df[COL_ATTACKS], errors="coerce")
df = df.dropna(subset=["depth", "current_player", COL_ATTACKS])

# ---------------------------------------
# Plot: Avg attacks vs depth
# ---------------------------------------
agg = (
    df.groupby(["depth", "current_player"])[COL_ATTACKS]
      .mean()
      .reset_index()
      .sort_values(["current_player", "depth"])
)

fig, ax = plt.subplots(figsize=(10, 6))

for player in players:
    d = agg[agg["current_player"] == player]
    if not d.empty:
        ax.plot(d["depth"], d[COL_ATTACKS], marker="o", label=player)

ax.set_title("Average combat actions per turn vs rollout depth")
ax.set_xlabel("Rollout depth")
ax.set_ylabel("Avg # combat actions")
ax.legend()
plt.tight_layout()

out1 = f"{OUT_DIR}/avg_attacks_vs_depth.png"
plt.savefig(out1, dpi=200)
plt.close()

print("Saved:", out1)



# # -------------------------------------------------------
# # Plot 3 (optional): per-game comparison (Game 1 vs Game 2)
# # -------------------------------------------------------
# if "game" in df.columns:
#     for g in sorted(df["game"].unique()):
#         gdf = df[df["game"] == g]
#         gagg = (
#             gdf.groupby(["depth", "current_player"])[COL_ATTACKS]
#                .mean()
#                .reset_index()
#                .sort_values(["current_player", "depth"])
#         )

#         fig, ax = plt.subplots(figsize=(10, 6))
#         for player in gagg["current_player"].unique():
#             d = gagg[gagg["current_player"] == player]
#             ax.plot(d["depth"], d[COL_ATTACKS], marker="o", label=str(player))

#         ax.set_title(f"Avg combat actions vs rollout depth (game={g})")
#         ax.set_xlabel("Rollout depth")
#         ax.set_ylabel("Avg # combat actions")
#         ax.legend()
#         plt.tight_layout()
#         outg = f"{OUT_DIR}/avg_attacks_vs_depth_game{g}.png"
#         plt.savefig(outg, dpi=200)
#         plt.close()
#         print("Saved:", outg)
