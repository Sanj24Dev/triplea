#!/bin/bash

# load modules needed to run pybind 
module purge
module load python
module load gcc
module load cmake

# compile the pybind cpp functions
g++ -O3 -Wall -shared -std=c++11 -fPIC $(python3 -m pybind11 --includes) reachability.cpp -o reachability_cpp$(python3 -m pybind11 --extension-suffix)

pip install --user pandas

rm -f smart_root_dumb_tree/metrics/*
rm -f smart_root_dumb_tree/profiling/*
rm -f smart_root_dumb_tree/combat_moves/*
rm -f smart_root_dumb_tree/profiles/*

# 1. Start the first program in the background and get its PID
REDUCTION_REC="smart_root_dumb_tree/metrics/reduction.csv"
EFFICIENCY_REC="smart_root_dumb_tree/metrics/mcts_efficiency.csv"

python3 -u game_mcts.py --reduction_file "$REDUCTION_REC" --efficiency_file "$EFFICIENCY_REC" > output.log &
MCTS_PID=$!

echo "Started MCTS with PID $MCTS_PID"

# 2. Wait 5 seconds for the socket server to come online
sleep 5

# 3. Run the second program in the foreground (blocks until finished)
python3 play_game.py > output_play.log

# 4. After second program exits, terminate the first program
echo "Game finished. Killing MCTS process $MCTS_PID"
kill $MCTS_PID

# Optional: Wait for clean exit
wait $MCTS_PID 2>/dev/null
rm "../logs/RL_BOT_3/Capture The Flag.log"

# use the following for profiling and analysis
python3 plot_efficiency.py
python3 plot_reduction.py
python3 profile_simulate.py

REPORT_PDF="smart_root.pdf"
REPORT_FOLDER="smart_root_dumb_tree"
GAME_SUMMARY="The program runs 1 game giving the MCTS time budget of 1s. The MCTS is programmed using Python and CPP(Pybind). The MCTS only selects one territory to attack in a round."
python3 summary_script.py --file_name="$REPORT_PDF" --report_folder="$REPORT_FOLDER" --game_summary="$GAME_SUMMARY"
zip -r simulation_results.zip $REPORT_PDF $REPORT_FOLDER
# tuna mcts.prof