import subprocess
import time
import signal
import json
import os
import socket  
from typing import List, Dict

# --- CONFIG ---
PLAY_ROUNDS = 2   # max rounds per game
PLAY_GAMES = int(os.environ["GAMES_TO_PLAY"])     # number of games to play
CHECK_INTERVAL = 2  # seconds between log checks
FORFEIT_CHECK = 20

PORT_ENV_VARS = ("PLAYER_1_PORT", "PLAYER_2_PORT", "PLAYER_3_PORT", "PLAYER_4_PORT")

def _get_active_ports() -> List[int]:
    """Collect active AI ports from environment variables."""
    ports: List[int] = []
    for k in PORT_ENV_VARS:
        v = os.getenv(k)
        if not v:
            continue
        try:
            ports.append(int(v))
        except ValueError:
            print(f"[WARN] Ignoring invalid port in {k}={v!r}")
    # de-dup, stable order
    seen = set()
    out = []
    for p in ports:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out

def notify_agent_game_end(host="127.0.0.1", port=5000):
    # send a line that game_mcts.py can interpret as a stop
    # keep it simple: include "stopped" and "lost" so it goes down the existing branch
    msg = f"[INFO] game stopped lost\n"
    try:
        with socket.create_connection((host, port), timeout=2) as s:
            s.sendall(msg.encode("utf-8"))
            _ = s.recv(1024)  # read ACK/json, optional
    except Exception as e:
        print("Could not notify agent:", e)


def count_rounds(filename):
    """Count lines containing 'Round'."""
    try:
        with open(filename, 'r') as f:
            return sum(1 for line in f if "Round" in line)
    except FileNotFoundError:
        return 0

def count_stopped(filename):
    """Check if log contains 'stopped' indicating game over."""
    try:
        with open(filename, 'r') as f:
            return sum(1 for line in f if "stopped" in line)
    except FileNotFoundError:
        return False
    return False

def start_game():
    print("Starting new game...\n")
    return subprocess.Popen(["./gradlew", ":game-app:game-headed:run"])

def clean_up_logfile(filename):
    try:
        with open(filename, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    last_stopped_idx = -1
    for i, line in enumerate(lines):
        if "stopped" in line:
            last_stopped_idx = i

    # Rewrite file
    with open(filename, "w") as f:
        if last_stopped_idx != -1:
            f.writelines(lines[last_stopped_idx + 1:])

def terminate_game(process):
    print("Stopping current game...")
    try:
        process.send_signal(signal.SIGINT)
        time.sleep(2)
        process.terminate()
    except Exception as e:
        print("Error stopping process:", e)
    process.wait(timeout=10)


def consec_no_combat(port):
    try:
        with open(f"forfeit_{port}.flag", 'r') as f:
            return sum(1 for line in f)
    except FileNotFoundError:
        return 0

def _build_log_files(root_folder: str, data: Dict, ports: List[int]) -> Dict[int, str]:
    """Map each port to its expected log file path."""
    log_folder = os.path.join(root_folder, "logs")
    game_name = data["DEFAULT_GAME_NAME_PREF"]

    log_files: Dict[int, str] = {}
    for port in ports:
        # Your logs look like: logs/player_5001/Capture The Flag.log
        player_dir = f"player_{port}"
        log_files[port] = os.path.join(log_folder, player_dir, f"{game_name}.log")
    return log_files

def main():
    with open("config.json", 'r') as f:
        data = json.load(f)

    root_folder = os.environ["PROJECT_ROOT"]
    
    ports = _get_active_ports()
    if not ports:
        # Fallback: old behavior via config.json
        log_folder = os.path.join(root_folder, "logs")
        log_file = os.path.join(log_folder, data["PLAYER_NAME"], f"{data['DEFAULT_GAME_NAME_PREF']}.log")
        ports = [5000]
        log_files = {5000: log_file}
        print(f"[WARN] No PLAYER_*_PORT env vars found; falling back to {log_file}")
    else:
        log_files = _build_log_files(root_folder, data, ports)
    

    games_played = 0
    prev_stopped: Dict[int, int] = {p: 0 for p in ports}

    while games_played < PLAY_GAMES:
        process = start_game()
        prev_round = -1

        try:
            while True:
                # Process crashed or exited
                if process.poll() is not None:
                    print("Process ended unexpectedly.")
                    break

                # Check log status
                rounds = 0
                for p in ports:
                    rounds = max(rounds, count_rounds(log_files[p]))
                stopped_now: Dict[int, int] = {p: count_stopped(log_files[p]) for p in ports}
                forfeit_score = 0
                for p in ports:
                    forfeit_score = max(forfeit_score, consec_no_combat(p))

                if rounds > PLAY_ROUNDS or forfeit_score >= FORFEIT_CHECK:
                    print(f"{PLAY_ROUNDS} rounds completed. Ending game.")
                    # for p in ports:
                    #     notify_agent_game_end(host="127.0.0.1", port=p)
                    terminate_game(process)
                    for p in ports:
                        clean_up_logfile(log_files[p])
                        prev_stopped[p] = stopped_now[p]
                    break


                if any(prev_stopped[p] < stopped_now[p] for p in ports):
                    inc_ports = [p for p in ports if prev_stopped[p] < stopped_now[p]]
                    print(f"Game stopped (winner detected) via ports: {inc_ports}")
                    # for p in ports:
                    #     notify_agent_game_end(host="127.0.0.1", port=p)
                    terminate_game(process)
                    for p in ports:
                        clean_up_logfile(log_files[p])
                        prev_stopped[p] = stopped_now[p]
                    break

                if prev_round != rounds:
                    prev_round = rounds
                    print(f"Playing round {rounds}")

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Stopping current game.")
            for p in ports:
                notify_agent_game_end(host="127.0.0.1", port=p)
            terminate_game(process)
            break

        games_played += 1
        print(f"Completed game {games_played}/{PLAY_GAMES}")

        # Optional cooldown to let ports or files reset
        time.sleep(5)

    print("All games finished.")

if __name__ == "__main__":
    main()