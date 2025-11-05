import socket
import json
import time
import os
import zipfile

import db_creation_helper as db
from online_greedy_agent import OnlineGreedyAgent
from capture_the_flag_graph import CaptureTheFlagGraph
from helper import parse_triplea_map, parse_purchase_line, parse_combat_line



def agent_loop(state_dim, host="127.0.0.1", port=5000):
    agent = OnlineGreedyAgent(state_dim)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    print(f"Server listening on {host}:{port}")

    ctf.draw()
    r = "0"
    episode = 1
    pu_before_move = 0
    pu_after_move = 0
    
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
                        # [INFO] Game stopped [PlayerId named: Russians]
                        elif msg.startswith("[INFO]") and parts[2] == "stopped":
                            # clear the graph
                            # json_file = f"final_graph_{ts}.json"
                            # print(f"Graph structure saved")
                            ctf.reset()
                            winner = parts[5].split("]")[0]
                            agent.latest_legal_moves = []   # reset agent memory if needed
                            r = "0"
                            dataset_path = f"{episode}purchase_dataset.jsonl" # zip this file and delete the text file
                            if os.path.exists(dataset_path):
                                zip_filename = f"{episode}purchase_{winner}_dataset.zip" 
                                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.write(dataset_path, arcname=os.path.basename(dataset_path))
                                os.remove(dataset_path)
                            else:
                                print("No dataset file found for this episode.")

                            dataset_path = f"{episode}combat_dataset.jsonl" # zip this file and delete the text file
                            if os.path.exists(dataset_path):
                                zip_filename = f"{episode}combat_{winner}_dataset.zip" 
                                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.write(dataset_path, arcname=os.path.basename(dataset_path))
                                os.remove(dataset_path)
                            else:
                                print("No dataset file found for this episode.")

                            dataset_path = f"{episode}noncombat_dataset.jsonl" # zip this file and delete the text file
                            if os.path.exists(dataset_path):
                                zip_filename = f"{episode}noncombat_{winner}_dataset.zip" 
                                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.write(dataset_path, arcname=os.path.basename(dataset_path))
                                os.remove(dataset_path)
                            else:
                                print("No dataset file found for this episode.")
                            
                            dataset_path = f"{episode}game_dataset.jsonl" # zip this file and delete the text file
                            if os.path.exists(dataset_path):
                                zip_filename = f"{episode}game_{winner}_dataset.zip" 
                                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.write(dataset_path, arcname=os.path.basename(dataset_path))
                                os.remove(dataset_path)
                            else:
                                print("No dataset file found for this episode.")
                            episode += 1
                        elif msg.startswith("[FOR_DB]"):
                            player = parts[1]
                            task = parts[2]
                            if task == "purchase": 
                                pu_before_move = ctf.get_player_resources(player)
                                agent.update_legal_moves(task, player, ctf)
                            elif task == "combat": 
                                pu_before_move = ctf.get_player_resources(player)
                                agent.update_legal_moves(task, player, ctf)
                            elif task == "noncombat": 
                                pu_before_move = ctf.get_player_resources(player)
                                agent.update_legal_moves(task, player, ctf)
                            elif task == "chosen":
                                chosen_delegate = parts[3]
                                move_msg = msg.strip().split("::")[1]
                                if chosen_delegate == "purchase":
                                    chosen_move = parse_purchase_line(ctf, player, move_msg)
                                    # print(agent.latest_legal_moves)
                                    # for legal_move in agent.latest_legal_moves:
                                    #     if chosen_move["purchase"] == legal_move["purchase"]:
                                    #         # print("Chosen move:", chosen_move)
                                    print("Saving purchase: Round=", r, " for ", player)
                                    pu_after_move = ctf.get_player_resources(player)
                                    db.save_delegate_json(state=agent.get_state_encoding(ctf, "purchase"), player=player, move_type="purchase", round_num=r, pu_before_move=pu_before_move, pu_after_move=pu_after_move, legal_moves=agent.latest_legal_moves, chosen_move=chosen_move, ep=episode)
                                            # break
                                elif chosen_delegate == "combat":
                                    chosen_move = parse_combat_line(ctf, player, move_msg)
                                    print("Saving combat: Round=", r, " for ", player)
                                    pu_after_move = ctf.get_player_resources(player)
                                    db.save_delegate_json(state=agent.get_state_encoding(ctf, "combat"), player=player, move_type="combat", round_num=r, pu_before_move=pu_before_move, pu_after_move=pu_after_move, legal_moves=agent.latest_legal_moves, chosen_move=chosen_move, ep=episode)
                                elif chosen_delegate == "noncombat":
                                    chosen_move = parse_combat_line(ctf, player, move_msg)
                                    print("Saving non-combat: Round=", r, " for ", player)
                                    pu_after_move = ctf.get_player_resources(player)
                                    db.save_delegate_json(state=agent.get_state_encoding(ctf, "noncombat"), player=player, move_type="noncombat", round_num=r, pu_before_move=pu_before_move, pu_after_move=pu_after_move, legal_moves=agent.latest_legal_moves, chosen_move=chosen_move, ep=episode)
                            else:
                                # print("Move: ", parts[1])
                                agent.update_legal_moves(task, player, ctf)
                            response = "ACK"
                        else:
                            ctf.apply_change_line(msg, 0)
                            response = "ACK"

                        # print("Sending:", response)
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
# json_file = f"final_graph_{ts}.json"
# with open(json_file, "w") as f:
#     json.dump(nx.node_link_data(ctf.G), f, indent=2)
# print(f"Graph structure saved as {json_file}")

# Save figure as PNG
# img_file = f"final_graph_{ts}.png"
# ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
# print(f"Graph exported as {img_file}")
print("\nShutting down...")

