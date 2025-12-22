import math
import random
from helper import convert_action_to_json, convert_combat_to_json
from collections import deque
import itertools
# import numpy as np
# import networkx as nx
import time
import re
from ctf_graph import Territory, Player
from itertools import product
from collections import Counter
import csv
import os
import reachability_cpp

# for non combat??
_reachability_cache = {}

class MetricLogger:
    def __init__(self, filename, header=None):
        self.filename = filename
        self.header = header

        # Ensure directory exists
        folder = os.path.dirname(filename)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        # Create file and write header
        if header and not os.path.exists(filename):
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)


    def log(self, *values):
        """Append one row of metrics."""
        with open(self.filename, "a", newline="") as f:
            csv.writer(f).writerow(values)




class Move:
    def __init__(self, delegate=None, to_terr=None, moves=None, end_phase=False, strength=0):
        self.delegate = delegate
        # self.from_terr = from_terr
        self.to_terr = to_terr
        self.moves = moves
        self.strength = strength
        self.end_phase = end_phase

    def __repr__(self):
        # different for different delegates == check when you add other delegates
        if self.end_phase:
            return f"{self.delegate} delegate: END PHASE"

        lines = [f"{self.delegate} delegate on {self.to_terr}"]
        
        # Imitate the original loop
        for attack in self.moves:
            unit = attack["unit"].unit_type
            frm = attack["from"]
            qty = attack["quantity"]

            lines.append(f"\tMove units:{qty}x{unit} from {frm}")

        # Add strength at the end
        lines.append(f"\tstrength={self.strength}")

        return "\n".join(lines)



# inital implmentation
def generate_legal_purchase_moves(ctf, player):
    if player in ctf.players:
        ctf.players[player].unplaced.clear()
    # print("Before purchase: ", ctf.G.owners[ctf.whoAmI]["unplaced"])
    rules = ctf.production_rules
    resources = ctf.get_player_resources(player)
    factories = ctf.get_factories(player)

    if not factories:
        return []  # can't build if no factory

    # Extract unit costs
    units = [(name, data["cost"]) for name, data in rules.items() if name not in {"fighter", "bomber", "aaGun"}]

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
    

def find_winning_subsets(ctf, units_that_can_attack, defender_strength):
    # Sort strongest first (optional, improves pruning & readability)
    # expanded_units.sort(
    #     key=lambda u: ctf.production_rules.get(u, {}).get("attack", 1),
    #     reverse=True
    # )
    all_moves = 0
    quantity_ranges = []
    for group in units_that_can_attack:
        # Range from 0 to max_quantity (inclusive)
        unit = group["unit"]
        quantity_ranges.append(range(0, unit.quantity + 1))


    winning_subsets = []
    for quantities in product(*quantity_ranges):
        # Skip empty combination
        if sum(quantities) == 0:
            continue
        
        # Build attack combination and unit list
        attack_combo = []
        unit_list = []
        
        for i, qty in enumerate(quantities):
            if qty > 0:
                group = units_that_can_attack[i]
                attack_combo.append({
                    "unit": group["unit"],
                    "from": group["from"],
                    "quantity": qty
                })
                # Expand for strength calculation
                unit_list.extend([group["unit"]] * qty)
        
        # print(unit_list)
        # Calculate attack strength
        attack_strength = ctf.calculate_attack_strength(unit_list)
        # print("In round ", ctf.round, " : ", attack_combo, "=", attack_strength, " attacks def=", defender_strength)
        # Check if this combination wins
        if attack_strength > defender_strength:
            # save only the info need for mcts
            winning_subsets.append((attack_combo, attack_strength))
        all_moves += 1


    return winning_subsets, all_moves

def generate_legal_combat_moves(ctf, player):
    legal_moves = []

    for terr_name, territory in ctf.territories.items():
        if territory.owner != player:
            continue

        for u in territory.units:
            if u.owner != player or u.quantity <= 0:
                continue

            move_range = ctf.production_rules.get(u.unit_type, {}).get("move", 1)
            if move_range <= 0 or u.unit_type in ("factory", "aaGun"):
                continue

            queue = deque([(terr_name, 0, [terr_name])])
            visited = set([terr_name])

            while queue:
                current, steps, path = queue.popleft()
                if steps >= move_range:
                    continue

                for neighbor in ctf.G.neighbors(current):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)

                    neighbor_territory = ctf.territories[neighbor]
                    neighbor_owner = neighbor_territory.owner

                    # If enemy or neutral, record as valid target
                    if neighbor_owner != player:
                        legal_moves.append({
                            "delegate": "combat",
                            "from": terr_name,
                            "to": neighbor,
                            "steps": steps + 1,
                            "units": u.unit_type,
                            "max_quantity": u.quantity,
                            "target_owner": neighbor_owner,
                            "path": path + [neighbor]
                        })

                    # Continue traversal even through own territories
                    if neighbor_owner == player or (steps + 1 < move_range):
                        queue.append((neighbor, steps + 1, path + [neighbor]))

    return legal_moves

# inital implmentation
def generate_legal_noncombat_moves(ctf, player):
    legal_moves = []

    for terr_name, territory in ctf.territories.items():
        if territory.owner != player:
            continue

        for u in territory.units:
            if u.owner != player or u.quantity <= 0:
                continue

            move_range = ctf.production_rules.get(u.unit_type, {}).get("move", 1)
            if move_range <= 0 or u.unit_type == "factory":
                continue

            # BFS: explore up to move_range steps through friendly territories
            queue = deque([(terr_name, 0, [terr_name])])
            visited = set([terr_name])

            while queue:
                current, steps, path = queue.popleft()
                if steps >= move_range:
                    continue

                for neighbor in ctf.G.neighbors(current):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)

                    neighbor_territory = ctf.territories[neighbor]
                    neighbor_owner = neighbor_territory.owner

                    # For non-combat, must stay within friendly territories
                    if neighbor_owner != player:
                        continue  # can't move into or through enemy/neutral

                    # Valid non-combat move (repositioning)
                    move = {
                        "delegate": "nonCombat",
                        "from": terr_name,
                        "to": neighbor,
                        "steps": steps + 1,
                        "units": u.unit_type,
                        "max_quantity": u.quantity,
                        "target_owner": neighbor_owner,
                        "path": path + [neighbor]
                    }
                    legal_moves.append(move)

                    # Continue exploring friendly chain up to move_range
                    if steps + 1 < move_range:
                        queue.append((neighbor, steps + 1, path + [neighbor]))

    return legal_moves


def to_cpp_unit(py_unit):
    u = reachability_cpp.Unit()
    u.owner = py_unit.owner
    u.type = py_unit.unit_type   # must match "armour" / etc
    return u


class MCTSGameState:
    """Compressed game state for MCTS"""
    def __init__(self, ctf):
        # Deep copy territories and their units
        self.territories = {}
        for name, territory in ctf.territories.items():
            # Create new Territory instance with copied data
            new_territory = Territory(name, territory.owner)
            new_territory.properties = territory.properties.copy()
            
            # Copy units
            for unit in territory.units:
                new_territory.add_unit(
                    unit.unit_type,
                    unit.owner,
                    unit.quantity,
                    unit.properties.copy()
                )
            
            self.territories[name] = new_territory
        
        # Shallow copy players
        self.players = {}
        for name, player in ctf.players.items():
            if name == "Russians":
                factory = self.territories["RussianBase"]
            elif name == "Italians":
                factory = self.territories["ItalianBase"]
            elif name == "Germans":
                factory = self.territories["GermanBase"]
            elif name == "Chinese":
                factory = self.territories["ChineseBase"]
            new_player = Player(name, player.PU, factory)
            new_player.latest_loc = player.latest_loc
            new_player.unplaced = player.unplaced.copy()
            self.players[name] = new_player
        
        # References (shared across all states - immutable)
        self.production_rules = ctf.production_rules
        self.territory_production = ctf.territory_production
        self.adjacency = ctf.G  # NetworkX graph structure
        self.victory_cities = ctf.victory_cities
        self.current_player = ctf.whoAmI
        self.round = ctf.round
        self.game_num = ctf.game_num
        self.turn_order = ["Russians", "Italians", "Germans", "Chinese"]

        cpp_adjacency = {
            name: list(self.adjacency.neighbors(name))
            for name in self.territories
        }
        reachability_cpp.set_adjacency(cpp_adjacency)

    def __repr__(self):
        # Summaries
        terr_summary = []
        for name, terr in self.territories.items():
            unit_str = ", ".join(
                f"{u.quantity}x{u.unit_type}({u.owner})" for u in terr.units
            )
            terr_summary.append(f"{name}: {terr.owner} [{unit_str}]")

        player_summary = ", ".join(
            f"{pname}(PU={p.PU}, unplaced={p.unplaced})"
            for pname, p in self.players.items()
        )

        return (
            "MCTSGameState(\n"
            f"  round={self.round}, current_player='{self.current_player}',\n"
            f"  territories={{\n      " + "\n      ".join(terr_summary) + "\n  }},\n"
            f"  players={{ {player_summary} }},\n"
            f"  turn_order={self.turn_order}\n"
            ")"
        )
    
    def clone_shallow(self):
        cloned = MCTSGameState.__new__(MCTSGameState)
        
        # Deep copy territories and their units
        cloned.territories = {}
        for name, territory in self.territories.items():
            new_territory = Territory(name, territory.owner)
            new_territory.properties = territory.properties.copy()
            
            # Copy units
            for unit in territory.units:
                new_territory.add_unit(
                    unit.unit_type,
                    unit.owner,
                    unit.quantity,
                    unit.properties.copy()
                )
            
            cloned.territories[name] = new_territory
        
        # Deep copy players
        cloned.players = {}
        for name, player in self.players.items():
            if name == "Russians":
                factory = cloned.territories["RussianBase"]
            elif name == "Italians":
                factory = cloned.territories["ItalianBase"]
            elif name == "Germans":
                factory = cloned.territories["GermanBase"]
            elif name == "Chinese":
                factory = cloned.territories["ChineseBase"]
            new_player = Player(name, player.PU, factory)
            new_player.latest_loc = player.latest_loc
            new_player.unplaced = player.unplaced.copy()
            cloned.players[name] = new_player
        

        # Shallow copy immutable references
        cloned.production_rules = self.production_rules
        cloned.territory_production = self.territory_production
        cloned.adjacency = self.adjacency
        cloned.victory_cities = self.victory_cities
        cloned.current_player = self.current_player
        cloned.round = self.round
        cloned.game_num = self.game_num
        cloned.turn_order = ["Russians", "Italians", "Germans", "Chinese"]
        
        return cloned

    def is_terminal(self):
        victory_count = {}
        for territory_name in self.victory_cities:
            territory = self.territories[territory_name]
            owner = territory.owner
            victory_count[owner] = victory_count.get(owner, 0) + 1
        return any(count == len(self.victory_cities) for count in victory_count.values()) 
    
    def am_i_winner(self):
        for territory_name in self.victory_cities:
            territory = self.territories[territory_name]
            owner = territory.owner
            if owner != self.current_player:
                return False
        return True
    

    # functions for simulation
    def purchase_legal_moves(self):
        player = self.current_player
        resources = self.players[player].PU

        factories = []
        for terr_name, territory in self.territories.items():
            if territory.owner == player:
                for unit in territory.units:
                    if unit.owner == player and unit.unit_type == "factory":
                        factories.append(terr_name)

        if not factories:
            return []  # can't build if no factory

        # Extract unit costs
        units = [(name, data["cost"]) for name, data in self.production_rules.items()]

        legal_moves = [{}]
        min_cost = min(cost for _, cost in units)
        max_units = resources // min_cost

        for r in range(1, max_units + 1):
            for combo in itertools.combinations_with_replacement(units, r):
                total_cost = sum(cost for _, cost in combo)
                if total_cost <= resources:
                    purchase_dict = {}
                    for unit, cost in combo:
                        purchase_dict[unit] = purchase_dict.get(unit, 0) + 1
                    legal_moves.append(Move(delegate="purchase",moves=purchase_dict))

        return legal_moves

    def check_reachability(self, unit, from_territory, to_territory):
        unit_type = unit.unit_type
        move_range = self.production_rules.get(unit_type, {}).get("move", 1)
        if move_range <= 0 or unit_type == "factory":
            return False
        cache_key = (unit_type, from_territory, to_territory)

        if cache_key in _reachability_cache:
            return _reachability_cache[cache_key]
        

        queue = deque([(from_territory, 0)])
        visited = set([from_territory])
        result = False
        my_territories = []
        for my_territory_name, my_territory in self.territories.items():
            if my_territory.owner == self.current_player:
                my_territories.append(my_territory.name)

        while queue:
            current, steps = queue.popleft()
            if steps >= move_range:
                continue

            for neighbor in self.adjacency.neighbors(current):
                if neighbor in visited:
                    continue
                # Can't move through enemy-occupied territory (unless blitzing and empty)
                terr_owner = self.territories[neighbor].owner
                if unit_type == "armour":
                    # CASE 1: neighbor is friendly → always allowed
                    if terr_owner == unit.owner:
                        pass
                    # CASE 2: neighbor is neutral → allowed (just like friendly)
                    elif terr_owner == "Neutral":
                        pass  # allowed
                    # CASE 3: neighbor is ENEMY
                    elif terr_owner != unit.owner:

                        # If NEIGHBOR == target → always allowed as final combat
                        if neighbor == to_territory:
                            pass  # can always attack enemy
                        else:
                            continue
                else:
                    if neighbor != to_territory:  # Not our target
                        if neighbor not in my_territories:  # Enemy territory
                            continue
                visited.add(neighbor)
                
                if neighbor == to_territory:
                    result = True
                    break
                queue.append((neighbor, steps + 1))
                
        
        _reachability_cache[cache_key] = result
        return result

    def _build_reachability_context(self, player):
        territories_cpp = {}
        my_territories = set()

        for name, terr in self.territories.items():
            t = reachability_cpp.Territory()
            t.owner = terr.owner
            territories_cpp[name] = t

            if terr.owner == player:
                my_territories.add(name)

        return territories_cpp, my_territories


    # initial representation
    def combat_legal_moves(self):
        player = self.current_player
        legal_moves = []

        territories_cpp, my_territories = self._build_reachability_context(player)
        # Build unit move ranges once
        unit_move_ranges = {
            unit_type: rules.get("move", 1)
            for unit_type, rules in self.production_rules.items()
        }
        # Collect all player's units with their locations
        all_units = []
        unit_lookup = {}  # Map to find original Python unit objects
        
        # print(f"\n\nFor player {player}")
        for territory_name, territory in self.territories.items():
            if territory.owner == player:
                for unit in territory.units:
                    if unit.owner == player and unit.unit_type != "factory":
                        cpp_unit = to_cpp_unit(unit)
                        info = reachability_cpp.UnitInfo()
                        info.from_territory = territory_name
                        info.unit = cpp_unit
                        info.quantity = unit.quantity
                        all_units.append(info)
                        
                        # Store original Python unit for later lookup
                        key = (territory_name, unit.unit_type, unit.owner)
                        unit_lookup[key] = unit

        for enemy_territory_name, enemy_territory in self.territories.items():
            if enemy_territory.owner == player:
                continue  

            units_that_can_attack = []


            # using cpp
            reachable_cpp = reachability_cpp.get_reachable_units(
                enemy_territory_name,
                player,
                territories_cpp,
                my_territories,
                all_units,
                unit_move_ranges
            )
            if not reachable_cpp:
                continue
            for unit_info in reachable_cpp:
                # Find original Python unit object if needed
                key = (unit_info.from_territory, unit_info.unit.type, unit_info.unit.owner)
                units_that_can_attack.append({
                    "from": unit_info.from_territory,
                    "unit": unit_lookup[key],  # or find original Python unit
                    "qty": unit_info.quantity
                })
            
            # # using pure python
            # for my_territory_name, my_territory in self.territories.items():
            #     if my_territory.owner != player:
            #         continue
                
            #     # Check each unit in my territory
            #     for unit in my_territory.units:
            #         if unit.owner != player:
            #             continue
            #         if unit.unit_type == "aaGun":
            #             continue

            #         if self.check_reachability(unit, my_territory_name, enemy_territory_name):
            #             units_that_can_attack.append({
            #                 "from": my_territory_name,
            #                 "unit": unit,
            #                 "qty": unit.quantity
            #             })

                        
            
            # If no units can reach the territory, skip
            if not units_that_can_attack:
                continue
   
            # Find legal attack subsets
            legal_subsets = []
            quantity_ranges = []
            for group in units_that_can_attack:
                # Range from 0 to max_quantity (inclusive)
                unit = group["unit"]
                quantity_ranges.append(range(0, unit.quantity + 1))
            
            for quantities in itertools.product(*quantity_ranges):
                # Skip empty combination
                if sum(quantities) == 0:
                    continue
                
                # Build attack combination and unit list
                attack_combo = []
                unit_list = []
                
                for i, qty in enumerate(quantities):
                    if qty > 0:
                        group = units_that_can_attack[i]
                        attack_combo.append({
                            "unit": group["unit"],
                            "from": group["from"],
                            "quantity": qty
                        })
                        # Expand for strength calculation
                        unit_list.extend([group["unit"]] * qty)

                legal_subsets.append(attack_combo)

            for subset in legal_subsets:
                legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=subset))
            
            # Always include option to skip attack on this territory
            legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[]))
        
        legal_moves.append(Move(delegate="combat", end_phase=True))
        
        return legal_moves

    def non_combat_legal_moves(self):
        player = self.current_player
        legal_moves = []
    
        for to_territory_name, to_territory in self.territories.items():
            if to_territory.owner != player:
                continue  

            units_that_can_attack = []
            for my_territory_name, my_territory in self.territories.items():
                if my_territory.owner != player:
                    continue
                
                # Check each unit in my territory
                for unit in my_territory.units:
                    if unit.owner != player:
                        continue

                    if self.check_reachability(unit, my_territory_name, to_territory_name):
                        units_that_can_attack.append({
                            "from": my_territory_name,
                            "unit": unit,
                            "qty": unit.quantity
                        })
            
            # If no units can reach the territory, skip
            if not units_that_can_attack:
                legal_moves.append(Move(delegate="noncombat", to_terr=to_territory_name, moves=[]))
                continue
            # print(f"Units that can attack {units_that_can_attack}")
            
            
            # Find legal attack subsets
            legal_subsets = []
            quantity_ranges = []
            for group in units_that_can_attack:
                # Range from 0 to max_quantity (inclusive)
                unit = group["unit"]
                quantity_ranges.append(range(0, unit.quantity + 1))
            
            for quantities in itertools.product(*quantity_ranges):
                # Skip empty combination
                if sum(quantities) == 0:
                    continue
                
                # Build attack combination and unit list
                attack_combo = []
                unit_list = []
                
                for i, qty in enumerate(quantities):
                    if qty > 0:
                        group = units_that_can_attack[i]
                        attack_combo.append({
                            "unit": group["unit"],
                            "from": group["from"],
                            "quantity": qty
                        })
                        # Expand for strength calculation
                        unit_list.extend([group["unit"]] * qty)

                legal_subsets.append(attack_combo)
            
            
            # Generate action for each winning subset
            for subset in legal_subsets:
                legal_moves.append(Move(delegate="noncombat", to_terr=to_territory_name, moves=subset))
            
            # Always include option to skip attack on this territory
            legal_moves.append(Move(delegate="noncombat", to_terr=to_territory_name, moves=[]))
        
        return legal_moves

    def heuristic_non_combat_legal_moves(self):
        player = self.current_player
        legal_moves = []

        # Iterate only over player-owned territories
        for to_name, to_terr in self.territories.items():
            if to_terr.owner != player:
                continue

            # Find all units that can reach this destination
            reachable_units = [
                {"from": from_name, "unit": unit, "qty": unit.quantity}
                for from_name, from_terr in self.territories.items()
                if from_terr.owner == player
                for unit in from_terr.units
                if unit.owner == player
                if self.check_reachability(unit, from_name, to_name)
            ]

            # If none can reach → only the skip move
            if not reachable_units:
                legal_moves.append(Move("noncombat", to_terr=to_name, moves=[]))
                continue

            # Pick one random move from reachable set
            choice = random.choice(reachable_units)
            move = {
                "unit": choice["unit"],
                "from": choice["from"],
                "quantity": choice["qty"]
            }

            legal_moves.append(Move("noncombat", to_terr=to_name, moves=[move]))

            # Also add skip option
            legal_moves.append(Move("noncombat", to_terr=to_name, moves=[]))

        return legal_moves

    def apply_purchase_move(self, move):
        player = self.current_player
        if not move or not move.moves:
            return 
        
        purchase_dict = move.moves
        total = 0
        for unit_type, qty in purchase_dict.items():
            stats = self.production_rules.get(unit_type, {})
            cost = stats.get("cost", 1)
            total += qty * cost
        
        self.players[player].PU -= total
        for unit_type, quantity in purchase_dict.items():
            self.players[player].unplaced[unit_type] = self.players[player].unplaced.get(unit_type, 0) + quantity

    def apply_combat_move(self, move):
        if move.end_phase:
            # Don't change state, just signal to stop attacking
            # The game state stays the same
            return
        player = self.current_player
        if not move or not move.moves:
            return

        to = move.to_terr
        to_territory = self.territories[to]
        attacks = move.moves
        if not attacks:  
            return
        
        defender_strength = 0
        units_at_target = to_territory.units
        # assuming all the units at target belong to the terr owner = all previous battles resolved
        for unit in units_at_target:
            unit_type = unit.unit_type
            stats = self.production_rules.get(unit_type, {})
            power = stats.get("defense", 1)
            defender_strength += unit.quantity * power

        attacker_strength = 0
        infantry = sum(u.quantity for u in units_at_target if u.unit_type == "infantry")
        artillery = sum(u.quantity for u in units_at_target if u.unit_type == "artillery")
        supported_inf = min(infantry, artillery)   # 1:1 support
        unsupported_inf = infantry - supported_inf
        for attack in attacks:
            unit = attack.get("unit")
            unit_type = unit.unit_type
            quantity = attack.get("quantity")
            # calculate strength
            stats = self.production_rules.get(unit_type, {})
            power = stats.get("attack", 1)
            if unit.unit_type == infantry:
                attacker_strength += supported_inf * (power+1) 
                attacker_strength += unsupported_inf * power
            else:
                attacker_strength += quantity * power
        
        for attack in attacks:
            frm = attack.get("from")
            unit = attack.get("unit")
            unit_type = unit.unit_type
            quantity = attack.get("quantity")
            from_territory = self.territories[frm]
            from_territory.remove_unit(unit_type, player, quantity)
            if attacker_strength > defender_strength:
                to_territory.add_unit(unit_type, player, quantity)
                for u in units_at_target:
                    to_territory.remove_unit(u.unit_type, to_territory.owner, u.quantity)

        if attacker_strength > defender_strength:
            self.territories[to_territory.name].owner = player

    def apply_noncombat_move(self, move):
        player = self.current_player
        if not move or not move.moves:
            return
        
        to = move.to_terr
        to_territory = self.territories[to]
        attacks = move.moves
        
        if not attacks:  
            return

        for attack in attacks:
            frm = attack.get("from")
            unit = attack.get("unit")
            unit_type = unit.unit_type
            quantity = attack.get("quantity")
            from_territory = self.territories[frm]
            from_territory.remove_unit(unit_type, player, quantity)
            to_territory.add_unit(unit_type, player, quantity)

    def update_income(self, player):
        pus = 0
        for territory_name, territory in self.territories.items():
            if territory.owner == player.name:
                pus += self.territory_production[territory_name]
        player.PU = pus

    # need to chnage - wrong logic
    def _calculate_player_strength(self, player):
        strength = 0
        for terr_name in self.territories:
            terr = self.territories[terr_name] 
            if terr.owner == player:
                for u in terr.units:
                    if u.owner == player:
                        unit_type = u.unit_type
                        qty = u.quantity
                        stats = self.production_rules.get(unit_type, {})
                        power = stats.get("attack", 1) + stats.get("defense", 1)         
                        strength += qty * power
        total = 0
        for terr_name in self.territories:
            terr = self.territories[terr_name] 
            if terr.owner == player:
                # get the infantry attack strength
                infantry_qty = 0
                artillery_qty = 0
                for u in terr.units:
                    if u.unit_type == "infantry":
                        infantry_qty += u.quantity
                    elif u.unit_type == "artillery":
                        artillery_qty += u.quantity
                infantry_supported = min(infantry_qty, artillery_qty)

                for unit in terr.units:
                    if unit.owner == player:   # just for sanity
                        unit_type = unit.unit_type
                        qty = unit.quantity
                        stats = self.production_rules.get(unit_type, {})

                        attack = stats.get("attack", 0)
                        if type in ("aaGun", "factory"):
                            attack_strength = 0
                        elif type == "infantry":
                            supported = min(qty, infantry_supported)
                            unsupported = qty - supported
                            attack_strength = supported * (attack + 1) + unsupported * attack
                        else:
                            attack_strength = qty * attack
                        
                        defense = stats.get("defense", 0)
                        # AA guns and factories contribute zero combat defense
                        if unit_type in ("aaGun", "factory"):
                            defense = 0
                        defense_strength = qty * defense

                        # mobility weights
                        if unit_type == "armour":
                            mobility = 1
                        elif unit_type in ("fighter", "bomber"):
                            mobility = 2
                        else:
                            mobility = 0


                        total += attack_strength + defense_strength + mobility + 1
        return strength



class MCTSNode:
    def __init__(self, state, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.untried_actions = None  # Lazy initialization
        self.visits = 0
        self.value = 0.0

    def is_fully_expanded(self):
        return self.untried_actions is not None and len(self.untried_actions) == 0
    
    def is_terminal(self):
        return self.state.is_terminal()
    
    def best_child(self, c_param=1.414):
        choices_weights = [
            (child.value / child.visits) + c_param * math.sqrt(2 * math.log(self.visits) / child.visits)
            for child in self.children
        ]
        return self.children[choices_weights.index(max(choices_weights))]


class MCTS:
    def __init__(self, reduction_file, efficiency_file, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.latest_legal_moves = []
        
        # MCTS parameters
        self.time_budget = 1.0  # seconds per move
        self.max_depth = 2  # Maximum playout depth
        self.exploration_constant = 1.414  # UCB1 exploration parameter

        # file paths to store metrics
        self.reduction_metric = MetricLogger(
            reduction_file,
            header=["game", "round", "total_moves", "pruned_moves"]
        )
        self.efficiency_metric = MetricLogger(
            efficiency_file,
            header=["game", "round", "num_iterations", "root_node_visits", "best_node_visits", "best_node_value"]
        )


    def generate_combat_moves_territory_based(self, ctf, player):
        legal_moves = []
        total_moves = 0

        for enemy_territory_name in ctf.get_enemy_territories_by_priority(player):
            # Find all units that can reach this territory
            enemy_territory = ctf.territories[enemy_territory_name]
            units_that_can_attack = []
            
            for my_territory_name in ctf.get_my_territories():
                my_territory = ctf.territories[my_territory_name]
                # in my territory, if the unit can reach this enemy territory then add its instance
                for unit in my_territory.units:
                    if unit.unit_type == "aaGun":
                        continue
                    if ctf.can_reach(unit, my_territory_name, enemy_territory_name):
                        units_that_can_attack.append({
                            "from": my_territory_name,
                            "unit": unit,
                            "qty": unit.quantity
                        })
               
            if not units_that_can_attack:
                continue

            enemy_territory_units = []
            for unit in enemy_territory.units:
                if unit.owner != player:
                    enemy_territory_units.append(unit)
            
            defender_strength = ctf.calculate_defense_strength(enemy_territory_units)            
            if defender_strength == 0:
                # go with 1 unit
                total_undefended_combinations = 1
                for info in units_that_can_attack:
                    # Each unit can send 0, 1, 2, ..., qty units
                    total_undefended_combinations *= (info["qty"] + 1)
                
                # Subtract 1 for the empty set (sending 0 of everything)
                total_undefended_combinations -= 1

                all_moves = total_undefended_combinations


                unit_to_attack = self.select_unit_to_attack_for_undeffended(units_that_can_attack)
                attack_strength = ctf.calculate_attack_strength([unit_to_attack["unit"]]) 
                move = {
                    "unit": unit_to_attack["unit"],
                    "from": unit_to_attack["from"],
                    "quantity": 1
                }
                legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[move], strength=attack_strength))
            else:
                # find all winning subsets
                winning_subsets, all_moves = find_winning_subsets( 
                    ctf,
                    units_that_can_attack, 
                    defender_strength
                )
                # generate action for each winning subset
                for subset in winning_subsets:
                    legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=subset[0], strength=subset[1]))
            total_moves += all_moves

            
            if ctf.round > 5:
                legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[], strength=0))
            total_moves += 1

        pruned_moves = len(legal_moves)
        # print("Number of moves before pruning: ", total_moves)
        # print("Number of moves after pruning: ", pruned_moves)
        self.reduction_metric.log(ctf.game_num, ctf.round, total_moves, pruned_moves)
        legal_moves.sort(key=lambda m: m.strength, reverse=True)
        return legal_moves

    def select_unit_to_attack_for_undeffended(self,units_that_can_attack):
        # check with weakest/cheapest unit
        return random.choice(units_that_can_attack)

    def get_move(self, line, ctf, round):
        line = line.strip()
        # print("\n")
        # print(line)
        print("\nGame ", ctf.game_num, " Round ", round, " " ,line)
        try:
            m = re.search(r"\[MY_MOVE\] (\w+)", line)
            if m:
                move_type = m.group(1)
                if move_type == "purchase":
                    ctf.round = int(round)
                    legal_moves = generate_legal_purchase_moves(ctf, ctf.whoAmI)

                    if legal_moves:
                        move = random.choice(legal_moves)
                        response = convert_action_to_json(move, "purchase")
                    else:
                        # print("No legal purchase moves available.")
                        response = []
                    # response = []
                elif move_type == "combat":
                    # print("\n")
                    
                    legal_moves = self.generate_combat_moves_territory_based(ctf, ctf.whoAmI)
                    # save in a file, then save the graph image with the same number - run for 10 rounds
                    img_file = f"smart_root_dumb_tree/combat_moves/graph_{ctf.game_num}_{round}.png"
                    ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    with open(f"smart_root_dumb_tree/combat_moves/MOVES_{ctf.game_num}_{round}.txt", "w") as f:
                        for sub in legal_moves:
                            f.write("Attack: \n\t")
                            f.write(sub.__repr__())
                            f.write("\n")
        
                    # select a random attack and try playout
                    current_state = MCTSGameState(ctf)
                    # action = self.mcts_search(current_state, legal_moves)
                    profile_name = f"smart_root_dumb_tree/profiles/mcts_{ctf.game_num}_"
                    if ctf.round < 10:
                        profile_name += "0"
                    profile_name += round + ".prof"
                    action = self.profile_mcts(current_state, legal_moves, profile_name)
                    response = convert_combat_to_json(action)
                    # print("Sending:", response)


                    # legal_moves = generate_legal_combat_moves(ctf, ctf.whoAmI)
                    # if legal_moves:
                    #     moves = random.choice(legal_moves)
                    #     response = convert_action_to_json(moves, "combat")
                    #     print("Sending:", response)
                    # else:
                    #     print("No legal combat moves available.")
                    #     response = []


                elif move_type == "noncombat":
                    # img_file = f"after_combat_{round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    # print(f"Graph exported as {img_file}")
                    legal_moves = generate_legal_noncombat_moves(ctf, ctf.whoAmI)
                    if legal_moves:
                        moves = random.choice(legal_moves)
                        response = convert_action_to_json(moves, "noncombat")
                    else:
                        # print("No legal noncombat moves available.")
                        response = []  
                else:
                    # print("Unsupported move type:", move_type)
                    response = []

            return response    
        except Exception as e:
            print(e)
            time.sleep(4)
            return []


    def select(self, node):
        while not node.is_terminal():
            if node.untried_actions is None:
                node.untried_actions = node.state.combat_legal_moves()
                return node
            
            if len(node.untried_actions) > 0: # has untried actions
                return node
            
            if len(node.children) == 0: # is a dead end
                return node
            
            # All actions tried, select best child using UCB1
            node = node.best_child(self.exploration_constant)
        
        return node
    
    def expand(self, node):
        if not node.untried_actions:    # cant expand without untried actions
            return node
    
        action = node.untried_actions.pop(0)
        new_state = node.state.clone_shallow()
        
        try:
            new_state.apply_combat_move(action)
            
            # Complete rest of current player's turn with random non-combat
            noncombat_moves = new_state.heuristic_non_combat_legal_moves()
            if noncombat_moves:
                noncombat = random.choice(noncombat_moves)
                new_state.apply_noncombat_move(noncombat)
            
            # Place units
            player = new_state.players[new_state.current_player]
            # player.place_units()
            new_state.update_income(player)
            
        except Exception as e:
            print(f"Error in expansion: {e}")
            return node
        
        # Create child node
        child = MCTSNode(new_state, parent=node, action=action)
        node.children.append(child)
        
        return child

    def simulate(self, state):
        current_state = state.clone_shallow()
        depth = 0
        # print("SIM START | current_player =", state.current_player)
        # print("TURN ORDER:", current_state.turn_order)
        
        try:
            idx = current_state.turn_order.index(current_state.current_player)
            
            # Complete current round for remaining players
            if idx < len(current_state.turn_order) - 1:
                for i in range(idx + 1, len(current_state.turn_order)):
                    # print(f"\nSimulation for {current_state.turn_order[i]}\n")
                    current_state.current_player = current_state.turn_order[i]
                    
                    # Random purchase
                    # purchase_moves = current_state.purchase_legal_moves()
                    # if purchase_moves:
                    #     current_state.apply_purchase_move(random.choice(purchase_moves))
                    
                    # Random combat
                    combat_moves = current_state.combat_legal_moves()
                    if combat_moves:
                        current_state.apply_combat_move(random.choice(combat_moves))
                    
                    # Random non-combat
                    noncombat_moves = current_state.heuristic_non_combat_legal_moves()
                    if noncombat_moves:
                        current_state.apply_noncombat_move(random.choice(noncombat_moves))
                    
                    # Place units
                    player = current_state.players[current_state.current_player]
                    # player.place_units()
                    current_state.update_income(player)
            
            current_state.round += 1
            depth += 1
            
            # Simulate future rounds
            while depth < self.max_depth and not current_state.is_terminal():
                for player_name in current_state.turn_order:
                    current_state.current_player = player_name
                    
                    # purchase_moves = current_state.purchase_legal_moves()
                    # if purchase_moves:
                    #     current_state.apply_purchase_move(random.choice(purchase_moves))
                    combat_moves = current_state.combat_legal_moves()
                    if combat_moves:
                        current_state.apply_combat_move(random.choice(combat_moves))
                    noncombat_moves = current_state.heuristic_non_combat_legal_moves()
                    if noncombat_moves:
                        current_state.apply_noncombat_move(random.choice(noncombat_moves))
                    player = current_state.players[current_state.current_player]
                    # player.place_units()
                    current_state.update_income(player)
                    
                    if current_state.is_terminal():
                        break
                
                current_state.round += 1
                depth += 1
            
        except Exception as e:
            print(f"Error in simulation: {e}")
            return -0.5
        
        # Evaluate final state
        return self.evaluate_state(current_state, depth)
    
    def backpropagate(self, node, reward):
        while node is not None:
            node.visits += 1
            node.value += reward
            
            # Flip reward for opponent's nodes (minimax)
            reward = -reward
            
            node = node.parent


    def mcts_search(self, initial_state, legal_actions):
        root = MCTSNode(initial_state)
        root.untried_actions = legal_actions.copy()
                
        start_time = time.time()
        iterations = 0
        
        while time.time() - start_time < self.time_budget:
            # 1. Selection
            node = self.select(root)
            
            # 2. Expansion
            if not node.is_terminal() and node.untried_actions:
                node = self.expand(node)
            
            # 3. Simulation (Playout)
            reward = self.simulate(node.state)
            
            # 4. Backpropagation
            self.backpropagate(node, reward)
            
            iterations += 1
        
        print(f"MCTS ran {iterations} iterations in {self.time_budget}s")
        print(f"Root node visits: {root.visits}")

        # print(f"\n{'='*60}")
        # print(f"MCTS STATISTICS")
        # print(f"{'='*60}")
        # print(f"Total iterations: {iterations} in {self.time_budget}s")
        # print(f"Root node visits: {root.visits}")
        # print(f"\nACTION SPACE COVERAGE:")
        # print(f"  Total legal actions: {len(legal_actions)}")
        # print(f"  Actions tried: {len(root.children)}")
        # print(f"  Actions never tried: {len(root.untried_actions)}")
        
        # if root.untried_actions:
        #     print(f"\n  ⚠️  WARNING: {len(root.untried_actions)} actions were NEVER explored!")
        #     print(f"  Untried actions:")
        #     for action in root.untried_actions[:3]:  # Show first 3
        #         print(f"    - {action}")
        #     if len(root.untried_actions) > 3:
        #         print(f"    ... and {len(root.untried_actions) - 3} more")
        
        # print(f"\nCHILDREN VISIT DISTRIBUTION:")
        # if root.children:
        #     sorted_children = sorted(root.children, key=lambda c: c.visits, reverse=True)
        #     for i, child in enumerate(sorted_children[:5], 1):  # Top 5
        #         avg_value = child.value / child.visits if child.visits > 0 else 0
        #         print(f"  {i}. Visits: {child.visits:3d} ({child.visits/root.visits*100:5.1f}%), "
        #             f"Value: {avg_value:+.3f} - {child.action}")
            
        #     if len(sorted_children) > 5:
        #         print(f"  ... and {len(sorted_children) - 5} more children")
            
        #     # Check for imbalanced exploration
        #     max_visits = sorted_children[0].visits
        #     min_visits = sorted_children[-1].visits
        #     if max_visits > min_visits * 10:
        #         print(f"\n  ⚠️  WARNING: Exploration very imbalanced!")
        #         print(f"     Most visited child: {max_visits} visits")
        #         print(f"     Least visited child: {min_visits} visits")
        
        # # print(f"\nTREE DEPTH:")
        # # max_depth = self._calculate_max_depth(root)
        # # print(f"  Maximum depth reached: {max_depth}")
        
        # print(f"{'='*60}\n")
        
        # Return best action based on visit count (most robust)
        if not root.children:
            print("Warning: No children expanded, returning random action")
            return random.choice(legal_actions)
        
        best_child = max(root.children, key=lambda c: c.visits)
        print(f"Best action visits: {best_child.visits}, value: {best_child.value/best_child.visits:.3f}")
        print(f"Selected action : {best_child.action}")
        best_child_value = best_child.value/best_child.visits
        self.efficiency_metric.log(root.state.game_num, root.state.round, iterations, root.visits, best_child.visits, best_child_value)
        # how do i selected actions on multiple territories
            
        return best_child.action
    
    def profile_mcts(self, initial_state, legal_actions, file):
        import cProfile
        with cProfile.Profile() as pr:
            result = self.mcts_search(initial_state, legal_actions)
        pr.dump_stats(file)
        return result

    def evaluate_state(self, state, depth):
        if state.is_terminal():
            if state.am_i_winner():
                return 0.6 + 0.4 * (10 - depth) / 10
            else:
                return -0.6 - 0.4 * (10 - depth) / 10
        else:
            # Count units, don't calculate strength
            my_units = sum(
                u.quantity
                for terr in state.territories.values()
                if terr.owner == state.current_player
                for u in terr.units
                if u.owner == state.current_player
            )
           
            
            total_enemy_units = sum(
                u.quantity
                for terr in state.territories.values()
                if terr.owner != state.current_player
                for u in terr.units
                if u.owner != state.current_player
            )
            
            total_size = my_units + total_enemy_units
            
            if total_size == 0:
                return 0.0
            
            # Paper's formula: divide by (total_size * 2)
            return (my_units - total_enemy_units) / (total_size * 2)
            
            # Clamp to [-0.5, 0.5] for non-terminal states
            # return max(-0.5, min(0.5, normalized_score))
        

    # def evaluate_state(self, state, depth):
    #     if state.is_terminal():
    #         if state.am_i_winner():
    #             return 0.6 + 0.4 * (10 - depth) / 10
    #         else:
    #             return -0.6 - 0.4 * (10 - depth) / 10
        
    #     # For shallow searches, emphasize immediate tactical gains
    #     my_player = state.current_player
        
    #     # 1. Victory city control (most important)
    #     my_victory_cities = sum(1 for vc in state.victory_cities 
    #                         if state.territories[vc].owner == my_player)
    #     total_vcs = len(state.victory_cities)
    #     vc_score = (my_victory_cities / total_vcs) - 0.25  # Range: -0.25 to +0.75
        
    #     # 2. Territory control
    #     my_territories = sum(1 for t in state.territories.values() 
    #                         if t.owner == my_player)
    #     total_territories = len(state.territories)
    #     territory_score = (my_territories / total_territories) - 0.25
        
    #     # 3. Economic advantage (PUs)
    #     my_pu = state.players[my_player].PU
    #     opponent_pus = [state.players[p].PU for p in state.turn_order 
    #                     if p != my_player]
    #     avg_opponent_pu = sum(opponent_pus) / len(opponent_pus) if opponent_pus else 0
    #     pu_advantage = (my_pu - avg_opponent_pu) / (my_pu + avg_opponent_pu + 1)
        
    #     # 4. Military strength (your current calculation)
    #     my_strength = state._calculate_player_strength(my_player)
    #     opponent_strengths = [state._calculate_player_strength(p) 
    #                         for p in state.turn_order if p != my_player]
    #     avg_opponent_strength = sum(opponent_strengths) / len(opponent_strengths) if opponent_strengths else 0
    #     total_strength = my_strength + sum(opponent_strengths)
    #     strength_score = (my_strength - avg_opponent_strength) / (total_strength + 1)
        
    #     # Weighted combination (adjust weights based on game phase)
    #     score = (
    #         0.40 * vc_score +           # Victory cities are critical
    #         0.20 * territory_score +     # Map control matters
    #         0.20 * pu_advantage +        # Economic engine
    #         0.20 * strength_score        # Military power
    #     )
        
    #     return max(-0.5, min(0.5, score))
        
    
    