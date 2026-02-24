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

# export PROJECT_ROOT="/home/sanjana/tripleMind"
export PROJECT_ROOT="/storage/home/hcoda1/6/snayak89/tripleMind"

MODEL_NAME="self_play_model"

rm -f $MODEL_NAME/metrics/*
rm -f $MODEL_NAME/player_logs/*
rm ../logs/player_5000/Capture\ The\ Flag.log
rm ../logs/player_5001/Capture\ The\ Flag.log
rm ../logs/player_5002/Capture\ The\ Flag.log
rm ../logs/player_5003/Capture\ The\ Flag.log


# 1. Start the first program in the background and get its PID
EFFICIENCY_REC="$MODEL_NAME/metrics/mcts_efficiency"
OUTCOME_REC="$MODEL_NAME/metrics/game_outcome"
QUALITY_REC="$MODEL_NAME/metrics/combat_quality"
ROLLOUT_REC="$MODEL_NAME/metrics/rollout_efficiency"


export GAMES_TO_PLAY=1

export PLAYER_1="startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
export PLAYER_2="startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
export PLAYER_3="startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
export PLAYER_4="startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
export PLAYER_1_PORT=5000
export PLAYER_2_PORT=5001
export PLAYER_3_PORT=5002
export PLAYER_4_PORT=5003

NUM_GAMES=1

for ((i=1; i<=NUM_GAMES; i++)); do
    export START_GAME_NUM=$i
    python3 -u game_mcts.py --model_name "$MODEL_NAME" --player_name "Russians" --port 5000 --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC" &
    PID_P1=$!
    python3 -u game_mcts.py --model_name "$MODEL_NAME" --player_name "Italians" --port 5001 --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC" &
    PID_P2=$!
    python3 -u game_mcts.py --model_name "$MODEL_NAME" --player_name "Germans" --port 5002 --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC" &
    PID_P3=$!
    python3 -u game_mcts.py --model_name "$MODEL_NAME" --player_name "Chinese" --port 5003 --efficiency_file "$EFFICIENCY_REC" --outcome_file "$OUTCOME_REC" --quality_file "$QUALITY_REC" --rollout_file "$ROLLOUT_REC" &
    PID_P4=$!
    echo "Started MCTS agents"
    sleep 5
    python3 play_game.py > output_play.log 
    echo "Game finished."
    kill $PID_P1 2>/dev/null
    kill $PID_P2 2>/dev/null
    kill $PID_P3 2>/dev/null
    kill $PID_P4 2>/dev/null
done

end_time=$(date +%s)
elapsed=$((end_time - start_time))
echo "Time taken: ${elapsed} seconds"
