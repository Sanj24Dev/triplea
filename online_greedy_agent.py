import random
import db_creation_helper as db
from helper import convert_action_to_json
from collections import deque
import itertools
import numpy as np
import networkx as nx


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

                    # ✅ If enemy or neutral, record as valid target
                    if neighbor_owner != player:
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

                    # ✅ Continue traversal even through own territories
                    if neighbor_owner == player or (steps + 1 < move_range):
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


    def update_legal_moves(self, move_type, player, ctf):
        if move_type == "purchase":
            legal_moves = generate_legal_purchase_moves(ctf, player)
            self.latest_legal_moves = legal_moves
            db.update_puchase_dict(legal_moves)

        elif move_type == "combat":
            legal_moves = generate_legal_combat_moves(ctf, player)
            self.latest_legal_moves = legal_moves
            db.update_combat_dict(legal_moves)
        
        elif move_type == "noncombat":
            legal_moves = generate_legal_noncombat_moves(ctf, player)
            self.latest_legal_moves = legal_moves
            db.update_noncombat_dict(legal_moves)


