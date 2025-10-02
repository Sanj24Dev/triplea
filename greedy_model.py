import socket
import json
# import numpy as np
import random
import networkx as nx
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
import re
import sys
import time

def parse_change_line(line: str):
    parts = line.strip().split()
    if not parts or parts[0] != "CHANGE":
        return None

    if parts[1] == "move":
        return {
            "action": "move",
            "unit": parts[2],
            "from": parts[4],
            "to": parts[6],
            "owner": parts[7].split("=")[1] if "owner=" in parts[7] else None
        }

    elif parts[1] == "buy":
        return {
            "action": "buy",
            "unit": parts[2],
            "territory": parts[4],
            "owner": parts[5].split("=")[1] if "owner=" in parts[5] else None
        }

    else:
        print("Unsupported CHANGE line:", line)
        return None


def parse_triplea_map(xml_path, output_path):
    # Parse the XML file
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # --- Extract Territories ---
    territories = [t.attrib["name"] for t in root.findall(".//map/territory")]

    # --- Extract Connections (graph edges between territories) ---
    connections = [
        {"from": conn.attrib["t1"], "to": conn.attrib["t2"]}
        for conn in root.findall(".//map/connection")
    ]

    # --- Extract Players ---
    players = [p.attrib["name"] for p in root.findall(".//playerList/player")]

    # --- Extract Units ---
    units = [u.attrib["name"] for u in root.findall(".//unitList/unit")]

    # --- Extract Production Rules ---
    production_rules = {}
    for rule in root.findall(".//production/productionRule"):
        name = rule.attrib["name"]
        cost = int(rule.find("cost").attrib["quantity"])
        unit = rule.find("result").attrib["resourceOrUnit"]
        production_rules[name] = {"unit": unit, "cost": cost}

    # --- Extract Starting Territory Ownership ---
    starting_ownership = {
        terr.attrib["territory"]: terr.attrib["owner"]
        for terr in root.findall(".//initialize/ownerInitialize/territoryOwner")
    }

    # --- Extract Starting Units per Territory ---
    starting_units = [
        {
            "unit": unit.attrib["unitType"],
            "territory": unit.attrib["territory"],
            "quantity": int(unit.attrib["quantity"]),
            "owner": unit.attrib.get("owner", "Neutral")
        }
        for unit in root.findall(".//initialize/unitInitialize/unitPlacement")
    ]

    # --- Extract Initial PU (Production Units) per Player ---
    initial_resources = {
        res.attrib["player"]: int(res.attrib["quantity"])
        for res in root.findall(".//initialize/resourceInitialize/resourceGiven")
    }

    # --- Extract Victory Cities (special territories) ---
    victory_cities = []
    for attach in root.findall(".//attachmentList/attachment[@type='territory']"):
        for opt in attach.findall("option"):
            if opt.attrib.get("name") == "victoryCity" and opt.attrib.get("value") == "1":
                victory_cities.append(attach.attrib["attachTo"])

    # --- Final structured data ---
    parsed_data = {
        "territories": territories,
        "connections": connections,
        "players": players,
        "units": units,
        "production_rules": production_rules,
        "starting_ownership": starting_ownership,
        "starting_units": starting_units,
        "initial_resources": initial_resources,
        "victory_cities": victory_cities
    }

    # Save to JSON file
    with open(output_path, "w") as f:
        json.dump(parsed_data, f, indent=2)

    print(f"Data successfully extracted and saved to {output_path}")



class CaptureTheFlagGraph:
    def __init__(self, json_path):
        with open(json_path, "r") as f:
            self.data = json.load(f)

        # Build initial graph
        self.G = nx.Graph()
        self._build_graph()

        #  only for display - can remove
        self.pos = nx.spring_layout(self.G, seed=42)
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.node_collection = nx.draw_networkx_nodes(
            self.G, self.pos, ax=self.ax,
            node_color=self._get_colors(), node_size=800
        )
        self.edge_collection = nx.draw_networkx_edges(self.G, self.pos, ax=self.ax)
        self.label_collection = nx.draw_networkx_labels(self.G, self.pos, ax=self.ax, font_size=8)

        plt.ion()
        plt.show()

    def _build_graph(self):
        # Add territories as nodes with attributes
        for territory in self.data["territories"]:
            owner = self.data["starting_ownership"].get(territory, "Neutral")
            self.G.add_node(territory, owner=owner, units=[], properties={"battle": False})       # do i need properties for a territory???

        # Add initial units
        for unit_info in self.data["starting_units"]:
            terr = unit_info["territory"]
            if terr in self.G.nodes:
                unit_entry = {
                    "unit": unit_info["unit"],
                    "owner": unit_info["owner"],
                    "quantity": unit_info["quantity"],
                    "properties": {}  # dynamic flags (e.g., has_moved, was_in_combat)
                }
                self.G.nodes[terr]["units"].append(unit_entry)

        # Add connections as edges
        for conn in self.data["connections"]:
            self.G.add_edge(conn["from"], conn["to"])

        self.G.owners = {}
        for owner, pu in self.data.get("initial_resources", {}).items():
            self.G.owners[owner] = {
                "name": owner,
                "PU": pu,
                "unplaced": {}  # dict of units -> qty
            }


    #  only for display - can remove
    def _get_colors(self):
        colors = []
        for node in self.G.nodes:
            owner = self.G.nodes[node].get("owner", None)
            if owner == "Russians":
                colors.append("red")
            elif owner == "Italians":
                colors.append("green")
            elif owner == "Germans":
                colors.append("black")
            elif owner == "Chinese":
                colors.append("yellow")
            else:
                colors.append("lightgray")
        return colors

    #  only for display - can remove
    def draw(self):
        border_colors = []
        labels = {}
        label_pos = {}

        # Build node colors and labels
        for node in self.G.nodes:
            owner = self.G.nodes[node].get("owner", None)
            units = self.G.nodes[node].get("units", [])

            # Border color
            if hasattr(self, "whoAmI") and owner == self.whoAmI:
                border_colors.append("gold")
            else:
                border_colors.append("black")

            # Unit label
            if units:
                unit_lines = [f"{u['quantity']} {u['unit']}" for u in units]
                labels[node] = "\n".join(unit_lines)
                x, y = self.pos[node]
                label_pos[node] = (x, y + 0.08)
            else:
                labels[node] = ""
                label_pos[node] = self.pos[node]

        
        # for territory in self.G.nodes:
        #     if self.G.nodes[territory]["properties"]["battle"]:
        #         self.G.nodes[territory]["shape"] = "octagon"
        #     else:
        #         # fallback shape if not in combat
        #         self.G.nodes[territory]["shape"] = "ellipse"


        # Edge colors (combat marking)
        edge_colors = []
        for u, v in self.G.edges:
            in_combat = False
            for node in (u, v):
                units = self.G.nodes[node].get("units", [])
                for unit in units:
                    props = self.G.graph.get("unit_properties", [])
                    for p in props:
                        if p["unit"] == unit["unit"] and p["owner"] == unit["owner"]:
                            if p["property"] == "wasInCombat" and p["new_value"] == "true":
                                in_combat = True
            edge_colors.append("red" if in_combat else "black")

        # Update visuals
        new_colors = self._get_colors()
        self.node_collection.set_facecolor(new_colors)
        self.node_collection.set_edgecolor(border_colors)
        self.node_collection.set_linewidth(2.0)

        self.edge_collection.set_edgecolor(edge_colors)
        self.edge_collection.set_linewidth(2.0)

        self.fig.set_size_inches(16, 16)

        # Remove previous labels if any
        if hasattr(self, "label_texts"):
            for txt in self.label_texts:
                txt.remove()
        self.label_texts = []

        # Draw shifted unit labels and keep references
        for node, (x, y) in label_pos.items():
            txt = self.ax.text(x, y, labels[node], fontsize=8, ha="left", va="center")
            self.label_texts.append(txt)

        if hasattr(self, "resource_text_box"):
            self.resource_text_box.remove()  # remove old box

        if hasattr(self.G, "owners"):
            lines = []
            for owner, pdata in self.G.owners.items():
                # Base line with PU
                line = f"{owner}: {pdata['PU']} PUs"

                # If unplaced units exist, append them inline
                if pdata["unplaced"]:
                    units_str = ", ".join(
                        [f"{qty} {utype}" for utype, qty in pdata["unplaced"].items()]
                    )
                    line += f" | Unplaced: {units_str}"

                lines.append(line)

            resource_text = "\n".join(lines)

            self.resource_text_box = self.ax.text(
                1.05, 0.5, resource_text, transform=self.ax.transAxes, fontsize=12,
                verticalalignment="center",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", edgecolor="black")
            )


        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()



    def update_my_role(self, role):
        self.whoAmI = role
        print(f"WHOAMI updated: {role}")

    def update_ownership(self, territory, new_owner):
        if territory in self.G.nodes:
            self.G.nodes[territory]["owner"] = new_owner
            print(f"{territory} is now owned by {new_owner}")

    def add_unit(self, territory, unit, owner, quantity=1, properties=None):
        """Add a unit to a territory or to a player's unplaced pool (purchase)."""
        if properties is None:
            properties = {}

        # --- Case 1: Territory placement ---
        if territory in self.G.nodes:
            for u in self.G.nodes[territory]["units"]:
                if u["unit"] == unit and u["owner"] == owner:
                    u["quantity"] += quantity
                    break
            else:
                self.G.nodes[territory]["units"].append({
                    "unit": unit,
                    "owner": owner,
                    "quantity": quantity,
                    "properties": properties
                })

            # Keep quick summary updated
            counts = self.G.nodes[territory].setdefault("unit_counts", {})
            counts[unit] = counts.get(unit, 0) + quantity

            print(f"Added {quantity} {unit}(s) for {owner} in {territory}")

        # --- Case 2: Purchase (unplaced pool) ---
        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) + quantity
            print(f"Purchased {quantity} {unit}(s) for {territory}")




    def remove_unit(self, territory, unit, owner, quantity=1):
        if territory in self.G.nodes:
            units = self.G.nodes[territory]["units"]
            for u in units:
                if u["unit"] == unit and u["owner"] == owner:
                    u["quantity"] -= quantity
                    if u["quantity"] <= 0:
                        units.remove(u)
                    break
            print(f"Removed {quantity} {unit}(s) of {owner} from {territory}")

        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) - quantity
            print(f"Placed {quantity} {unit}(s) for {territory}")


    def update_unit_property(self, unit, owner, prop, new_val):
        """
        Update a property for a specific unit in a territory.
        Automatically stores old value for reference.
        """
        if territory in self.G.nodes:
            for u in self.G.nodes[territory]["units"]:
                if u["unit"] == unit and u["owner"] == owner:
                    old_val = u["properties"].get(prop, None)
                    u["properties"][prop] = new_val
                    self.G.graph.setdefault("unit_properties", []).append({
                        "territory": territory,
                        "unit": unit,
                        "owner": owner,
                        "property": prop,
                        "old_value": old_val,
                        "new_value": new_val
                    })
                    print(f"Updated {unit} ({owner}) in {territory}: {prop} changed from {old_val} to {new_val}")
                    break


    def add_connection(self, from_t, to_t):
        self.G.add_edge(from_t, to_t, color="black")  # default color
        print(f"Connection added between {from_t} and {to_t}")

    def remove_connection(self, from_t, to_t):
        if self.G.has_edge(from_t, to_t):
            self.G.remove_edge(from_t, to_t)
            print(f"Connection removed between {from_t} and {to_t}")

    def update_pus(self, player, qty):
        self.G.owners[player]["PU"] += qty

    def add_battle_record(self, player, battle_id, territory):
        """
        Add a battle record to the graph.
        `battle` can include battle_id, type, and territory.
        """
        # self.G.graph.setdefault("battles", {}).setdefault(player, []).append(battle)
        self.G.nodes[territory]["properties"]["battle"] = True
        print(f"{player}: Battle at {territory}")




    def apply_change_line(ctf, line: str, ispartComposite):
        line = line.strip()

        # --- Role assignment ---
        m = re.search(r"Role: (\w+)", line)
        if m:
            role = m.group(1)
            ctf.update_my_role(role)
            return

        # havent checked in composite
        if "Adding Battle Records:" in line:
            m = re.search(r"Adding Battle Records: \[(.*?)\]", line)
            if m:
                records = m.groups()
                # Split into player=battles
                for part in records:
                    if "=" in part:
                        player, battles = part.split("=", 1)
                        player = player.strip()
                        battles = battles.strip()
                        id_terr = re.findall(r"([0-9a-f]+):.*?battle in (\w+)", battles)
                        for pair in id_terr:
                            battle_id, territory = pair
                            ctf.add_battle_record(player, battle_id, territory)
            return

        # --- CompositeChange ---
        if "CompositeChange" in line:
            # Extract sub-changes safely
            # Match until ], >, or end-of-line
            parts = re.findall(
                r"(Add unit change.*?(?:\[.*?\])?|Remove unit change.*?(?:\[.*?\])?|Resource:PUs.*?|takes .*? from .*?)(?:, |$)", 
                line
            )

            # print(parts)
            for p in parts:
                # print("\tDOING: ", p)
                ctf.apply_change_line(p, 1)
                
            return

        # --- Territory takes ---
        m = re.search(r"(\w+) takes (\w+) from (\w+)", line)
        if m:
            player, territory, old_owner = m.groups()
            ctf.update_ownership(territory, player)
            return

        # --- Add unit change ---
        m = re.search(r"Add unit change.*Add to: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")  # remove any trailing characters
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    ctf.add_unit(territory, unit.strip(), owner.strip())
            return

        # --- Remove unit change ---
        # apart from the territories, it also tells just the owners losing the units, understand why
        m = re.search(r"Remove unit change.*Remove from: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    ctf.remove_unit(territory, unit.strip(), owner.strip())
            return

        # # --- Resource change ---
        # # "Change resource"
        m = re.search(r"Resource:PUs quantity:(-?\d+) Player:(\w+)", line)
        if m:
            qty, player = m.groups()
            qty = int(qty)
            ctf.update_pus(player, qty)
            # ctf.G.graph.setdefault("resources", {})[player] = qty
            print(f"Updated resources for {player}: {ctf.G.owners[player]["name"]}")
            return

        # # --- Property change ---
        # ============================ SKIPPED since not all info is provided =======================
        m = re.search(
            r"Property change, unit:(\w+) owned by (\w+) property:(\w+) newValue:(\w+) oldValue:(\w+)", 
            line
        )
        if m:
            # Property change, unit:armour owned by Russians property:wasInCombat newValue:true oldValue:false
            unit, owner, prop, new_val, old_val = m.groups()
            # ctf.update_unit_property(unit.strip(), owner.strip(), prop.strip(), new_val.strip())
            return


        

        



class OnlineGreedyAgent:
    def __init__(self, state_dim, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        # self.w = np.zeros(state_dim, dtype=np.float32)

    # def value(self, s):
    #     return float(np.dot(self.w, s))

    # def update(self, s, r, s_next, done):
    #     v_s = self.value(s)
    #     v_next = 0.0 if done else self.value(s_next)
    #     delta = r + self.gamma * v_next - v_s
    #     self.w += self.alpha * delta * s

    # def select_action(self, state_vec, legal_actions, env_socket):
    #     # epsilon-greedy
    #     if random.random() < self.epsilon:
    #         return randomterritories.choice(legal_actions)

    #     best_score, best_action = -float("inf"), None
    #     for a in legal_actions:
    #         # ask TripleA to simulate (if supported) or approximate reward
    #         request = {"cmd": "simulate", "action": a}
    #         env_socket.send(json.dumps(request).encode("utf-8"))
    #         sim_response = json.loads(env_socket.recv(65536).decode("utf-8"))

    #         s_prime = np.array(sim_response["state_vec"], dtype=np.float32)
    #         r = sim_response["reward"]
    #         done = sim_response["done"]

    #         v_prime = 0 if done else self.value(s_prime)
    #         score = r + self.gamma * v_prime

    #         if score > best_score:
    #             best_score, best_action = score, a

    #     return best_action

    def get_move(line : str):
        x = 1
        print(line)
        # use regex to find what move am i playing, then predict the action







def agent_loop(state_dim, host="127.0.0.1", port=5000):
    agent = OnlineGreedyAgent(state_dim)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    print(f"Server listening on {host}:{port}")

    ctf.draw()


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

                if buffer.startswith("[MY_MOVE]"):
                    print(buffer)
                    # send back actions
                    # agent.get_move(buffer)
                else:
                    ctf.apply_change_line(buffer, 0)
                ctf.draw()

    except KeyboardInterrupt:
        sock.close()

    finally:
        # sock.close()
        # sys.exit(0)
        return
                
            # print(buffer)

        # msg = json.loads(data)
        # state_vec = np.array(msg["state_vec"], dtype=np.float32)
        # legal_actions = msg["legal_actions"]
        # reward = msg.get("reward", 0.0)
        # done = msg.get("done", False)

        # # update critic (needs previous state transition)
        # if "prev_state_vec" in msg:
        #     s_prev = np.array(msg["prev_state_vec"], dtype=np.float32)
        #     r_prev = msg["prev_reward"]
        #     agent.update(s_prev, r_prev, state_vec, done)

        # # select next action
        # action = agent.select_action(state_vec, legal_actions, sock)
        # sock.send(json.dumps({"action": action}).encode("utf-8"))

        # agent.epsilon *= agent.epsilon_decay


with open("config.json", 'r') as f:
    data = json.load(f)

xml_file = data["DEFAULT_GAME_URI_PREF"] # Path to your TripleA XML file
xml_file = xml_file.split("//")[1]
output_file = "gameInfo/" + data["DEFAULT_GAME_NAME_PREF"]+".json"  # Output JSON file

parse_triplea_map(xml_file, output_file)

ctf = CaptureTheFlagGraph("gameInfo/Capture The Flag.json")

agent_loop(10)

ts = time.strftime("%Y%m%d_%H%M%S")

# Save graph structure as JSON
json_file = f"final_graph_{ts}.json"
with open(json_file, "w") as f:
    json.dump(nx.node_link_data(ctf.G), f, indent=2)
print(f"Graph structure saved as {json_file}")

# Save figure as PNG
img_file = f"final_graph_{ts}.png"
ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
print(f"Graph exported as {img_file}")
print("\nShutting down...")

# conn, addr = server_socket.accept()
# print("Client connected from", addr)

# with conn:
#     buffer = ""
#     while True:
#         data = conn.recv(1024)
#         if not data:
#             break
#         buffer += data.decode()
#         # Expect newline-delimited CHANGE lines
#         while "\n" in buffer:
#             line, buffer = buffer.split("\n", 1)
#             if line.startswith("CHANGE"):
#                 gs.update_from_line(line)
#                 print("Current state vector:", gs.vectorize())