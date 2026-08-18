import socket
import json
# import networkx as nx
import time
import os

from ctf_graph import CaptureTheFlag, MetricLogger
from helper import parse_triplea_map, convert_action_to_json
from combat_mcts_agent import MCTS

import argparse

START_GAME_NUM = int(os.environ["START_GAME_NUM"]) 

parser = argparse.ArgumentParser()
parser.add_argument("--reduction_file", type=str, required=True)
parser.add_argument("--efficiency_file", type=str, required=True)
parser.add_argument("--outcome_file", type=str, required=True)
parser.add_argument("--quality_file", type=str, required=True)
parser.add_argument("--rollout_file", type=str, required=True)
parser.add_argument("--playerInfo_file", type=str, required=True)
parser.add_argument("--tree_info", type=str, required=True)
parser.add_argument("--model_name", type=str, required=True)
parser.add_argument("--game_num", type=str, required=True)
parser.add_argument("--opponent", type=str, required=False)
parser.add_argument("--player_name", type=str, required=True)
args = parser.parse_args()

reduction_file = args.reduction_file
efficiency_file = args.efficiency_file
outcome_file = args.outcome_file
quality_file = args.quality_file
rollout_file = args.rollout_file
playerInfo_file = args.playerInfo_file
tree_info = args.tree_info
model_name = args.model_name
g_num = int(args.game_num)
opponent = args.opponent
my_agent_name = args.player_name


def agent_loop(host="127.0.0.1", port=5000):
    turn_order = ["Russians", "Italians", "Germans", "Chinese"]
    turn_order = [t for t in turn_order if t in (my_agent_name, opponent)]
    print(turn_order)
    agent = MCTS(model_name, efficiency_file, quality_file, rollout_file, tree_info, ctf.production_rules, ctf.territory_production, ctf.victory_cities, ctf.G, turn_order, ctf.territories)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    print(f"Server listening on {host}:{port}")

    # ctf.draw()
    r = "0"
    my_player = ""
    prevCombat_empty = False
    FORFEIT_FLAG = f"forfeit.flag"
    start_time = time.time()

    try:
        # print("Waiting for accept()")
        game_end = False
        while True and not game_end:
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
                        # print(f"Received: {msg}")
                        response = "ACK"
                        parts = msg.strip().split(' ')
                        # if msg.startswith("[INFO]"):
                        #     print(parts)
                        if msg.startswith("[MY_MOVE]"):
                            response, isCombat = agent.get_move(msg, ctf, r)
                            if isCombat:
                                if response == []:
                                    if prevCombat_empty == True:
                                        # write to the file
                                        with open(FORFEIT_FLAG, "a") as f:
                                            f.write(f"empty combat in round={ctf.round} game={ctf.game_num}\n")
                                    prevCombat_empty = True
                                else:
                                    prevCombat_empty = False
                                    if os.path.exists(FORFEIT_FLAG):
                                        os.remove(FORFEIT_FLAG)

                            # response = []
                        elif msg.startswith("[INFO]") and "stopped" in msg: 
                            time_taken = time.time() - start_time
                            bracket_str = msg[msg.index("[", msg.index("]") + 1): msg.rindex("]") + 1]
                            players = [p.strip() for p in bracket_str.strip("[]").split(",") if p.strip()]
                            # print(bracket_str, "players:", players)
                            rank = 5 
                            for p in players:
                                rank -= 1
                                if p == my_player:
                                    break
                            if rank == 5:
                                rank = 0
                                
                            if "lost" in msg:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "lost", int(time_taken), rank, bracket_str)
                            elif parts[3] == my_player:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "won", int(time_taken), rank, bracket_str)
                            else:
                                ctf.game_outcome_metric.log(ctf.game_num, ctf.round, "lost", int(time_taken), rank, bracket_str)
                            ctf.reset()
                            agent.on_game_end()
                            agent.latest_legal_moves = []   # reset agent memory
                            r = "0"
                            ctf.game_num += 1
                            agent.terr_before_combat = 2
                            if os.path.exists(FORFEIT_FLAG):
                                os.remove(FORFEIT_FLAG)
                            print("Game ended")
                            game_end = True
                            # print("Starting next game in 1s.")
                            # time.sleep(1)
                        elif msg.startswith("[INFO]") and "Round" in msg:
                            r = parts[3]
                            if ctf.round != 0:
                                agent.pu_after_combat = ctf.players[ctf.whoAmI].PU
                                agent.terr_after_combat = sum(1 for t in ctf.territories.values() if t.owner == ctf.whoAmI)
                                agent.combat_quality.buffer(ctf.game_num, ctf.round, agent.pu_after_combat, agent.terr_after_combat)
                            ctf.round = int(r)
                        elif msg.startswith("[INFO]") and "Role:" in msg:
                            ctf.apply_change_line(msg, 0)
                            my_player = parts[2]
                            agent.update_whoAmI(my_player)
                            player_info.log(ctf.game_num, my_player, opponent)
                        else:
                            ctf.apply_change_line(msg, 0)
                            response = "ACK"
                        
                        if response != "ACK":
                            print("R", ctf.round," Sending:", response)
                        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

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

# xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
# xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

# parse_triplea_map(xml_file, output_file)

# with open(output_file, "r") as f:
#     game_data = json.load(f)

ctf = CaptureTheFlag("gameInfo/Capture The Flag.json", outcome_file)
ctf.game_num = g_num
print(f"Starting from game number: {ctf.game_num}")

player_info = MetricLogger(
            playerInfo_file,
            header=["game", "player", "opponent"]
        )

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

