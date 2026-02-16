import os
import pandas as pd
import matplotlib.pyplot as plt
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"
CSV_PATH = f"{FOLDER}/rollout_efficiency.csv" 
OUT_DIR = FOLDER
os.makedirs(OUT_DIR, exist_ok=True)

COL_ATTACKS = "terr_attacked_in_round (actions taken)"

df = pd.read_csv(CSV_PATH)

# --- basic hygiene ---
# ensure numeric
df["depth"] = pd.to_numeric(df["depth"], errors="coerce")
df[COL_ATTACKS] = pd.to_numeric(df[COL_ATTACKS], errors="coerce")
df = df.dropna(subset=["depth", "current_player", COL_ATTACKS])

# ----------------------------
# Plot 1: Avg attacks vs depth
# ----------------------------
agg = (
    df.groupby(["depth", "current_player"])[COL_ATTACKS]
      .mean()
      .reset_index()
      .sort_values(["current_player", "depth"])
)

fig, ax = plt.subplots(figsize=(10, 6))
for player in agg["current_player"].unique():
    d = agg[agg["current_player"] == player]
    ax.plot(d["depth"], d[COL_ATTACKS], marker="o", label=str(player))

ax.set_title("Average combat actions per turn vs rollout depth")
ax.set_xlabel("Rollout depth")
ax.set_ylabel("Avg # combat actions (apply_combat_move calls)")
ax.legend()
plt.tight_layout()
out1 = f"{OUT_DIR}/avg_attacks_vs_depth.png"
plt.savefig(out1, dpi=200)
plt.close()

print("Saved:", out1)

# -------------------------------------------------------
# Plot 2 (optional): Russia advantage vs others by depth
# -------------------------------------------------------
RUS_NAME = "Russians"  # adjust if your label differs

# mean attacks of others at each depth
mean_by_depth = df.groupby("depth")[COL_ATTACKS].mean().rename("mean_all")
rus_by_depth = (
    df[df["current_player"] == RUS_NAME]
      .groupby("depth")[COL_ATTACKS]
      .mean()
      .rename("mean_rus")
)

delta = pd.concat([mean_by_depth, rus_by_depth], axis=1).dropna()
delta["mean_others"] = (delta["mean_all"] * 4 - delta["mean_rus"]) / 3  # assumes 4 players
delta["rus_minus_others"] = delta["mean_rus"] - delta["mean_others"]
delta = delta.reset_index()

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(delta["depth"], delta["rus_minus_others"], marker="o")
ax.axhline(0, linewidth=1)
ax.set_title("Russians: avg attacks minus avg of other players (by rollout depth)")
ax.set_xlabel("Rollout depth")
ax.set_ylabel("Δ attacks (Russians - others)")
plt.tight_layout()
out2 = f"{OUT_DIR}/rus_minus_others_vs_depth.png"
plt.savefig(out2, dpi=200)
plt.close()

print("Saved:", out2)

# -------------------------------------------------------
# Plot 3 (optional): per-game comparison (Game 1 vs Game 2)
# -------------------------------------------------------
if "game" in df.columns:
    for g in sorted(df["game"].unique()):
        gdf = df[df["game"] == g]
        gagg = (
            gdf.groupby(["depth", "current_player"])[COL_ATTACKS]
               .mean()
               .reset_index()
               .sort_values(["current_player", "depth"])
        )

        fig, ax = plt.subplots(figsize=(10, 6))
        for player in gagg["current_player"].unique():
            d = gagg[gagg["current_player"] == player]
            ax.plot(d["depth"], d[COL_ATTACKS], marker="o", label=str(player))

        ax.set_title(f"Avg combat actions vs rollout depth (game={g})")
        ax.set_xlabel("Rollout depth")
        ax.set_ylabel("Avg # combat actions")
        ax.legend()
        plt.tight_layout()
        outg = f"{OUT_DIR}/avg_attacks_vs_depth_game{g}.png"
        plt.savefig(outg, dpi=200)
        plt.close()
        print("Saved:", outg)
