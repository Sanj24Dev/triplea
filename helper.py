import xml.etree.ElementTree as ET
import re
import json
import time
import os
import ast


# def convert_combat_to_json(move):
#     actions = []
#     # attacking one territory
#     for attack in move.moves:
#         qty = attack.get("quantity")
#         action = {
#             "delegate": "combat",
#             "from": attack.get("from"),
#             "to": move.to_terr,
#             "unit": attack.get("unit").unit_type,
#             "count": qty,
#         }
#         actions.append(action)
#     return actions


def convert_combat_to_json(move):
    actions = []
    # attacking one territory
    for attack in move.moves:
        qty = attack.quantity
        action = {
            "delegate": "combat",
            "from": attack.from_territory,
            "to": move.to_terr,
            "unit": attack.unit_type,
            "count": qty,
        }
        actions.append(action)
    return actions


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
            "unit": move.get("units"),
        }
        actions.append(action)
    
    return actions


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

    # --- Extract Territory Production Values (income per territory) ---
    territory_production = {}
    for attach in root.findall(".//attachmentList/attachment[@type='territory']"):
        territory_name = attach.attrib["attachTo"]
        for opt in attach.findall("option"):
            if opt.attrib.get("name") == "production":
                territory_production[territory_name] = int(opt.attrib["value"])
                break
    
    # Set default production value of 0 for territories without explicit production
    for territory in territories:
        if territory not in territory_production:
            territory_production[territory] = 0

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
        "territory_production": territory_production,  # Added here
        "starting_ownership": starting_ownership,
        "starting_units": starting_units,
        "initial_resources": initial_resources,
        "victory_cities": victory_cities
    }

    # Save to JSON file
    with open(output_path, "w") as f:
        json.dump(parsed_data, f, indent=2)

    print(f"Data successfully extracted and saved to {output_path}")



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

def parse_combat_line(ctf, player, line):
    try:
        # Sometimes Java .toString() uses single quotes, which aren't valid JSON
        # Use ast.literal_eval safely instead of eval
        move_data = ast.literal_eval(line.strip())

        if isinstance(move_data, list):
            parsed_moves = []
            for move in move_data:
                if not isinstance(move, dict):
                    continue

                units = move.get("units").split(",")
                for u in units:
                    parsed_moves.append({
                        'from': move.get('from'),
                        'to': move.get('to'),
                        'steps': int(move.get('steps', 0)),
                        'units': u.strip(),
                        'path': move.get('path', [])
                    })

            return parsed_moves

        else:
            print("Warning: Combat move message is not a list:", move_data)
            return []

    except Exception as e:
        print(f"Error parsing combat move message for {player}: {e}")
        print("Raw move_msg:", line)
        return []
    
