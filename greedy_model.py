import itertools
import socket
import json
import numpy as np
import random
import networkx as nx
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
import re
import sys
import time
from collections import deque
import csv
import os
import zipfile

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

    # --- Extract Units with Stats (attack, defense, movement) ---
    unit_stats = {}
    for attach in root.findall(".//attachmentList/attachment[@type='unitType']"):
        unit_name = attach.attrib["attachTo"]
        stats = {}
        for opt in attach.findall("option"):
            name = opt.attrib.get("name")
            value = opt.attrib.get("value")
            if name in ("attack", "defense", "movement"):
                stats[name] = int(value)
        if stats:
            unit_stats[unit_name] = stats

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
        "unit_stats": unit_stats,
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
        self.production_rules = {}  # e.g., {"infantry": {"cost": 3, "attack": 1, "defense": 2, ...}}
        self.victory_cities = set()
        self.unit_info = {}  # general unit metadata (range, move type, etc.)
        self.turn_number = 1

        self.pending_props = {}

        self._build_graph()
        self._load_metadata()

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
                "PU": int(pu),
                "latest_loc": "", # to maintain the latest owner=territory that got updated, for logs that do not mention any territory that the unit belongs to 
                "unplaced": {}  # dict of units -> qty
            }

    def _load_metadata(self):
        # --- Load Production Rules with Unit Stats ---
        unit_stats = self.data.get("unit_stats", {})   

        for key, rule in self.data["production_rules"].items():
            unit_name = rule["unit"]
            stats = unit_stats.get(unit_name, {})      

            self.production_rules[unit_name] = {
                "cost": rule["cost"],
                "attack": stats.get("attack", 0),      
                "defense": stats.get("defense", 0),
                "move": stats.get("movement", 1),
                "type": rule.get("type", "land")
            }

        # --- Store Unit and Victory City Info ---
        self.unit_info = self.data.get("units", {})
        self.victory_cities = set(self.data.get("victory_cities", []))


    def reset(self):
        """Reset graph state to initial configuration."""
        self.G.clear()
        self._build_graph()
        self._load_metadata()
        self.turn_number = 1
        print("Graph reset complete.")


    #  only for display - can remove
    def _get_colors(self):
        colors = []
        for node in self.G.nodes:
            owner = self.G.nodes[node].get("owner", None)
            if owner == "Russians":
                colors.append("brown")
            elif owner == "Italians":
                colors.append("green")
            elif owner == "Germans":
                colors.append("blue")
            elif owner == "Chinese":
                colors.append("purple")
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
                unit_lines = []
                for u in units:
                    props = u.get("properties", {})
                    in_combat = str(props.get("wasInCombat", "")).lower() == "true"
                    tag = " [inCombat]" if in_combat else ""
                    unit_lines.append(f"{u['quantity']} {u['unit']} ({u['owner']}){tag}")
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



        # Update visuals
        new_colors = self._get_colors()
        self.node_collection.set_facecolor(new_colors)
        self.node_collection.set_edgecolor(border_colors)
        self.node_collection.set_linewidth(2.0)

        # self.edge_collection.set_edgecolor(edge_colors)
        # self.edge_collection.set_linewidth(3.0)
        # self.edge_collection.set_zorder(1)
        # self.node_collection.set_zorder(2)

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
            self.G.owners[new_owner]["latest_loc"] = territory
            # print(f"{territory} is now owned by {new_owner}")

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

            # print(f"Added {quantity} {unit}(s) for {owner} in {territory}")

        # --- Case 2: Purchase (unplaced pool) ---
        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) + quantity
            # print(f"Purchased {quantity} {unit}(s) for {territory}")




    def remove_unit(self, territory, unit, owner, quantity=1):
        if territory in self.G.nodes:
            units = self.G.nodes[territory]["units"]
            for u in units:
                if u["unit"] == unit and u["owner"] == owner:
                    u["quantity"] -= quantity
                    if u["quantity"] <= 0:
                        units.remove(u)
                    break
            # print(f"Removed {quantity} {unit}(s) of {owner} from {territory}")

        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) - quantity
            # print(f"Placed {quantity} {unit}(s) for {territory}")


    def update_unit_property(self, unit, owner, prop, new_val):
        """
        Update a property for a specific unit in a territory.
        Automatically stores old value for reference.
        """
        if not hasattr(self, "pending_props"):
            self.pending_props = {}
        territory = self.G.owners[owner]["latest_loc"]
        if territory and territory in self.G.nodes:
            for u in self.G.nodes[territory]["units"]:
                if u["unit"] == unit and u["owner"] == owner:
                    old_val = u["properties"].get(prop, None)
                    u["properties"][prop] = new_val
                    # print(f"Updated {unit} ({owner}) in {territory}: {prop} changed from {old_val} to {new_val}")
                    break
            else:
                self.pending_props[prop] = new_val
                # print(f"Updated pending props: {self.pending_props}")



    def add_connection(self, from_t, to_t):
        self.G.add_edge(from_t, to_t, color="black")  # default color
        # print(f"Connection added between {from_t} and {to_t}")

    def remove_connection(self, from_t, to_t):
        if self.G.has_edge(from_t, to_t):
            self.G.remove_edge(from_t, to_t)
            # print(f"Connection removed between {from_t} and {to_t}")

    def update_pus(self, player, qty):
        self.G.owners[player]["PU"] += qty
        # print(f"Updated resources for {player}: {self.G.owners[player]["PU"]}")

    def add_battle_record(self, player, battle_id, territory):
        """
        Add a battle record to the graph.
        `battle` can include battle_id, type, and territory.
        """
        # self.G.graph.setdefault("battles", {}).setdefault(player, []).append(battle)
        self.G.nodes[territory]["properties"]["battle"] = True
        # print(f"{player}: Battle at {territory}")




    def apply_change_line(self, line: str, ispartComposite):
        line = line.strip()
        # print(f"SEARCHING  {line}")

        # --- Role assignment ---
        m = re.search(r"Role: (\w+)", line)
        if m:
            role = m.group(1)
            self.update_my_role(role)
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
                            self.add_battle_record(player, battle_id, territory)
            return

        # --- CompositeChange ---
        if "CompositeChange" in line:
            # Collect the text inside the top-level CompositeChange <[ ... ]>
            start = line.find("<[")
            if start == -1:
                return
            start += 2
            depth = 1
            inner = []
            for i in range(start, len(line)):
                if line[i:i+2] == "<[":
                    depth += 1
                    inner.append(line[i:i+2])
                    continue
                if line[i:i+2] == "]>":
                    depth -= 1
                    if depth == 0:
                        break
                    inner.append(line[i:i+2])
                    continue
                inner.append(line[i])

            inner_text = ''.join(inner)

            # Split at commas that start a new sub-change
            parts = re.split(
                r", (?=(?:Property change|Add unit change|Remove unit change|Change resource|takes |CompositeChange ))",
                inner_text
            )

            for p in parts:
                p = p.strip()
                if p:
                    self.apply_change_line(p, 1)
            return

        # --- Territory takes ---
        m = re.search(r"(\w+) takes (\w+) from (\w+)", line)
        if m:
            player, territory, old_owner = m.groups()
            self.update_ownership(territory, player)
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
                    self.add_unit(territory, unit.strip(), owner.strip())
                    if self.pending_props != {}:
                        for key in self.pending_props.keys():
                            self.update_unit_property(unit.strip(), owner.strip(), key, self.pending_props[key])
                        self.pending_props = {}
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
                    self.remove_unit(territory, unit.strip(), owner.strip())
            return

        # # --- Resource change ---
        # # "Change resource"
        m = re.search(r"Resource:PUs quantity:(-?\d+) Player:(\w+)", line)
        if m:
            qty, player = m.groups()
            qty = int(qty)
            self.update_pus(player, qty)
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
            self.update_unit_property(unit.strip(), owner.strip(), prop.strip(), new_val.strip())
            return

    def get_factories(self, player):
        factories = []
        for territory, data in self.G.nodes(data=True):
            for unit in data["units"]:
                if unit["owner"] == player and unit["unit"] == "factory":
                    factories.append(territory)
        return factories
    
    def get_player_resources(self, player):
        return self.G.owners[player]["PU"]
    

def generate_legal_purchase_moves(ctf, player):
    ctf.G.owners[ctf.whoAmI]["unplaced"].clear()
    # print("Before purchase: ", ctf.G.owners[ctf.whoAmI]["unplaced"])
    rules = ctf.production_rules
    resources = ctf.get_player_resources(player)
    factories = ctf.get_factories(player)

    if not factories:
        return []  # can't build if no factory

    # Extract unit costs
    units = [(name, data["cost"]) for name, data in rules.items()]

    legal_moves = []

    # brute force: try buying up to floor(resources/min_cost) units
    min_cost = min(cost for _, cost in units)
    max_units = resources // min_cost

    # We generate combinations of units with repetition
    for r in range(1, max_units + 1):
        for combo in itertools.combinations_with_replacement(units, r):
            total_cost = sum(cost for _, cost in combo)
            if total_cost <= resources:
                purchase_dict = {}
                for unit, cost in combo:
                    purchase_dict[unit] = purchase_dict.get(unit, 0) + 1
                # Each purchase is assigned to a factory (simplest: evenly distribute) 
                legal_moves.append({
                    "purchase": purchase_dict,
                    "cost": total_cost,
                    "place_in": factories  # player chooses where later - not necessary to mention as it always is placed in a factory
                })

    return legal_moves

def print_legal_moves(moves):
    for move in moves:
        print(f"Purchase: {move['purchase']}, Cost: {move['cost']}, Place in: {move['place_in']}")


def generate_legal_combat_moves(ctf, player):
    legal_moves = []

    for terr, data in ctf.G.nodes(data=True):
        if data.get("owner") != player:
            continue

        for u in data.get("units", []):
            if u["owner"] != player or u["quantity"] <= 0:
                continue

            move_range = ctf.production_rules.get(u["unit"], {}).get("move", 1)
            if move_range <= 0 or u["unit"] in ("factory", "aaGun"):
                continue

            # BFS traversal: (current_territory, steps, path)
            queue = deque([(terr, 0, [terr])])
            visited = set([terr])

            while queue:
                current, steps, path = queue.popleft()
                if steps >= move_range:
                    continue

                for neighbor in ctf.G.neighbors(current):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)

                    neighbor_owner = ctf.G.nodes[neighbor].get("owner", None)
                    if neighbor_owner == player:
                        continue  # cannot move through own territories in combat

                    # Record as a valid attack destination
                    legal_moves.append({
                        "delegate": "combat",
                        "from": terr,
                        "to": neighbor,
                        "steps": steps + 1,
                        "units": u["unit"],
                        "max_quantity": u["quantity"],
                        "target_owner": neighbor_owner,
                        "path": path + [neighbor]
                    })

                    # Continue expanding if still within move limit
                    if steps + 1 < move_range:
                        queue.append((neighbor, steps + 1, path + [neighbor]))

    return legal_moves

def generate_legal_noncombat_moves(ctf, player):
    legal_moves = []

    for terr, data in ctf.G.nodes(data=True):
        if data.get("owner") != player:
            continue

        for u in data.get("units", []):
            if u["owner"] != player or u["quantity"] <= 0:
                continue

            move_range = ctf.production_rules.get(u["unit"], {}).get("move", 1)
            if move_range <= 0 or u["unit"] in ("factory", "aaGun"):
                continue

            # BFS: explore up to move_range steps through friendly territories
            queue = deque([(terr, 0, [terr])])
            visited = set([terr])

            while queue:
                current, steps, path = queue.popleft()
                if steps >= move_range:
                    continue

                for neighbor in ctf.G.neighbors(current):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)

                    neighbor_owner = ctf.G.nodes[neighbor].get("owner", None)

                    # For non-combat, must stay within friendly territories
                    if neighbor_owner != player:
                        continue  # can't move into or through enemy/neutral

                    # Valid non-combat move (repositioning)
                    move = {
                        "delegate": "nonCombat",
                        "from": terr,
                        "to": neighbor,
                        "steps": steps + 1,
                        "units": u["unit"],
                        "max_quantity": u["quantity"],
                        "target_owner": neighbor_owner,
                        "path": path + [neighbor]
                    }
                    legal_moves.append(move)

                    # Continue exploring friendly chain up to move_range
                    if steps + 1 < move_range:
                        queue.append((neighbor, steps + 1, path + [neighbor]))

    return legal_moves

def generate_legal_place_moves(ctf, player):
    # print("Before place: ", ctf.G.owners[ctf.whoAmI]["unplaced"])
    factories = ctf.get_factories(player)

    if not factories:
        return []  # can't build if no factory

    # Extract unit costs
    unplaced_units = [u for u in ctf.G.owners[player]["unplaced"]]

    if not unplaced_units:
        return []

    # Each unit can go to any factory or "None" (not placed)
    placement_options = [factories + [None] for _ in unplaced_units]

    # Cartesian product → all combinations of choices
    all_combinations = itertools.product(*placement_options)

    legal_moves = []
    for combo in all_combinations:
        # Build the list of (unit, factory) for all placed ones
        moves = [{"unit":unit, "to":place_in} for unit, place_in in zip(unplaced_units, combo) if place_in is not None]
        legal_moves.append(moves)

    return legal_moves


def print_moves(moves):
    for m in moves:
        print(m)

def convert_action_to_json(move, move_type):
    actions = []
    if move_type == "purchase":
        place_in = move.get("place_in", [])
        if not place_in:
            raise ValueError("Missing 'place_in' in move")

        target_location = place_in[0]  # Assuming one placement location
        for unit, qty in move.get("purchase", {}).items():
            for _ in range(qty):
                actions.append({
                    "delegate": move_type,
                    "unit": unit,
                    "from": "",
                    "to": target_location
                })

    # elif move_type == "combat":
    #     for m in move:
    #         action = {
    #             "delegate": move_type,
    #             "from": m.get("from"),
    #             "to": m.get("to"),
    #             # "steps": move.get("steps"),
    #             "unit": m.get("units"),
    #             # "max_quantity": move.get("max_quantity"),
    #             # "target_owner": move.get("target_owner"),
    #             # "path": move.get("path", [])
    #         }
    #         actions.append(action)
    elif move_type == "place":
        for m in move:
            actions.append({
                "delegate": move_type,
                "from": "",
                "to": m.get("to"),
                "unit": m.get("unit")
            })
    else:
        action = {
            "delegate": move_type,
            "from": move.get("from"),
            "to": move.get("to"),
            # "steps": move.get("steps"),
            "unit": move.get("units"),
            # "max_quantity": move.get("max_quantity"),
            # "target_owner": move.get("target_owner"),
            # "path": move.get("path", [])
        }
        actions.append(action)
    
    return actions


class OnlineGreedyAgent:
    def __init__(self, state_dim, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay

        self.latest_legal_moves = []
        # self.w = np.zeros(state_dim, dtype=np.float32)

    def get_move(self, line, ctf):
        line = line.strip()
        print("\n")
        print(line)
        
        try:
            m = re.search(r"\[MY_MOVE\] (\w+)", line)
            if m:
                move_type = m.group(1)
                if move_type == "purchase":
                    legal_moves = generate_legal_purchase_moves(ctf, ctf.whoAmI)
                    if legal_moves:
                        # print("node_features shape:", state["node_features"].shape)
                        # print("adjacency shape:", state["adjacency"].shape)
                        # print("global_features shape:", state["global_features"].shape)
                        # time.sleep(15)

                        move = random.choice(legal_moves)
                        response = convert_action_to_json(move, "purchase")
                        
                    else:
                        print("No legal purchase moves available.")
                        response = []
                elif move_type == "combat":
                    legal_moves = generate_legal_combat_moves(ctf, ctf.whoAmI)
                    if legal_moves:
                        moves = random.choice(legal_moves)
                        response = convert_action_to_json(moves, "combat")
                    else:
                        print("No legal combat moves available.")
                        response = []
                elif move_type == "noncombat":
                    legal_moves = generate_legal_noncombat_moves(ctf, ctf.whoAmI)
                    if legal_moves:
                        moves = random.choice(legal_moves)
                        response = convert_action_to_json(moves, "noncombat")
                    else:
                        print("No legal noncombat moves available.")
                        response = []
                elif move_type == "place":
                    legal_moves = generate_legal_place_moves(ctf, ctf.whoAmI)
                    if legal_moves:
                        moves = random.choice(legal_moves)
                        response = convert_action_to_json(moves, "place")
                        response = []
                    else:
                        print("No legal place moves available.")
                        response = []          
                else:
                    print("Unsupported move type:", move_type)
                    response = []
            return response    
        except Exception as e:
            print(e)
            time.sleep(4)
            return []


    def get_state_encoding(self, ctf, delegate):
        '''
        state = {
            node_features - features of a territory - owner, units_i_own, avg_attack_of_stationed_units, avg_defense_of_stationed_units, total_unit_count, is_victory_city, is_in_battle 
            adjacency - matrix
            global_features - delegate_type
        }
        '''
        num_players = len(ctf.G.owners)
        owner_to_idx = {owner: i for i, owner in enumerate(ctf.G.owners.keys())}
        num_nodes = len(ctf.G.nodes)
        
        node_features = []
        
        for terr, data in ctf.G.nodes(data=True):
            owner_vec = np.zeros(num_players, dtype=np.float32)
            if data["owner"] in owner_to_idx:
                owner_vec[owner_to_idx[data["owner"]]] = 1.0

            units = data.get("units", [])
            total_units = float(sum(u["quantity"] for u in units))

            attack_values, defense_values, in_combat_flags, moved_values = [], [], [], []

            for u in units:
                rule = ctf.production_rules.get(u["unit"], {})
                if "attack" in rule:
                    attack_values.append(float(rule["attack"]))
                if "defense" in rule:
                    defense_values.append(float(rule["defense"]))

                props = u.get("properties", {})
                if str(props.get("wasInCombat", "")).lower() == "true":
                    in_combat_flags.append(1.0)
                val = props.get("alreadyMoved", 0)
                try:
                    moved_values.append(float(val))
                except (ValueError, TypeError):
                    moved_values.append(0.0)

            avg_attack = np.mean(attack_values) if attack_values else 0.0
            avg_defense = np.mean(defense_values) if defense_values else 0.0
            frac_in_combat = np.mean(in_combat_flags) if in_combat_flags else 0.0
            avg_moved = np.mean(moved_values) if moved_values else 0.0
            is_victory_city = float(terr in ctf.victory_cities)
            in_battle = float(data.get("properties", {}).get("battle", False))

            numeric_features = np.array([
                total_units, avg_attack, avg_defense,
                frac_in_combat, avg_moved, is_victory_city, in_battle
            ], dtype=np.float32)

            node_vec = np.concatenate([owner_vec, numeric_features])
            node_features.append(node_vec)

        
        node_features = np.array(node_features, dtype=np.float32)

        adjacency = nx.to_numpy_array(ctf.G, dtype=np.float32)

        delegate_types = ["purchase", "combat", "noncombat"]    
        delegate_onehot = np.zeros(len(delegate_types))    
        delegate_onehot[delegate_types.index(delegate)] = 1             
        global_features = np.concatenate([delegate_onehot])

        state = {
            "node_features": node_features,
            "adjacency": adjacency,
            "global_features": global_features
        }
        return state


    def update_legal_moves(self, move_type, player):
        global MOVE_DICT

        if move_type == "purchase":
            legal_moves = generate_legal_purchase_moves(ctf, player)
            self.latest_legal_moves = legal_moves

            # --- Update move dictionary ---
            updated = False
            for move in legal_moves:
                # Represent move as a canonical string key
                key = json.dumps(move.get("purchase"), sort_keys=True)

                if key not in MOVE_DICT:
                    MOVE_DICT[key] = len(MOVE_DICT)
                    updated = True

            # Save dictionary if new moves were added
            if updated:
                with open(MOVE_DICT_PATH, "w") as f:
                    json.dump(MOVE_DICT, f, indent=2)


def parse_purchase_line(ctf, player, line):
    """
    Parse a purchase log line like:
    'ProductionRule:buyArtillery -> 1 ProductionRule:buyInfantry -> 1'
    and return a dict in the same format as generate_legal_purchase_moves().
    """
    # Step 1. Find all "ProductionRule:buyX -> N" patterns
    matches = re.findall(r"ProductionRule:buy(\w+)\s*->\s*(\d+)", line)
    if not matches:
        return None  # no valid matches

    # Step 2. Normalize names and quantities
    purchase_dict = {}
    for unit_name, qty_str in matches:
        unit_name = unit_name.lower()  # optional normalization
        qty = int(qty_str)
        purchase_dict[unit_name] = purchase_dict.get(unit_name, 0) + qty

    # Step 3. Compute total cost using production rules
    total_cost = 0
    for unit_name, qty in purchase_dict.items():
        rule = ctf.production_rules.get(unit_name)
        if rule:
            total_cost += rule.get("cost", 0) * qty
        else:
            print(f"Warning: no cost found for {unit_name}")

    # Step 4. Get available factories
    factories = ctf.get_factories(player)

    return {
        "purchase": purchase_dict,
        "cost": total_cost,
        "place_in": factories
    }


def get_purchase_move_id(move):
    key = json.dumps(move.get("purchase"), sort_keys=True)
    if key not in MOVE_DICT:
        MOVE_DICT[key] = len(MOVE_DICT)
        with open(MOVE_DICT_PATH, "w") as f:
            json.dump(MOVE_DICT, f)
    return MOVE_DICT[key]


def save_delegate_json(state, player, move_type, pu_before_move, pu_after_move, ep, round_num=None, legal_moves=None, chosen_move=None, base_filename="_dataset.jsonl"):
    base_filename = f"{move_type}{ep}{base_filename}"
    legal_ids = [get_purchase_move_id(m) for m in legal_moves]
    chosen_id = get_purchase_move_id(chosen_move)
    entry = {
        "round": round_num,
        "player": player,
        "delegate": move_type,
        "pu_before_move": pu_before_move,
        "pu_after_move": pu_after_move,
        "state": {
            "node_features": state["node_features"].tolist(),
            "adjacency": state["adjacency"].tolist(),
            "global_features": state["global_features"].tolist()
        },
        "legal_moves": legal_ids,
        "chosen_move": chosen_id
        # ideally also isWinner
    }

    with open(base_filename, "a") as f:
        json.dump(entry, f)
        f.write("\n")

    # np.savez_compressed(
    #     f"purchase_data/game1/round_{round_num}_{player}.npz",
    #     round=round_num,
    #     player=player,
    #     delegate=move_type,
    #     pu_before_move=pu_before_move,
    #     pu_after_move=pu_after_move,
    #     node_features=state["node_features"],
    #     adjacency=state["adjacency"],
    #     global_features=state["global_features"],
    #     legal_moves=legal_ids,
    #     chosen_move=chosen_id
    # )


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
                            dataset_path = f"purchase{episode}_dataset.jsonl" # zip this file and delete the text file
                            if os.path.exists(dataset_path):
                                zip_filename = f"purchase{episode}winner{winner}_dataset.zip" 
                                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.write(dataset_path, arcname=os.path.basename(dataset_path))
                                os.remove(dataset_path)
                            else:
                                print("No dataset file found for this episode.")
                            episode += 1
                        elif msg.startswith("[FOR_DB]"):
                            player = parts[2]
                            if parts[1] == "purchase": # or one of delegates
                                pu_before_move = ctf.get_player_resources(player)
                                agent.update_legal_moves(parts[1], parts[2])
                            if parts[1] == "chosen":
                                move_msg = msg.strip().split("::")[1]
                                chosen_move = parse_purchase_line(ctf, player, move_msg)
                                # print(agent.latest_legal_moves)
                                for legal_move in agent.latest_legal_moves:
                                    if chosen_move["purchase"] == legal_move["purchase"]:
                                        # print("Chosen move:", chosen_move)
                                        print("Saving: Round=", r, " for ", player)
                                        pu_after_move = ctf.get_player_resources(player)
                                        save_delegate_json(state=agent.get_state_encoding(ctf, "purchase"), player=player, move_type="purchase", round_num=r, pu_before_move=pu_before_move, pu_after_move=pu_after_move, legal_moves=agent.latest_legal_moves, chosen_move=chosen_move, ep=episode)
                                        break
                            else:
                                # print("Move: ", parts[1])
                                agent.update_legal_moves(parts[1], parts[2])
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






MOVE_DICT_PATH = "move_dict.json"
try:
    with open(MOVE_DICT_PATH, "r") as f:
        MOVE_DICT = json.load(f)
except FileNotFoundError:
    MOVE_DICT = {}



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

