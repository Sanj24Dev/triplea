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

# run the self play training
python self_play_training.py > training_log.txt 