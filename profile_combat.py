import pstats

INPUT = "smart_root_dumb_tree/profiles/mcts_07.prof"

p = pstats.Stats(INPUT)
p.strip_dirs().sort_stats("tottime").print_stats("combat_legal_moves")