import socket
import json
# import networkx as nx
import time

from ctf_graph import CaptureTheFlag
from helper import parse_triplea_map, convert_action_to_json
from combat_mcts_agent import MCTS

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--reduction_file", type=str, required=True)
parser.add_argument("--efficiency_file", type=str, required=True)
parser.add_argument("--outcome_file", type=str, required=True)
parser.add_argument("--quality_file", type=str, required=True)
parser.add_argument("--model_name", type=str, required=True)
args = parser.parse_args()

reduction_file = args.reduction_file
efficiency_file = args.efficiency_file
outcome_file = args.outcome_file
quality_file = args.quality_file
model_name = args.model_name


def agent_loop(host="127.0.0.1", port=5000):
    turn_order = ["Russians", "Italians", "Germans", "Chinese"]
    agent = MCTS(model_name, reduction_file, efficiency_file, quality_file, ctf.production_rules, ctf.territory_production, ctf.victory_cities, ctf.G, turn_order)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    print(f"Server listening on {host}:{port}")

    # ctf.draw()
    r = "0"
    my_player = ""

    try:
        # print("Waiting for accept()")
        while True:
            conn, addr = sock.accept()
            # print("Client connected from", addr)

            with conn:
                buffer = ""
                while True:
                    data = conn.recv(1024)
                    if not data:
                        # print("game disconnected")
                        break
                    buffer += data.decode()

                    while "\n" in buffer:
                        msg, buffer = buffer.split("\n", 1)
                        msg = msg.strip()
                        if not msg:
                            continue

                        response = "ACK"
                        parts = msg.strip().split(' ')
                        # if msg.startswith("[INFO]"):
                        #     print(parts)
                        if msg.startswith("[MY_MOVE]"):
                            response = agent.get_move(msg, ctf, r)
                            # response = []
                        elif msg.startswith("[INFO]") and "stopped" in msg: 
                            if "lost" in msg:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "lost")
                            elif parts[3] == my_player:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "won")
                            else:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "lost")
                            ctf.reset()
                            agent.latest_legal_moves = []   # reset agent memory
                            r = "0"
                            ctf.game_num += 1
                            print("Starting next game in 5s.")
                            time.sleep(5)
                        elif msg.startswith("[INFO]") and "Round" in msg:
                            r = parts[3]
                        elif msg.startswith("[INFO]") and "Role:" in msg:
                            ctf.apply_change_line(msg, 0)
                            my_player = parts[2]
                        else:
                            ctf.apply_change_line(msg, 0)
                            response = "ACK"

                        if response != "ACK":
                            print("Sending:", response)
                        conn.send((json.dumps(response) + "\n").encode("utf-8"))
                        # ctf.draw()


    except KeyboardInterrupt:
        sock.close()

    except Exception as e:
        print(e)
        time.sleep(4)

    finally:
        return
                


with open("config.json", 'r') as f:
    data = json.load(f)

xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

parse_triplea_map(xml_file, output_file)

with open(output_file, "r") as f:
    game_data = json.load(f)

ctf = CaptureTheFlag("gameInfo/Capture The Flag.json", outcome_file)
ctf.game_num = 1


agent_loop()

ts = time.strftime("%Y%m%d_%H%M%S")

# Save graph structure as JSON
json_file = f"final_graph_{ts}.json"
# with open(json_file, "w") as f:
#     json.dump(nx.node_link_data(ctf.G), f, indent=2)
print(f"Graph structure saved as {json_file}")

# Save figure as PNG
# img_file = f"final_graph_{ts}.png"
# ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
# print(f"Graph exported as {img_file}")
print("\nShutting down...")

