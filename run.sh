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
# export PROJECT_ROOT="/storage/home/hcoda1/6/snayak89/tripleMind"

# source torch_env/bin/activate

MODEL_NAME="self_play_model"

rm -f $MODEL_NAME/test/metrics/*
rm -f $MODEL_NAME/test/player_logs/*
rm -f $MODEL_NAME/test/profiles/*
rm -f $MODEL_NAME/test/profiling/*
rm ../logs/player_5010/Capture\ The\ Flag.log
rm ../logs/player_5011/Capture\ The\ Flag.log
rm ../logs/player_5012/Capture\ The\ Flag.log
rm ../logs/player_5013/Capture\ The\ Flag.log
# run the self play training
python -u self_play_testing.py > testing_log.txt 