import glob
import matplotlib.pyplot as plt
import pandas as pd
import os
import numpy as np
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--folder", type=str, required=True)
args = parser.parse_args()

main_folder = args.folder

CSV_INPUT  = f"{main_folder}/profiling/profile_data.csv"
OUTPUT_DIR = f"{main_folder}/profiling"
TEXT_REPORT = f"{OUTPUT_DIR}/profile_report.txt"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TOP_K_FUNCS = 5

df = pd.read_csv(CSV_INPUT)

df["profile_short"] = df["profile"].apply(
    lambda x: os.path.basename(x).replace("mcts_", "").replace(".prof", "")
)

############################################
# TEXT REPORT
############################################

with open(TEXT_REPORT, "w") as f:
    for prof, gdf in df.groupby("profile"):
        f.write("=" * 60 + "\n")
        f.write(f"PROFILE FILE: {prof}\n")
        f.write("=" * 60 + "\n")

        total_time = gdf["total_time"].iloc[0]
        f.write(f"TOTAL PROFILE RUNTIME (CPU): {total_time:.3f} s\n")

        f.write(f"{'Function':40} | {'time':>10} | {'ncalls':>8} | {'per_call':>12}\n")
        f.write("-" * 80 + "\n")
        for _, row in gdf.sort_values("time", ascending=False).head(5).iterrows():
            f.write(f"{row['func_name']:40} | {row['time']:10.6f} | {row['ncalls']:8.0f} | {row['time_per_call']:12.8f}\n")

    f.write("\n" + "=" * 60 + "\n")
    f.write("MEDIAN STATISTICS ACROSS ALL GAMES\n")
    f.write("=" * 60 + "\n")
    f.write(f"{'Function':40} | {'med_time':>10} | {'med_ncalls':>10} | {'med_per_call':>14}\n")
    f.write("-" * 80 + "\n")

    median_stats = (
        df.groupby("func_name")[["time", "ncalls", "time_per_call"]]
        .median()
        .sort_values("time", ascending=False)
    )

    for func_name, row in median_stats.iterrows():
        f.write(
            f"{func_name:40} | {row['time']:10.6f} | {row['ncalls']:10.0f} | {row['time_per_call']:14.8f}\n"
        )

print("Text report written to", TEXT_REPORT)

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
# BOX PLOT
############################################

# plt.figure(figsize=(10, 6))

# data = [df_top[df_top["func_name"] == f]["time"].values for f in top_funcs]

# plt.boxplot(data, labels=top_funcs, showfliers=True)
# plt.ylabel("Time per game (seconds)")
# plt.title("Distribution of Time Spent per Function Across Games")
# plt.xticks(rotation=30)
# plt.tight_layout()
# plt.savefig(f"{OUTPUT_DIR}/boxplot_function_time.png")
# plt.close()
# print(f"Plot saved {OUTPUT_DIR}/boxplot_function_time.png")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

data_total = [df_top[df_top["func_name"] == f]["time"].values for f in top_funcs]
ax1.boxplot(data_total, labels=top_funcs, showfliers=True)
ax1.set_ylabel("Time per game (seconds)")
ax1.set_title("Total Time per Function Across Games")
ax1.tick_params(axis='x', rotation=30)

data_per_call = [df_top[df_top["func_name"] == f]["time_per_call"].values for f in top_funcs]
ax2.boxplot(data_per_call, labels=top_funcs, showfliers=True)
ax2.set_ylabel("Time per call (seconds)")
ax2.set_title("Per-Call Time per Function Across Games")
ax2.tick_params(axis='x', rotation=30)

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/boxplot_function_time.png")
plt.close()

############################################
# STACKED PERCENTAGE BAR
############################################

composition = (
    df_top.groupby(["profile_short", "func_name"])["time"]
    .sum()
    .unstack(fill_value=0)
)

composition_pct = composition.div(composition.sum(axis=1), axis=0)
# # composition_pct["Other"] = 1.0 - composition_pct.sum(axis=1)

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
# plt.savefig(f"{OUTPUT_DIR}/stacked_runtime_composition.png")
# plt.close()
# print(f"Plot saved {OUTPUT_DIR}/stacked_runtime_composition.png")

composition_per_call = (
    df_top.groupby(["profile_short", "func_name"])["time_per_call"]
    .mean()  # mean per-call time across games, per function
    .unstack(fill_value=0)
)
composition_per_call_pct = composition_per_call.div(composition_per_call.sum(axis=1), axis=0)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6))

# --- existing total time chart on ax1 ---
bottom = np.zeros(len(composition_pct))
x = np.arange(len(composition_pct))
for col in composition_pct.columns:
    ax1.bar(x, composition_pct[col], bottom=bottom, label=col)
    bottom += composition_pct[col].values
ax1.set_xticks([])
ax1.set_ylabel("Fraction of total runtime")
ax1.set_title("Runtime Composition per Game (Top Functions)")
ax1.legend(loc="upper right", fontsize=9)

# --- new per-call chart on ax2 ---
bottom = np.zeros(len(composition_per_call_pct))
x2 = np.arange(len(composition_per_call_pct))
for col in composition_per_call_pct.columns:
    ax2.bar(x2, composition_per_call_pct[col], bottom=bottom, label=col)
    bottom += composition_per_call_pct[col].values
ax2.set_xticks([])
ax2.set_ylabel("Fraction of mean per-call time")
ax2.set_title("Per-Call Time Composition per Game (Top Functions)")
ax2.legend(loc="upper right", fontsize=9)

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/stacked_runtime_composition.png")
plt.close()