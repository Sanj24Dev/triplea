import pstats
import glob
import csv
import matplotlib.pyplot as plt
from collections import defaultdict

PROF_GLOB = "smart_root_dumb_tree/profiles/mcts_*.prof"
TARGET_FILE = "combat_mcts_agent.py"
TEXT_REPORT = "smart_root_dumb_tree/profiling/profile_report.txt"
CSV_OUTPUT = "smart_root_dumb_tree/profiling/profile_data.csv"

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

    results.sort(key=lambda x: x[4], reverse=True)
    return results


################################
# 1. Process all profiles
################################
profiles = sorted(glob.glob(PROF_GLOB))
for prof in profiles:
    analyze_prof_file(prof)


################################
# 2. Write Text Summary
################################
with open(TEXT_REPORT, "w") as f:
    for prof in profiles:
        f.write("=" * 60 + "\n")
        f.write(f"PROFILE FILE: {prof}\n")
        f.write("=" * 60 + "\n\n")

        funcs = per_profile[prof]

        if not funcs:
            f.write("No entries found.\n\n")
            continue

        f.write(f"{'Function':40} | tottime | cumtime\n")
        f.write("-" * 80 + "\n")

        # Sort per profile by cumtime descending
        sorted_funcs = sorted(
            funcs.items(), key=lambda x: x[1]["cumtime"], reverse=True
        )

        for key, d in sorted_funcs[:10]:
            name, line = key.split(":")
            f.write(f"{name:40} | {d['tottime']:7.3f} | {d['cumtime']:7.3f}\n")
        f.write("\n")

print("Text report written to", TEXT_REPORT)





if simulate_times:
    plt.figure(figsize=(10, 5))

    names = list(simulate_times.keys())
    times = [t for t in simulate_times.values()]

    plt.bar(range(len(names)), times)
    plt.xticks(range(len(names)), [n.replace("smart_root_dumb_tree/profiles/mcts_", "").replace(".prof", "") for n in names], rotation=45)
    plt.ylabel("Time spent in simulate() (seconds)")
    plt.title("simulate() Timing Across All Profile Runs")
    plt.tight_layout()
    plt.savefig("smart_root_dumb_tree/profiling/simulate_per_profile.png")
    print("Plot written to simulate_per_profile.png")
else:
    print("No simulate() entries found; skipping plot.")




# Determine the top functions globally
top_functions = sorted(
    aggregated.items(), key=lambda x: x[1]["cumtime"], reverse=True
)[:5]

func_keys = [k for (k, _) in top_functions]
func_labels = [k.split(":")[0] for k in func_keys]
plt.figure(figsize=(12, 6))

# Create grouped bars manually
x = range(len(profiles))
bar_width = 0.12

for i, func in enumerate(func_keys):
    values = []
    for prof in profiles:
        values.append(
            per_profile.get(prof, {}).get(func, {}).get("cumtime", 0)
        )
        # print(f"prof: {prof} = {v}")

    positions = [p + i * bar_width for p in x]
    plt.bar(positions, values, width=bar_width, label=func_labels[i])

plt.xticks(
    [p + bar_width * (len(func_keys)/2) for p in x],
    [p.replace("smart_root_dumb_tree/profiles/mcts_", "").replace(".prof", "") for p in profiles],
    rotation=45
)
plt.ylabel("Cumulative Time (seconds)")
plt.title("Function Timing Comparison Across Profiles")
plt.legend()
plt.tight_layout()
plt.savefig("smart_root_dumb_tree/profiling/timing_comparison.png")

# print([per_profile.get(p, {}).get('heuristic_non_combat_legal_moves', {}).get('cumtime', 0) for p in profiles])


print("Plot written to timing_comparison.png")
