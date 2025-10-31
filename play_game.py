import subprocess
import time
import signal
import json
import os

# --- CONFIG ---
PLAY_ROUNDS = 100   # max rounds per game
PLAY_GAMES = 2     # number of games to play
CHECK_INTERVAL = 2  # seconds between log checks

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
    """Start a new TripleA game process."""
    print("Starting new game...")
    return subprocess.Popen(["./gradlew", ":game-app:game-headed:run"])

def terminate_game(process):
    """Gracefully stop the current game."""
    print("Stopping current game...")
    try:
        process.send_signal(signal.SIGINT)
        time.sleep(2)
        process.terminate()
    except Exception as e:
        print("Error stopping process:", e)
    process.wait(timeout=10)

def main():
    with open("config.json", 'r') as f:
        data = json.load(f)

    root_log_folder = "/home/sanjana/triplea/logs/"
    log_file = os.path.join(root_log_folder, data["PLAYER_NAME"], f"{data['DEFAULT_GAME_NAME_PREF']}.log")

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
                rounds = count_rounds(log_file) - rounds_till_last
                curr_stopped = count_stopped(log_file)

                if rounds > PLAY_ROUNDS:
                    print(f"{PLAY_ROUNDS} rounds completed. Ending game.")
                    rounds_till_last += rounds
                    terminate_game(process)
                    prev_stopped = curr_stopped
                    break

                if prev_stopped < curr_stopped:
                    print(f"Game stopped (winner detected). {curr_stopped} {prev_stopped}")
                    rounds_till_last += rounds
                    terminate_game(process)
                    prev_stopped = curr_stopped
                    break

                if prev_round != rounds:
                    prev_round = rounds
                    print(f"Playing round {rounds}")

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Stopping current game.")
            terminate_game(process)
            break

        games_played += 1
        print(f"Completed game {games_played}/{PLAY_GAMES}")

        # Optional cooldown to let ports or files reset
        time.sleep(5)

    print("All games finished.")

if __name__ == "__main__":
    main()
