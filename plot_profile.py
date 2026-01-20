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

PROF_GLOB = f"{main_folder}/profiles/mcts_*.prof"
TARGET_FILE = "combat_mcts_agent.py"
TEXT_REPORT = f"{main_folder}/profiling/profile_report.txt"
CSV_OUTPUT = f"{main_folder}/profiling/profile_data.csv"
OUTPUT_DIR = f"{main_folder}/profiling"

TOP_K_FUNCS = 5

aggregated = defaultdict(lambda: {"cumtime": 0, "tottime": 0, "count": 0})
per_profile = {}          
simulate_times = {}      


def analyze_prof_file(fname):
    p = pstats.Stats(fname)
    p.strip_dirs()
    results = []

    profile_name = fname
    per_profile[profile_name] = {}

    for func, stat in p.stats.items():
        file, line, name = func
        if TARGET_FILE in file:
            cc, nc, tt, ct, callers = stat
            results.append((file, line, name, tt, ct))

            key = f"{name}:{line}"

            # Aggregated stats across all profiles
            aggregated[key]["tottime"] += tt        # its python level code
            aggregated[key]["cumtime"] += ct        # its python level code + all the function calls in it
            aggregated[key]["count"] += 1

            # NEW: per profile stats
            per_profile[profile_name][key] = {
                "tottime": tt,
                "cumtime": ct
            }

            # NEW: record simulate() only
            if name == "simulate":
                simulate_times[profile_name] = ct
    per_profile[profile_name]["__total_time__"] = p.total_tt
    results.sort(key=lambda x: x[4], reverse=True)
    return results


profiles = sorted(glob.glob(PROF_GLOB))
for prof in profiles:
    analyze_prof_file(prof)



with open(TEXT_REPORT, "w") as f:
    for prof in profiles:
        f.write("=" * 60 + "\n")
        f.write(f"PROFILE FILE: {prof}\n")
        f.write("=" * 60 + "\n")

        total_time = per_profile[prof].get("__total_time__", None)
        if total_time is not None:
            f.write(f"TOTAL PROFILE RUNTIME (CPU): {total_time:.3f} s\n")


        funcs = per_profile[prof]

        if not funcs:
            f.write("No entries found.\n\n")
            continue

        f.write(f"{'Function':40} | tottime | cumtime\n")
        f.write("-" * 80 + "\n")

        # Sort per profile by cumtime descending
        sorted_funcs = sorted(
            (
                (k, v)
                for k, v in funcs.items()
                if isinstance(v, dict) and "cumtime" in v
            ),
            key=lambda x: x[1]["cumtime"],
            reverse=True
        )

        for key, d in sorted_funcs[:5]:
            name, line = key.split(":")
            f.write(f"{name:40} | {d['tottime']:7.3f} | {d['cumtime']:7.3f}\n")
        f.write("\n")

print("Text report written to", TEXT_REPORT)


records = []

for prof in profiles:
    total_time = per_profile[prof].get("__total_time__", None)
    for func_key, t_dict in per_profile[prof].items():
        # Skip metadata entries
        if not isinstance(t_dict, dict):
            continue
        
        # Extract function name without line number
        func_name = func_key.split(":")[0]

        records.append({
            "profile": prof,
            "func_name": func_name,
            "time": t_dict["tottime"],   # Use cumtime for plotting total cost
            "total_time": total_time
        })

df = pd.DataFrame(records)

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

plt.boxplot(data, tick_labels=top_funcs, showfliers=True)
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
