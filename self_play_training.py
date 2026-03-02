import json
import os
import subprocess
import time

from helper import parse_triplea_map

# ---------- GLOBAL ENV VARS ----------
os.environ["PROJECT_ROOT"] = "/home/sanjana/tripleMind"
os.environ["GAMES_TO_PLAY"] = "1"

os.environ["PLAYER_1"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_2"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_3"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"
os.environ["PLAYER_4"] = "startup.PlayerTypes.PLAYER_TYPE_AI_TRIPLE_MIND_LABEL"

os.environ["PLAYER_1_PORT"] = "5000"
os.environ["PLAYER_2_PORT"] = "5001"
os.environ["PLAYER_3_PORT"] = "5002"
os.environ["PLAYER_4_PORT"] = "5003"

MODEL_NAME = "self_play_model"

EFFICIENCY_REC = f"{MODEL_NAME}/metrics/mcts_efficiency"
OUTCOME_REC = f"{MODEL_NAME}/metrics/game_outcome"
QUALITY_REC = f"{MODEL_NAME}/metrics/combat_quality"
ROLLOUT_REC = f"{MODEL_NAME}/metrics/rollout_efficiency"

NUM_GAMES = 20


def start_agent(player_name, port):
    return subprocess.Popen(
        [
            "python3", "-u", "game_mcts.py",
            "--model_name", MODEL_NAME,
            "--player_name", player_name,
            "--port", str(port),
            "--efficiency_file", EFFICIENCY_REC,
            "--outcome_file", OUTCOME_REC,
            "--quality_file", QUALITY_REC,
            "--rollout_file", ROLLOUT_REC,
        ],
        env=os.environ.copy()
    )


def kill_process(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


start_time = time.time()

with open("config.json", 'r') as f:
    data = json.load(f)

xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

parse_triplea_map(xml_file, output_file)

# run the trainer/learner process
# subprocess.Popen(["python3", "trainer_learner.py"])

for i in range(1, NUM_GAMES + 1):
    os.environ["START_GAME_NUM"] = str(i)

    p1 = start_agent("Russians", 5000)
    p2 = start_agent("Italians", 5001)
    p3 = start_agent("Germans", 5002)
    p4 = start_agent("Chinese", 5003)

    print("Started MCTS agents")
    time.sleep(5)

    subprocess.run(["python3", "play_game.py"])

    print("Game finished.")

    kill_process(p1)
    kill_process(p2)
    kill_process(p3)
    kill_process(p4)

elapsed = time.time() - start_time
print(f"Time taken: {int(elapsed)} seconds")