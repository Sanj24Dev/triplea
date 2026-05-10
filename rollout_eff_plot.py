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
PLAYER_INFO_PATH = f"{FOLDER}/player_info.csv"
OUT_DIR = FOLDER
os.makedirs(OUT_DIR, exist_ok=True)

COL_ATTACKS = "terr_attacked_in_round (actions taken)"

# ── Load data ────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)
player_info = pd.read_csv(PLAYER_INFO_PATH)  # columns: game, player

df["depth"] = pd.to_numeric(df["depth"], errors="coerce")
df[COL_ATTACKS] = pd.to_numeric(df[COL_ATTACKS], errors="coerce")
df = df.dropna(subset=["depth", "current_player", COL_ATTACKS])

# ── Merge so each row knows which nation the agent played that game ──────────
df = df.merge(player_info.rename(columns={"player": "agent_nation"}),
              on="game", how="left")

# ── All nations that ever appear ─────────────────────────────────────────────
all_nations = sorted(df["current_player"].unique())

# ── One subplot per nation the agent can be ──────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharey=False)
axes = axes.flatten()

agent_roles = sorted(df["agent_nation"].dropna().unique())  # nations agent actually played

for ax_idx, role in enumerate(agent_roles):
    ax = axes[ax_idx]

    # Only games where agent played this role
    games_as_role = df[df["agent_nation"] == role]["game"].unique()
    subset = df[df["game"].isin(games_as_role)]

    agg = (
        subset
        .groupby(["depth", "current_player"])[COL_ATTACKS]
        .mean()
        .reset_index()
        .sort_values(["current_player", "depth"])
    )

    for nation in sorted(agg["current_player"].unique()):
        d = agg[agg["current_player"] == nation]
        is_agent = (nation == role)
        ax.plot(
            d["depth"], d[COL_ATTACKS],
            marker="o",
            linewidth=2.5 if is_agent else 1.2,
            linestyle="-" if is_agent else "--",
            label=f"{nation} ← AGENT" if is_agent else nation,
            zorder=3 if is_agent else 2,
        )

    n_games = len(games_as_role)
    ax.set_title(f"Agent playing as: {role}  ({n_games} game{'s' if n_games != 1 else ''})",
                 fontweight="bold")
    ax.set_xlabel("Rollout depth")
    ax.set_ylabel("Avg combat actions")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

# Hide any unused subplots (if agent played fewer than 4 roles)
for i in range(len(agent_roles), len(axes)):
    axes[i].set_visible(False)

fig.suptitle("Avg combat actions vs rollout depth — agent role comparison",
             fontsize=14, fontweight="bold", y=1.01)
plt.tight_layout()

out = f"{OUT_DIR}/avg_attacks_by_agent_role.png"
plt.savefig(out, dpi=200, bbox_inches="tight")
plt.close()
print("Saved:", out)