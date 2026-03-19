import pstats
import glob
import csv
import matplotlib.pyplot as plt
from collections import defaultdict
import pandas as pd
import os
import numpy as np
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder
# FOLDER = f"{main_folder}/metrics"

# PROF_GLOB = f"{main_folder}/profiles/mcts_*.prof"
# TARGET_FILE = "combat_mcts_agent.py"
# TEXT_REPORT = f"{main_folder}/profiling/profile_report.txt"
# CSV_OUTPUT = f"{main_folder}/profiling/profile_data.csv"
OUTPUT_DIR = f"{main_folder}/profiling"

TOP_K_FUNCS = 5



df = pd.read_csv(f"{OUTPUT_DIR}/profile_data.csv")
# df = df[df["profile"].str.contains(r"mcts_5003_*")]

# Short function names for plotting
df["func_name"] = df["func_name"].apply(lambda x: x.split(":")[0])
df["profile_short"] = df["profile"].apply(
    lambda x: os.path.basename(x).replace("mcts_", "").replace(".prof", "")
)

############################################
# SELECT TOP-K FUNCTIONS (GLOBAL)
############################################

top_funcs = (
    df.groupby("func_name")["time"]
    .sum()
    .sort_values(ascending=False)
    .head(TOP_K_FUNCS)
    .index
    .tolist()
)

df_top = df[df["func_name"].isin(top_funcs)]

############################################
# BOX PLOT — DISTRIBUTION VIEW
############################################

plt.figure(figsize=(10, 6))

data = [
    df_top[df_top["func_name"] == f]["time"].values
    for f in top_funcs
]

plt.boxplot(data, labels=top_funcs, showfliers=True)
plt.ylabel("Cumulative time per game (seconds)")
plt.title("Distribution of Time Spent per Function Across Games")
plt.xticks(rotation=30)
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/boxplot_function_time.png")
plt.close()
print(f"Plot saved {OUTPUT_DIR}/boxplot_function_time.png")




############################################
# STACKED PERCENTAGE BAR — COMPOSITION VIEW
############################################

composition = (
    df_top.groupby(["profile_short", "func_name"])["time"]
    .sum()
    .unstack(fill_value=0)
)

# Normalize to percentages
composition_pct = composition.div(composition.sum(axis=1), axis=0)

# Add "Other"
other = 1.0 - composition_pct.sum(axis=1)
composition_pct["Other"] = other

plt.figure(figsize=(12, 6))

bottom = np.zeros(len(composition_pct))
x = np.arange(len(composition_pct))

for col in composition_pct.columns:
    plt.bar(x, composition_pct[col], bottom=bottom, label=col)
    bottom += composition_pct[col].values

# plt.xticks(x, composition_pct.index, rotation=45)
plt.xticks([]) 
plt.ylabel("Fraction of total runtime")
plt.title("Runtime Composition per Game (Top Functions)")
plt.legend(loc="upper right", fontsize=9)
plt.tight_layout()

plt.savefig(f"{OUTPUT_DIR}/stacked_runtime_composition.png")
plt.close()
print(f"Plot saved {OUTPUT_DIR}/stacked_runtime_composition.png")



# top_funcs = (
#     df.groupby("func_name")["cumtime"]
#     .sum()
#     .sort_values(ascending=False)
#     .head(TOP_K_FUNCS)
#     .index
#     .tolist()
# )

# df_top = df[df["func_name"].isin(top_funcs)]

# plt.figure(figsize=(10, 6))

# data = [
#     df_top[df_top["func_name"] == f]["cumtime"].values
#     for f in top_funcs
# ]

# plt.boxplot(data, labels=top_funcs, showfliers=True)
# plt.ylabel("Cumulative time per game (seconds)")
# plt.title("Distribution of Time Spent Cummulatively per Function Across Games")
# plt.xticks(rotation=30)
# plt.tight_layout()
# plt.savefig(f"{OUTPUT_DIR}/boxplot_function_cumtime.png")
# plt.close()
# print(f"Plot saved {OUTPUT_DIR}/boxplot_function_cumtime.png")


# FUNCTIONS_TO_PLOT = [
#     "select",
#     "expand",
#     "simulate",
#     "backpropagate",
# ]

# # Filter to only wanted functions
# df_filtered = df[df["func_name"].isin(FUNCTIONS_TO_PLOT)]
# # print(df_filtered)

# composition = (
#     df_filtered.groupby(["profile_short", "func_name"])["cumtime"]
#     .sum()
#     .unstack(fill_value=0)
# )

# # Ensure all wanted functions are present as columns even if missing in some profiles
# for fn in FUNCTIONS_TO_PLOT:
#     if fn not in composition.columns:
#         composition[fn] = 0.0

# # Reorder columns to match FUNCTIONS_TO_PLOT order
# composition = composition[FUNCTIONS_TO_PLOT]



# # Normalize
# composition_pct = composition.div(composition.sum(axis=1), axis=0)
# other = 1.0 - composition_pct.sum(axis=1)
# composition_pct["Other"] = other.clip(lower=0)  # avoid tiny negatives from float error

# # Plot
# plt.figure(figsize=(12, 6))
# bottom = np.zeros(len(composition_pct))
# x = np.arange(len(composition_pct))

# for col in composition_pct.columns:
#     plt.bar(x, composition_pct[col], bottom=bottom, label=col)
#     bottom += composition_pct[col].values

# plt.xticks([])
# plt.ylabel("Fraction of total runtime")
# plt.title("Runtime Composition per Game (Top Functions)")
# plt.legend(loc="upper right", fontsize=9)
# plt.tight_layout()
# plt.savefig(f"{OUTPUT_DIR}/stacked_runtime_composition_mcts.png")
# plt.close()