import pstats

INPUT = "mcts_1.prof"
OUTPUT = "mcts_filtered.prof"
FILTER_PATH = "/storage/home/hcoda1/6/snayak89/tripleMind/triplea/"

p = pstats.Stats(INPUT)

# Keep only entries whose filename contains your project path
p.stats = {
    func: stat
    for func, stat in p.stats.items()
    if FILTER_PATH in func[0]   # func[0] = file path
}

p.dump_stats(OUTPUT)
print("Wrote filtered profile to", OUTPUT)
p.sort_stats("cumtime")
p.print_stats()