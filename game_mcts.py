import socket
import json
# import networkx as nx
import time
import os
import argparse

from ctf_graph import CaptureTheFlag, MetricLogger
from helper import parse_triplea_map, convert_action_to_json
from combat_policy_mcts_agent import PolicyGuidedMCTS
from nn_models.cnn.policy_value_net import PolicyValueNet
from nn_models.utils.move_db import get_dict_len
from nn_models.utils.encoding import build_grid_index_ctf



START_GAME_NUM = int(os.environ["START_GAME_NUM"]) 

parser = argparse.ArgumentParser()
parser.add_argument("--efficiency_file", type=str, required=True)
parser.add_argument("--outcome_file", type=str, required=True)
parser.add_argument("--quality_file", type=str, required=True)
parser.add_argument("--rollout_file", type=str, required=True)
parser.add_argument("--model_name", type=str, required=True)
# parser.add_argument("--sync", type=lambda x: x == "True")
parser.add_argument("--player_name", type=str, required=True)
parser.add_argument("--port", type=int, default=5000)
args = parser.parse_args()

port = args.port
efficiency_file = args.efficiency_file + f"_port{port}.csv"
outcome_file = args.outcome_file + f".csv"
quality_file = args.quality_file + f"_port{port}.csv"
rollout_file = args.rollout_file + f"_port{port}.csv"
model_name = args.model_name
# sync = args.sync

def log_message(port, message):
    filename = f"{args.model_name}/player_logs/port{port}.log"
    with open(filename, "a") as f:
        f.write(message + "\n")

def agent_loop(host="127.0.0.1", port=5000):
    turn_order = ["Russians", "Italians", "Germans", "Chinese"]
    net = PolicyValueNet(in_channels=12, grid_shape=(9,9), num_filters=64, num_res_blocks=5)
    grid_index = build_grid_index_ctf()
    grid_shape = (9,9)
    agent = PolicyGuidedMCTS(model_name, port, net, efficiency_file, quality_file, ctf.production_rules, ctf.territory_production, ctf.victory_cities, ctf.G, turn_order, grid_index, grid_shape)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    # except Exception as e:
    #     print(f"for {port}: {e}")
    sock.listen(1)
    # print(f"Server listening on {host}:{port}")
    log_message(port, f"Server started on {host}:{port}")

    # ctf.draw()
    r = "0"
    my_player = ""
    prevCombat_empty = False
    FORFEIT_FLAG = f"forfeit_{port}.flag"

    my_player = args.player_name
    ctf.update_my_role(my_player)
    agent.update_whoAmI(my_player)
    player_info.log(ctf.game_num, port, my_player)
    log_message(port, f"Game {ctf.game_num} Player {my_player} Role assigned")
    print(f"Game {ctf.game_num} Player {my_player} Role assigned")

    # always plays with the latest
    # print(sync)
    if ctf.game_num % 5 == 0:
        agent._sync_weights()

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
                                log_message("_dict", str(port) + " " + str(ctf.round) + " " + str(get_dict_len()))

                            # response = []
                        elif msg.startswith("[INFO]") and "stopped" in msg: 
                            # if my_player in msg:
                            #     ctf.game_outcome_metric.log(ctf.game_num, ctf.round, my_player)
                            #     log_message(port, f"Game {ctf.game_num} Round {ctf.round} Outcome: Won")
                            # else:
                            #     log_message(port, f"Game {ctf.game_num} Round {ctf.round} Outcome: lost")
                            
                            start = msg.index("[", msg.index("Game stopped"))
                            end   = msg.index("]", start)
                            inner = msg[start+1 : end]
                            players_in_order = [p.strip() for p in inner.split(",")]
                            # players_in_order = [first_elim, ..., winner] — winner is last
                            log_message(port, f"Player in order of elimination: {players_in_order}")
                            winner = players_in_order[-1]
                            eliminated = players_in_order[:-1]  # in elimination order
                            z = 0.0
                            for rank, player in enumerate(players_in_order):
                                if player == my_player:
                                    if rank == len(players_in_order) - 1:
                                        # i am the winner
                                        agent.curr_game_len = ctf.round
                                        z = 1.0
                                        ctf.game_outcome_metric.log(ctf.game_num, ctf.round, my_player)
                                        log_message(port, f"Game {ctf.game_num} Round {agent.curr_game_len}/{ctf.round} Outcome: Won Z: {z}")
                                        
                                    else:
                                        # i was eliminated, rank 0 = first out
                                        if agent.curr_game_len == 0:
                                            agent.curr_game_len = ctf.round
                                        z = 1.0 - (2.0 * (len(players_in_order) - 1 - rank) / (len(players_in_order) - 1))
                                        log_message(port, f"Game {ctf.game_num} Round {agent.curr_game_len}/{ctf.round} Outcome: lost Z: {z}")
                                        

                            agent.pu_after_combat = ctf.players[ctf.whoAmI].PU
                            agent.terr_after_combat = sum(1 for t in ctf.territories.values() if t.owner == ctf.whoAmI)
                            agent.combat_quality.log(ctf.game_num, ctf.round, agent.pu_after_combat, agent.terr_after_combat)
                            log_message(port, f"Game {ctf.game_num} ended. Starting next game in 5s.")
                            # won = my_player in msg and "lost" not in msg
                            # before = time.time()
                            # print(f"Weighted the samples with {agent.curr_game_len}")
                            agent.on_game_end(z, agent.curr_game_len, ctf.round)
                            # time_taken_to_save = time.time() - before
                            # log_message(port, f"Time taken to save: {time_taken_to_save}")
                            # reset everything for next game
                            ctf.reset()
                            agent.latest_legal_moves = []   # reset agent memory
                            agent.episode_examples = []
                            r = "0"
                            agent.curr_game_len = 0
                            # ctf.game_num += 1
                            # agent.terr_before_combat = 2
                            if os.path.exists(FORFEIT_FLAG):
                                os.remove(FORFEIT_FLAG)
                            # print("\n")
                            # time.sleep(5)
                            sock.close()
                            time.sleep(1)
                            exit(0)

                        elif msg.startswith("[INFO]") and "eliminated" in msg and my_player in msg:
                            agent.curr_game_len = ctf.round
                            log_message(port, f"{msg} in Round {agent.curr_game_len}")

                        elif msg.startswith("[INFO]") and "Round" in msg:
                            r = parts[3]
                            if ctf.round != 0:
                                agent.pu_after_combat = ctf.players[ctf.whoAmI].PU
                                agent.terr_after_combat = sum(1 for t in ctf.territories.values() if t.owner == ctf.whoAmI)
                                agent.combat_quality.log(ctf.game_num, ctf.round, agent.pu_after_combat, agent.terr_after_combat)
                                
                            ctf.round = int(r)

                        # elif msg.startswith("[INFO]") and "Role:" in msg:
                        #     ctf.apply_change_line(msg, 0)
                        #     my_player = parts[2]
                        #     agent.update_whoAmI(my_player)
                        #     player_info.log(ctf.game_num, port, my_player)
                        #     log_message(port, f"Game {ctf.game_num} Round {ctf.round} Player {my_player} Role assigned")
                        else:
                            ctf.apply_change_line(msg, 0)
                            response = "ACK"
                        
                        if response != "ACK":
                            # print("Sending:", response)
                            log_message(port, f"Game {ctf.game_num} Round {ctf.round} Player {my_player} Action: {response}")
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

with open(output_file, "r") as f:
    game_data = json.load(f)

ctf = CaptureTheFlag("gameInfo/Capture The Flag.json", outcome_file)
ctf.game_num = START_GAME_NUM
ctf.port = port

player_info = MetricLogger(
            f"{args.model_name}/metrics/player_info.csv",
            header=["game", "port", "player"]
        )

agent_loop(port=args.port)

ts = time.strftime("%Y%m%d_%H%M%S")

# Save graph structure as JSON
json_file = f"final_graph_{ts}.json"
# with open(json_file, "w") as f:
#     json.dump(nx.node_link_data(ctf.G), f, indent=2)
# print(f"Graph structure saved as {json_file}")

# Save figure as PNG
# img_file = f"final_graph_{ts}.png"
# ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
# print(f"Graph exported as {img_file}")
# print("\nShutting down...")



# elif msg.startswith("[INFO]") and "Game stopped" in msg:
#                             start = msg.index("[", msg.index("Game stopped"))
#                             end   = msg.index("]", start)
#                             inner = msg[start+1 : end]
#                             players_in_order = [p.strip() for p in inner.split(",")]
#                             # players_in_order = [first_elim, ..., winner] — winner is last
                            
#                             winner = players_in_order[-1]
#                             eliminated = players_in_order[:-1]  # in elimination order
#                             z =
#                             for rank, player in enumerate(players_in_order):
#                                 if player == my_player:
#                                     if rank == len(players_in_order) - 1:
#                                         # i am the winner
#                                         z = 1.0
#                                         ctf.game_outcome_metric.log(ctf.game_num, ctf.round, my_player)
#                                         log_message(port, f"Game {ctf.game_num} Round {ctf.round} Outcome: Won Z: {z}")
#                                     else:
#                                         # i was eliminated, rank 0 = first out
#                                         z = 1.0 - (2.0 * (len(players_in_order) - 1 - rank) / (len(players_in_order) - 1))
#                                         log_message(port, f"Game {ctf.game_num} Round {ctf.round} Outcome: lost Z: {z}")
                            
#                             agent.pu_after_combat = ctf.players[ctf.whoAmI].PU
#                             agent.terr_after_combat = sum(1 for t in ctf.territories.values() if t.owner == ctf.whoAmI)
#                             agent.combat_quality.log(ctf.game_num, ctf.round, agent.pu_after_combat, agent.terr_after_combat)
#                             log_message(port, f"Game {ctf.game_num} ended. Starting next game in 5s.")
#                             # won = my_player in msg and "lost" not in msg
#                             # before = time.time()
#                             agent.on_game_end(z)
#                             # time_taken_to_save = time.time() - before
#                             # log_message(port, f"Time taken to save: {time_taken_to_save}")
#                             # reset everything for next game
#                             ctf.reset()
#                             agent.latest_legal_moves = []   # reset agent memory
#                             agent.episode_examples = []
#                             r = "0"
#                             # ctf.game_num += 1
#                             agent.terr_before_combat = 2
#                             if os.path.exists(FORFEIT_FLAG):
#                                 os.remove(FORFEIT_FLAG)
                            
#                             # time.sleep(5)
#                             sock.close()
#                             time.sleep(1)
#                             exit(0)