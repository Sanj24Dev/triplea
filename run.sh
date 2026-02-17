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
# python setup.py build_ext --inplace

# pip install --user pandas

export PROJECT_ROOT="/storage/home/hcoda1/6/snayak89/tripleMind"

MODEL_NAME="multi_front_attack"

rm -f multi_front_attack/metrics/*
rm -f multi_front_attack/profiling/*
rm -f multi_front_attack/combat_moves/*
rm -f multi_front_attack/trees/*
rm -f multi_front_attack/profiles/*
rm "../logs/RL_BOT_3/Capture The Flag.log"

# 1. Start the first program in the background and get its PID
REDUCTION_REC="multi_front_attack/metrics/reduction.csv"
EFFICIENCY_REC="multi_front_attack/metrics/mcts_efficiency.csv"
OUTCOME_REC="multi_front_attack/metrics/game_outcome.csv"
QUALITY_REC="multi_front_attack/metrics/combat_quality.csv"
ROLLOUT_REC="multi_front_attack/metrics/rollout_efficiency.csv"

export GAMES_TO_PLAY=5

export PLAYER_ID=2
export START_GAME_NUM=1
python3 -u game_mcts.py --model_name "$MODEL_NAME" --reduction_file "$REDUCTION_REC" --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC"> output.log &
MCTS_PID=$!
echo "Started MCTS with PID $MCTS_PID"
sleep 5
python3 play_game.py > output_play.log 
echo "Game finished. Killing MCTS process $MCTS_PID"
kill $MCTS_PID

export START_GAME_NUM=$((START_GAME_NUM + GAMES_TO_PLAY))
python3 -u game_mcts.py --model_name "$MODEL_NAME" --reduction_file "$REDUCTION_REC" --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC"> output.log &
MCTS_PID=$!
echo "Started MCTS with PID $MCTS_PID"
sleep 5
python3 play_game.py > output_play.log 
echo "Game finished. Killing MCTS process $MCTS_PID"
kill $MCTS_PID

export PLAYER_ID=3
export START_GAME_NUM=$((START_GAME_NUM - GAMES_TO_PLAY))
python3 -u game_mcts.py --model_name "$MODEL_NAME" --reduction_file "$REDUCTION_REC" --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC"> output.log &
MCTS_PID=$!
echo "Started MCTS with PID $MCTS_PID"
sleep 5
python3 play_game.py > output_play.log 
echo "Game finished. Killing MCTS process $MCTS_PID"
kill $MCTS_PID

export START_GAME_NUM=$((START_GAME_NUM + GAMES_TO_PLAY))
python3 -u game_mcts.py --model_name "$MODEL_NAME" --reduction_file "$REDUCTION_REC" --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC"> output.log &
MCTS_PID=$!
echo "Started MCTS with PID $MCTS_PID"
sleep 5
python3 play_game.py > output_play.log 
echo "Game finished. Killing MCTS process $MCTS_PID"
kill $MCTS_PID


# Optional: Wait for clean exit
wait $MCTS_PID 2>/dev/null

end_time=$(date +%s)
elapsed=$((end_time - start_time))
echo "Time taken: ${elapsed} seconds"
