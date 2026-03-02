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

PROF_GLOB = f"{main_folder}/profiles/mcts_*.prof"
TARGET_FILE = "combat_policy_mcts_agent.py"
TEXT_REPORT = f"{main_folder}/profiling/profile_report.txt"
CSV_OUTPUT = f"{main_folder}/profiling/profile_data.csv"


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

for func_key, stats in aggregated.items():
    rows.append({
    "function": func_key,
    "total_tottime": stats["tottime"],
    "total_cumtime": stats["cumtime"],
    "num_profiles_seen": stats["count"],
    "avg_tottime_per_profile": stats["tottime"] / stats["count"],
    "avg_cumtime_per_profile": stats["cumtime"] / stats["count"],
    })

df = pd.DataFrame(rows)
df.sort_values("total_cumtime", ascending=False, inplace=True)

os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
df.to_csv(CSV_OUTPUT, index=False)

print(f"Saved aggregated profile data → {CSV_OUTPUT}")

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
