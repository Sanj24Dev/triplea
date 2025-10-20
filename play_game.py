import subprocess
import time
import signal
import json
import xml.etree.ElementTree as ET


play_rounds = 3


def count_rounds(filename):
    try:
        with open(filename, 'r') as f:
            return sum(1 for line in f if "Round" in line)
    except FileNotFoundError:
        return 0

def main():

    with open("config.json", 'r') as f:
        data = json.load(f)

    # xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
    # xml_file = xml_file.split("//")[1]
    # output_file = "/home/sanjana/triplea/gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

    # parse_triplea_map(xml_file, output_file)





    process = subprocess.Popen(["./gradlew", ":game-app:game-headed:run"])
    root_log_folder = "/home/sanjana/triplea/logs/" # update this
    log_file = root_log_folder+data["PLAYER_NAME"]+"/"+data["DEFAULT_GAME_NAME_PREF"]+".log"

    prev_round = -1
    
    try:
        while True:
            if process.poll() is not None:
                print("Process ended\n")
                break
            rounds = count_rounds(log_file)
            if rounds > play_rounds:
                print(play_rounds, " rounds done\n")
                process.send_signal(signal.SIGINT)
                process.terminate()
                break
            if prev_round != rounds:
                prev_round = rounds
                print("Playing round ", rounds)

            # time.sleep(1)
    except KeyboardInterrupt:
        print("Keyboard interrupt\n")
        process.terminate()
    
    process.wait()

if __name__ == "__main__":
    main()