import socket
import json
import networkx as nx
import time

from capture_the_flag_graph import CaptureTheFlagGraph
from helper import parse_triplea_map, convert_action_to_json
from online_greedy_agent import OnlineGreedyAgent



def agent_loop(state_dim, host="127.0.0.1", port=5000):
    agent = OnlineGreedyAgent(state_dim)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    print(f"Server listening on {host}:{port}")

    ctf.draw()
    r = "0"

    try:
        while True:
            conn, addr = sock.accept()
            # print("Client connected from", addr)

            with conn:
                buffer = ""
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    buffer += data.decode()

                    while "\n" in buffer:
                        msg, buffer = buffer.split("\n", 1)
                        msg = msg.strip()
                        if not msg:
                            continue

                        response = "ACK"
                        parts = msg.strip().split(' ')
                        if msg.startswith("[MY_MOVE]"):
                            response = agent.get_move(msg, ctf)
                        elif msg.startswith("[INFO]") and len(parts) == 4:
                            r = parts[3]
                        elif msg.startswith("[INFO]") and parts[2] == "stopped":
                            ctf.reset()
                            agent.latest_legal_moves = []   # reset agent memory if needed
                            r = "0"
                        else:
                            ctf.apply_change_line(msg, 0)
                            response = "ACK"

                        print("Sending:", response)
                        conn.send((json.dumps(response) + "\n").encode("utf-8"))
                        ctf.draw()


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

ctf = CaptureTheFlagGraph("gameInfo/Capture The Flag.json")



agent_loop(10)

ts = time.strftime("%Y%m%d_%H%M%S")

# Save graph structure as JSON
json_file = f"final_graph_{ts}.json"
# with open(json_file, "w") as f:
#     json.dump(nx.node_link_data(ctf.G), f, indent=2)
print(f"Graph structure saved as {json_file}")

# Save figure as PNG
img_file = f"final_graph_{ts}.png"
ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
print(f"Graph exported as {img_file}")
print("\nShutting down...")

