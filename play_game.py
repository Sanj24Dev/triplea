import subprocess
import time
import signal
import json
import os
import socket  

# --- CONFIG ---
PLAY_ROUNDS = 100   # max rounds per game
PLAY_GAMES = int(os.environ["GAMES_TO_PLAY"])     # number of games to play
CHECK_INTERVAL = 2  # seconds between log checks
FORFEIT_CHECK = 20

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


def consec_no_combat():
    try:
        with open(f"forfeit.flag", 'r') as f:
            return sum(1 for line in f)
    except FileNotFoundError:
        return 0

def main():
    with open("config.json", 'r') as f:
        data = json.load(f)

    root_folder = os.environ["PROJECT_ROOT"]
    log_folder = root_folder + "/logs/"
    log_file = os.path.join(log_folder, data["PLAYER_NAME"], f"{data['DEFAULT_GAME_NAME_PREF']}.log")

    games_played = 0
    rounds_till_last = 0
    prev_stopped = 0

    while games_played < PLAY_GAMES:
        process = start_game()
        prev_round = -1
        start_time = time.time()

        try:
            while True:
                # Process crashed or exited
                if process.poll() is not None:
                    print("Process ended unexpectedly.")
                    break

                # Check log status
                rounds = count_rounds(log_file)
                curr_stopped = count_stopped(log_file)

                if rounds > PLAY_ROUNDS or consec_no_combat() >= FORFEIT_CHECK:
                    print(f"{PLAY_ROUNDS} rounds completed. Ending game.")
                    rounds_till_last += rounds
                    notify_agent_game_end()
                    terminate_game(process)
                    clean_up_logfile(log_file)
                    # prev_stopped = curr_stopped
                    break


                if prev_stopped < curr_stopped:
                    print(f"Game stopped (winner detected). {curr_stopped} {prev_stopped}")
                    rounds_till_last += rounds
                    terminate_game(process)
                    clean_up_logfile(log_file)
                    # prev_stopped = curr_stopped
                    break

                if prev_round != rounds:
                    prev_round = rounds
                    print(f"Playing round {rounds}")

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Stopping current game.")
            notify_agent_game_end()
            terminate_game(process)
            break

        games_played += 1
        print(f"Completed game {games_played}/{PLAY_GAMES}")

        # Optional cooldown to let ports or files reset
        time.sleep(5)

    print("All games finished.")

if __name__ == "__main__":
    main()