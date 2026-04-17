import json
import os
import subprocess
import time

from helper import parse_triplea_map

# ---------- GLOBAL ENV VARS ----------
os.environ["PROJECT_ROOT"] = "/home/sanjana/tripleMindGNN"
os.environ["GAMES_TO_PLAY"] = "1"

os.environ["PLAYER_1"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_2"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_3"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_4"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
# PLAYER_TYPE_AI_EASY_LABEL

os.environ["PLAYER_1_PORT"] = "5010"
os.environ["PLAYER_2_PORT"] = "5011"
os.environ["PLAYER_3_PORT"] = "5012"
os.environ["PLAYER_4_PORT"] = "5013"

MODEL_NAME = "self_play_model"

EFFICIENCY_REC = f"{MODEL_NAME}/metrics/mcts_efficiency"
OUTCOME_REC = f"{MODEL_NAME}/metrics/game_outcome"
QUALITY_REC = f"{MODEL_NAME}/metrics/combat_quality"
ROLLOUT_REC = f"{MODEL_NAME}/metrics/rollout_efficiency"

NUM_GAMES = 1000
# doSync = False


def start_agent(player_name, port):
    # global doSync
    log = open(f"{MODEL_NAME}/player_logs/debug_{port}.log", "a")
    return subprocess.Popen(
        [
            "python3", "-u", "game_mcts.py",
            "--model_name", MODEL_NAME,
            # "--sync", str(doSync),
            "--player_name", player_name,
            "--port", str(port),
            "--efficiency_file", EFFICIENCY_REC,
            "--outcome_file", OUTCOME_REC,
            "--quality_file", QUALITY_REC,
            "--rollout_file", ROLLOUT_REC,
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

def stop_process(proc, port, timeout=10):
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
import zipfile

PROF_GLOB = f"{MODEL_NAME}/profiles/mcts_*.prof"
TARGET_FILE = "combat_policy_mcts_agent.py"
CSV_OUTPUT = f"{MODEL_NAME}/profiling/profile_data.csv"

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
                "cumtime": ct
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
                "time": t_dict["tottime"],   # Use cumtime for plotting total cost
                "cumtime": t_dict["cumtime"],
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


def cleanup():
    for f in glob.glob(f"{MODEL_NAME}/trees/*"):
        os.remove(f)

    for f in glob.glob(f"forfeit_*"):
        os.remove(f)

    print("Cleanup completed")


def save_zip(folder_path, zip_path):
    folder_path = os.path.abspath(folder_path)
    # zip_path = folder_path.rstrip("/") + ".zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if not file.endswith(".png"):
                    continue
                full_path = os.path.join(root, file)

                # keeps relative structure inside the zip
                arcname = os.path.relpath(full_path, folder_path)

                z.write(full_path, arcname)
    return zip_path




start_time = time.time()
print(f"Training started at {time.strftime('%Y-%m-%d %H:%M:%S')}")

with open("config.json", 'r') as f:
    data = json.load(f)

xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

parse_triplea_map(xml_file, output_file)

# run the trainer/learner process
pt = None
with open("trainer.log", "w") as log:
    pt = subprocess.Popen(["python3", "-u", "trainer.py"], stdout=log, stderr=log)
print(f"Trianer at {pt.pid}")

try:
    for i in range(1, NUM_GAMES + 1):
        os.environ["START_GAME_NUM"] = str(i)

        # clear the previously saved trees and flags before starting new game
        cleanup()

        game_start_time = time.time()

        p1 = start_agent("Russians", 5010)
        p2 = start_agent("Italians", 5011)
        p3 = start_agent("Germans", 5012)
        p4 = start_agent("Chinese", 5013)

        print(f"\nStarting Game {i}")
        time.sleep(5)

        log = open(f"{MODEL_NAME}/player_logs/game.log", "a")
        subprocess.run(["python3", "play_game.py"], stdout=log, stderr=log)

        time_taken = time.time() - game_start_time
        print(f"Game {i} finished in {int(time_taken)} seconds")
        time.sleep(5)


        stop_process(p1, 5010)
        stop_process(p2, 5011)
        stop_process(p3, 5012)
        stop_process(p4, 5013)

        time.sleep(5)
        save_profile()
        if i == 1 or i % 10 == 0:
            save_zip(f"{MODEL_NAME}/trees", f"{MODEL_NAME}/trees_g{i}.zip")
        
except KeyboardInterrupt:
    save_profile()


elapsed = time.time() - start_time
print(f"\nTime taken: {int(elapsed)} seconds")
kill_process(pt)

# ps aux | grep trainer.py
