import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def get_roots_and_children(df):
    df = df.copy()
    df["key"] = list(zip(df["game"], df["round"]))
    root_idx = df.groupby("key")["tree_level"].idxmin()
    roots = df.loc[root_idx].set_index("key")

    children = []
    for key, root_entry in roots.iterrows():
        sub = df[df["key"] == key]
        kids = sub[sub["parent_id"] == root_entry["node_id"]]
        if len(kids) == 0:
            continue
        kids = kids.copy()
        kids["key"] = [key] * len(kids)
        children.append(kids)

    children = pd.concat(children, ignore_index=True) if children else pd.DataFrame()
    return roots, children




parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
FOLDER = f"{main_folder}/metrics"

INPUT_FILE = f"{FOLDER}/tree_info.csv"
ROOT_VISITS = f"{FOLDER}/total_root_visits_over_round.png"

df = pd.read_csv(INPUT_FILE)

roots, children = get_roots_and_children(df)


# total_root_visits_over_rounds
 
if len(children) == 0:
    print("No data for total_root_visits_over_round")
else:
    roots_flat = roots.reset_index()[["key", "vis", "n_legal"]].rename(
        columns={"vis": "root_total_vis", "n_legal": "n_legal_root"}
    )
 
    # sum of children's vis, to sanity-check against root's own vis (backprop check)
    child_vis_sum = (
        children.groupby("key")["vis"].sum().reset_index().rename(columns={"vis": "sum_children_vis"})
    )
 
    grp = children.groupby("key").agg(
        n_children_logged=("vis", "size"),  # arms that actually got >=1 visit / were expanded
        round=("round", "first"),
        game=("game", "first"),
    ).reset_index()
 
    grp = grp.merge(roots_flat, on="key", how="left")
    grp = grp.merge(child_vis_sum, on="key", how="left")
 
    # true branching factor should come from n_legal logged at the root, not n_children_logged
    grp["n_legal"] = grp["n_legal_root"]
    grp["visits_per_arm"] = grp["root_total_vis"] / grp["n_legal"]
 
    # backprop sanity check: root vis vs sum of children vis
    grp["root_vs_children_mismatch"] = grp["root_total_vis"] - grp["sum_children_vis"]
    mismatches = grp[grp["root_vs_children_mismatch"].abs() > 0]
    if len(mismatches) > 0:
        print(f"WARNING: {len(mismatches)} rows where root vis != sum(children vis). "
              f"Check backprop bookkeeping. Example mismatches:\n"
              f"{mismatches[['game','round','root_total_vis','sum_children_vis']].head()}")
 
    fig, ax = plt.subplots(figsize=(9, 5))
    for game, gsub in grp.groupby("game"):
        gsub = gsub.sort_values("round")
        ax.plot(gsub["round"], gsub["visits_per_arm"], marker="o", ms=3, lw=1, alpha=0.8, label=f"game {game}")
 
    ax.axhline(1.0, color="red", ls="--", lw=1, alpha=0.6, label="1 visit/arm (starved)")
    ax.set_xlabel("round")
    ax.set_ylabel("visits per arm  =  N(s) / n_legal")
    ax.set_title("Average visits per legal arm at root, over rounds")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(ROOT_VISITS)
    plt.close(fig)
    print(f"Saved {ROOT_VISITS}")
 
    # also report a quick summary table
    # summary = grp.groupby("game")["visits_per_arm"].agg(["mean", "min", "max"])
    # print(summary)


# visit scatter plot
VIS_SCATTER = f"{FOLDER}/vis_scatter.png"
if len(children) == 0:
    print("No data for vis_scatter")
else:
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    ax[0].scatter(children["avg"], children["vis"], s=8, alpha=0.35)
    ax[0].set_xlabel("avg value")
    ax[0].set_ylabel("vis")
    ax[0].set_title("Per-arm avg vs vis")
    corrs = []
    for key, sub in children.groupby("key"):
        if sub["avg"].nunique() > 1 and sub["vis"].nunique() > 1 and len(sub) > 2:
            corrs.append(sub["avg"].corr(sub["vis"]))
    corrs = [c for c in corrs if not np.isnan(c)]
    if corrs:
        ax[1].hist(corrs, bins=20)
        ax[1].axvline(0, color="red", ls="--", lw=1)
        ax[1].set_xlabel("corr")
        ax[1].set_ylabel("count of decisions")
        ax[1].set_title(f"Per-decision correlation\nmean={np.mean(corrs):.2f}, median={np.median(corrs):.2f}")
    fig.tight_layout()
    fig.savefig(VIS_SCATTER)
    plt.close(fig)
    print(f"Saved {VIS_SCATTER}")