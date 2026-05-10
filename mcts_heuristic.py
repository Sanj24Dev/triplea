import json
import os
import subprocess
import time

from helper import parse_triplea_map

# ---------- GLOBAL ENV VARS ----------
os.environ["PROJECT_ROOT"] = "/home/sanjana/tripleMindMCTS"
os.environ["GAMES_TO_PLAY"] = "1"
# os.environ["PLAYER_ID"] = "3"

MODEL_NAME = "mcts_heuristic_v2"

REDUCTION_REC = f"{MODEL_NAME}/metrics/mcts_reduction.csv"
EFFICIENCY_REC = f"{MODEL_NAME}/metrics/mcts_efficiency.csv"
OUTCOME_REC = f"{MODEL_NAME}/metrics/game_outcome.csv"
QUALITY_REC = f"{MODEL_NAME}/metrics/combat_quality.csv"
ROLLOUT_REC = f"{MODEL_NAME}/metrics/rollout_efficiency.csv"
PLAYERINFO_REC = f"{MODEL_NAME}/metrics/player_info.csv"

NUM_GAMES = 100


def start_agent(player_name, port):
    log = open(f"{MODEL_NAME}/player_logs/debug_{port}.log", "w")
    return subprocess.Popen(
        [
            "python3", "-u", "game_mcts.py",
            "--model_name", MODEL_NAME,
            # "--player_name", player_name,
            # "--port", str(port),
            "--reduction_file", REDUCTION_REC,
            "--efficiency_file", EFFICIENCY_REC,
            "--outcome_file", OUTCOME_REC,
            "--quality_file", QUALITY_REC,
            "--rollout_file", ROLLOUT_REC,
            "--playerInfo_file", PLAYERINFO_REC,
        ],
        env=os.environ.copy(),
        stdout=log,
        stderr=log,
    )

def kill_process(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"{proc} ended")

def who_is_using_port(port):
    result = subprocess.run(
        ["lsof", "-i", f":{port}"],
        capture_output=True,
        text=True
    )
    print(f"lsof -i:{port} => {result.stdout}")

def stop_process(proc, port, timeout=5):
    try:
        # First wait politely
        proc.wait(timeout=timeout)
        print(f"Process {proc.pid} exited cleanly.")
    except subprocess.TimeoutExpired:
        print(f"Process {proc.pid} did not exit in {timeout}s. Terminating...")
        proc.terminate()  # sends SIGTERM

        try:
            proc.wait(timeout=5)
            print(f"Process {proc.pid} terminated gracefully.")
        except subprocess.TimeoutExpired:
            print(f"Process {proc.pid} still alive. Killing...")
            proc.kill()  # sends SIGKILL
            proc.wait()
            print(f"Process {proc.pid} killed.")
    
    who_is_using_port(port)


import pstats
import csv
import glob
import pandas as pd

main_folder = "mcts_heuristic_v2"  
PROF_GLOB = f"{main_folder}/profiles/mcts_*.prof"
TARGET_FILE = "combat_mcts_agent.py"
CSV_OUTPUT = f"{main_folder}/profiling/profile_data.csv"

per_profile = {}

def analyze_prof_file(fname):
    p = pstats.Stats(fname)
    p.strip_dirs()

    profile_name = fname
    per_profile[profile_name] = {}

    for func, stat in p.stats.items():
        file, line, name = func
        if TARGET_FILE in file:
            cc, nc, tt, ct, callers = stat

            key = f"{name}:{line}"
            # NEW: per profile stats
            per_profile[profile_name][key] = {
                "tottime": tt,
                "cumtime": ct,
                "ncalls": nc
            }
    per_profile[profile_name]["__total_time__"] = p.total_tt


def save_profile():
    global per_profile
    per_profile = {}
    records = []
    profiles = sorted(glob.glob(PROF_GLOB))
    for prof in profiles:
        analyze_prof_file(prof)
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
                "ncalls": t_dict["ncalls"], 
                "time": t_dict["tottime"],   # Use cumtime for plotting total cost
                "time_per_call": t_dict["tottime"] / t_dict["ncalls"] if t_dict["ncalls"] else 0, 
                "total_time": total_time
            })
        try:
            os.remove(prof)
        except Exception as e:
            print(e)

    if not records:
        return

    df = pd.DataFrame(records)
    # df.sort_values("time", ascending=False, inplace=True)
    file_exists = os.path.isfile(CSV_OUTPUT)

    df.to_csv(
        CSV_OUTPUT,
        mode="a",
        header=not file_exists,   # only write header if file doesn't exist
        index=False
    )

    print("Profile records saved")



start_time = time.time()
print(f"Games started at {time.strftime('%Y-%m-%d %H:%M:%S')}")

with open("config.json", 'r') as f:
    data = json.load(f)

xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

parse_triplea_map(xml_file, output_file)

players = ["Russians", "Italians", "Germans", "Chinese"]
ports = [5000, 5001, 5002, 5003]

for i in range(1, NUM_GAMES + 1):
    # the index of player in players * number of games per player gives the first game ID for that player
    p_id = os.environ.get("PLAYER_ID", "0")
    first_game_id_for_player = NUM_GAMES * int(p_id)
    os.environ["START_GAME_NUM"] = str(first_game_id_for_player + i)

    p = start_agent(players[int(p_id)], 5000)
    # p1 = start_agent("Russians", 5000)
    # p2 = start_agent("Italians", 5001)
    # p3 = start_agent("Germans", 5002)
    # p4 = start_agent("Chinese", 5003)

    print(f"\nStarting Game {i}")
    time.sleep(5)

    log = open(f"{MODEL_NAME}/player_logs/game.log", "w")
    subprocess.run(["python3", "play_game.py"], stdout=log, stderr=log)

    print(f"Game {i} finished.")
    time.sleep(5)


    # stop_process(p1, 5000)
    # stop_process(p2, 5001)
    # stop_process(p3, 5002)
    # stop_process(p4, 5003)
    stop_process(p, 5000)

    time.sleep(5)
    save_profile()

elapsed = time.time() - start_time
print(f"\nTime taken: {int(elapsed)} seconds")
