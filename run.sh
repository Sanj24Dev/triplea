#!/bin/bash
start_time=$(date +%s)
# load modules needed to run pybind 
# module purge
# module load python
# module load gcc
# module load cmake

# compile the pybind cpp functions
# g++ -O3 -Wall -shared -std=c++11 -fPIC $(python3 -m pybind11 --includes) reachability.cpp -o reachability_cpp$(python3 -m pybind11 --extension-suffix)
# g++ -O3 -Wall -shared -std=c++11 -fPIC $(python3 -m pybind11 --includes) check_reachability.cpp -o check_reachability_cpp$(python3 -m pybind11 --extension-suffix)

# compile cython file
python3 setup.py build_ext --inplace

# pip install --user pandas

export PROJECT_ROOT="/home/sanjana/tripleMind"

MODEL_NAME="mcts_heuristic_v2"

rm -f $MODEL_NAME/metrics/*
rm -f $MODEL_NAME/profiling/*
rm -f $MODEL_NAME/combat_moves/*
rm -f $MODEL_NAME/move_sim/*
rm -f $MODEL_NAME/snapshots/*
rm -f $MODEL_NAME/trees/*
rm -f $MODEL_NAME/profiles/*
rm "../logs/RL_BOT_3/Capture The Flag.log"

# export DISABLED="(2 3)"
export START_GAME_NUM="1"
for i in {0..3}; do
    export PLAYER_ID="$i"
    python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
done

# export DISABLED="(1 3)"
# for i in {0..0}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(1 2)"
# for i in {0..0}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done


# export DISABLED="(2 3)"
# for i in {1..1}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 3)"
# for i in {1..1}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 2)"
# for i in {1..1}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done


# export DISABLED="(1 3)"
# for i in {2..2}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 3)"
# for i in {2..2}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 1)"
# for i in {2..2}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done


# export DISABLED="(1 2)"
# for i in {3..3}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 2)"
# for i in {3..3}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done

# export DISABLED="(0 1)"
# for i in {3..3}; do
#     export PLAYER_ID="$i"
#     python3 -u mcts_heuristic.py > mcts_heuristic_${PLAYER_ID}.log
# done



