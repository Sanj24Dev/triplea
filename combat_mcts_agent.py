# sim model 2


import math
import random
from helper import convert_action_to_json, convert_combat_to_json
from collections import deque
import itertools
import time
import re
from ctf_graph import Territory, Player, MetricLogger
from itertools import product
import copy

# for non combat??
# _reachability_cache = {}
game_rules = None
territory_production = None
victory_cities = None
adjacency = None
turn_order = None

FACTORY_MAP = {
    "Russians": "RussianBase",
    "Italians": "ItalianBase",
    "Germans": "GermanBase",
    "Chinese": "ChineseBase"
}

class Attack:
    def __init__(self, type, from_territory, quantity):
        self.unit_type = type
        self.from_territory = from_territory
        self.quantity = quantity

    def __repr__(self):
        return f"Move units: {self.quantity}x{self.unit_type} from {self.from_territory}"


class Move:
    def __init__(self, delegate=None, to_terr=None, moves=None, end_phase=False, strength=0):
        self.delegate = delegate
        self.to_terr = to_terr
        self.moves = moves
        self.strength = strength
        self.end_phase = end_phase

    def __repr__(self):
        if self.end_phase:
            return f"{self.delegate} delegate: END PHASE"

        lines = [f"{self.delegate} delegate on {self.to_terr}"]
        for attack in self.moves:
            lines.append(f"\t{attack}")
        lines.append(f"\tstrength={self.strength}")

        return "\n".join(lines)


def generate_legal_purchase_moves(ctf, player):
    if player in ctf.players:
        ctf.players[player].unplaced.clear()

    resources = ctf.get_player_resources(player)
    factories = ctf.get_factories(player)

    if not factories:
        return []  # can't build if no factory

    # Extract unit costs
    units = [(name, data["cost"]) for name, data in game_rules.items() if name not in {"fighter", "bomber", "aaGun"}]

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
                attack_combo.append(Attack(type=group["unit"].unit_type, from_territory=group["from"], quantity=qty))
                unit_list.extend([group["unit"]] * qty)
        
        attack_strength = ctf.calculate_attack_strength(unit_list)
        if attack_strength > defender_strength:
            winning_subsets.append((attack_combo, attack_strength))
        all_moves += 1

    return winning_subsets, all_moves


def generate_legal_noncombat_moves(ctf, player):
    legal_moves = []

    for terr_name, territory in ctf.territories.items():
        if territory.owner != player:
            continue

        for u in territory.units:
            if u.owner != player or u.quantity <= 0:
                continue

            move_range = game_rules.get(u.unit_type, {}).get("move", 1)
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
                        # "steps": steps + 1,
                        "units": u.unit_type
                        # "max_quantity": u.quantity,
                        # "target_owner": neighbor_owner,
                        # "path": path + [neighbor]
                    }
                    legal_moves.append(move)

                    # Continue exploring friendly chain up to move_range
                    if steps + 1 < move_range:
                        queue.append((neighbor, steps + 1, path + [neighbor]))

    return legal_moves



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
            new_player = Player(name, player.PU, self.territories[FACTORY_MAP[name]])
            new_player.latest_loc = player.latest_loc
            new_player.unplaced = player.unplaced.copy()
            self.players[name] = new_player
        
        self.current_player = ctf.whoAmI
        self.round = ctf.round
        self.game_num = ctf.game_num

        self.actions = []              # Generated actions for current territory
        self.actionIndex = 0           # Current position in actions list
        self.excluded = set()          # Territories already processed

        # Territory lists (computed once, reused)
        self.my_territories = [t for t_name, t in self.territories.items() if t.owner == self.current_player]
        self.enemy_territories = [t for t_name, t in self.territories.items() if t.owner != self.current_player]


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
            f"  turn_order={turn_order}\n"
            ")"
        )
    
    def clone(self):        
        cloned = copy.deepcopy(self)
        return cloned

    def is_terminal(self):
        victory_count = {}
        for territory_name in victory_cities:
            territory = self.territories[territory_name]
            owner = territory.owner
            victory_count[owner] = victory_count.get(owner, 0) + 1
        return any(count == len(victory_cities) for count in victory_count.values()) 
    
    def am_i_winner(self):
        for territory_name in victory_cities:
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
                    if unit.unit_type == "factory" and unit.owner == player:
                        factories.append(terr_name)

        if not factories:
            return []  # can't build if no factory

        # Extract unit costs
        units = [(name, data["cost"]) for name, data in game_rules.items() if name not in {"fighter", "bomber", "aaGun"}]

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
        move_range = game_rules.get(unit_type, {}).get("move", 1)
        if move_range <= 0 or unit_type == "factory":
            return False
        
        cache_key = (unit_type, from_territory, to_territory)
        if cache_key in self._reachability_cache:
            return self._reachability_cache[cache_key]
        

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

            for neighbor in adjacency.neighbors(current):
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
                
        
        self._reachability_cache[cache_key] = result
        return result

    def calculate_attack_strength(self, units):
        attacker_strength = 0
        infantry = sum(u["qty"] for u in units if u["unit_type"] == "infantry")
        artillery = sum(u["qty"] for u in units if u["unit_type"] == "artillery")
        supported_inf = min(infantry, artillery)   # 1:1 support
        unsupported_inf = infantry - supported_inf

        for u in units:
            unit_type = u["unit_type"]
            quantity = u["qty"]
            # calculate strength
            stats = game_rules.get(unit_type, {})
            power = stats.get("attack", 1)
            if unit_type == "infantry":
                attacker_strength += supported_inf * (power+1) 
                attacker_strength += unsupported_inf * power
            else:
                attacker_strength += quantity * power
        return attacker_strength
    
    def form_attacks(self, units):
        grouped = {}
        for u in units:
            key = (u["from"], u["unit_type"])
            if key not in grouped:
                grouped[key] = {
                    "from": u["from"],
                    "unit_type": u["unit_type"],
                    "count": 0
                }
            grouped[key]["count"] += 1
        
        # Convert to Attack objects
        attacks = []
        for group in grouped.values():
            attacks.append(
                Attack(
                    type=group["unit_type"],
                    from_territory=group["from"],
                    quantity=group["count"]
                )
            )
        
        return attacks


    def heuristic_combat_legal_moves(self, time_budget):
        player = self.current_player
        legal_moves = []
        self.actions = []
        self.actionIndex = 0
        start = time.time()
        self._reachability_cache = {}

        strengthThreshold = 1.1  # Start at 110% of defender
        maxThreshold = 3.5       # Stop at 350% of defend

        # enemy_territories.sort()

        for enemy_territory in self.enemy_territories:
            enemy_territory_name = enemy_territory.name

            if enemy_territory_name not in self.excluded:
                # the territory isnt considered yet
                # Find all units that can reach this destination
                units_that_can_attack = [
                    {"from": from_terr.name, "unit_type": unit.unit_type, "qty": unit.quantity}
                    for from_terr in self.my_territories
                    for unit in from_terr.units
                    if unit.owner == player
                    if unit.unit_type != "aaGun"
                    if self.check_reachability(unit, from_terr.name, enemy_territory_name)
                ]                
                
                if time.time() - start > time_budget:
                    return legal_moves
                # If no units can reach the territory, skip
                if not units_that_can_attack:
                    self.excluded.add(enemy_territory_name)
                    continue

                # the territory is reachable 
                # Always include option to skip attack on this territory
                legal_moves.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[]))

                defender_strength = 0
                units_at_target = [u for u in enemy_territory.units if u.owner != player]
                # assuming all the units at target belong to the terr owner = all previous battles resolved
                for unit in units_at_target:
                    unit_type = unit.unit_type
                    stats = game_rules.get(unit_type, {})
                    power = stats.get("defense", 1)
                    defender_strength += unit.quantity * power


                sets = []
                unitsUpToStrength = []
                for unit in units_that_can_attack:
                    unitsUpToStrength.append(unit)
                    
                    currentStrength = self.calculate_attack_strength(unitsUpToStrength)
                     # Save when crossing threshold
                    if (currentStrength > strengthThreshold * defender_strength and currentStrength < (maxThreshold * defender_strength) + 4):  
                        attacks = self.form_attacks(unitsUpToStrength)                     
                        sets.append((attacks, currentStrength))
                        strengthThreshold += 0.1  # Increment by 10%
                    
                    # Stop if exceeded max
                    if currentStrength >= (maxThreshold * defender_strength) + 4:
                        break

                # Always include final full force
                if unitsUpToStrength:
                    attacks = self.form_attacks(unitsUpToStrength) 
                    sets.append((attacks, currentStrength))

                sets.reverse()
                for unitSet, strength in sets:
                    self.actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=unitSet, strength=strength))

                self.excluded.add(enemy_territory_name)
                return 

        legal_moves.append(Move(delegate="combat", end_phase=True, strength=0))

               
    def heuristic_non_combat_legal_moves(self, time_budget):
        player = self.current_player
        legal_moves = []
        start = time.time()
        self._reachability_cache = {}

        my_territories = [t for t in self.territories.values() if t.owner == player]
    
        for to_territory in my_territories:
            to_territory_name = to_territory.name
            # Always include option to skip attack on this territory
            legal_moves.append(Move(delegate="noncombat", to_terr=to_territory_name, moves=[]))

            units_that_can_attack  = [
                {"from": from_terr.name, "unit": unit, "qty": unit.quantity}
                for from_terr in my_territories
                if from_terr.name != to_territory_name
                for unit in from_terr.units
                if unit.owner == player
                if self.check_reachability(unit, from_terr.name, to_territory_name)
            ]
            if time.time() - start > time_budget:
                return legal_moves
            
            # If no units can reach the territory, skip
            if not units_that_can_attack:
                continue
            # print(f"Units that can attack {units_that_can_attack}")
            
            # Pick one random move from reachable set
            choice = random.choice(units_that_can_attack)
            move = Attack(type=choice["unit"].unit_type, from_territory=choice["from"], quantity=choice["qty"])
            legal_moves.append(Move("noncombat", to_terr=to_territory_name, moves=[move]))

            if time.time() - start > time_budget:
                return legal_moves
            
            
        del self._reachability_cache
        return legal_moves

    def apply_purchase_move(self, move):
        player = self.current_player
        if not move or not move.moves:
            return 
        
        purchase_dict = move.moves
        total = 0
        for unit_type, qty in purchase_dict.items():
            stats = game_rules.get(unit_type, {})
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
            stats = game_rules.get(unit_type, {})
            power = stats.get("defense", 1)
            defender_strength += unit.quantity * power

        attacker_strength = move.strength
        
        for attack in attacks:
            frm = attack.from_territory
            unit_type = attack.unit_type
            quantity = attack.quantity
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
            frm = attack.from_territory
            unit_type = attack.unit_type
            quantity = attack.quantity
            from_territory = self.territories[frm]
            from_territory.remove_unit(unit_type, player, quantity)
            to_territory.add_unit(unit_type, player, quantity)

    def update_income(self, player):
        pus = player.PU
        for territory_name, territory in self.territories.items():
            if territory.owner == player.name:
                pus += territory_production[territory_name]
        player.PU = pus

    def getNextAction(self):
        if self.actionIndex < len(self.actions):
            action = self.actions[self.actionIndex]
            self.actionIndex += 1
            return action
        else:
            return None


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
    def __init__(self, model_name, reduction_file, efficiency_file, quality_file, production_rules, terr_production, vic_cities, adj, order, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.latest_legal_moves = []
        
        # MCTS parameters
        self.time_budget = 1.0  # seconds per move
        self.max_depth = 10  # Maximum playout depth
        self.exploration_constant = 1.414  # UCB1 exploration parameter

        self.model_name = model_name
        # file paths to store metrics
        self.reduction_metric = MetricLogger(
            reduction_file,
            header=["game", "round", "total_moves", "pruned_moves"]
        )
        self.efficiency_metric = MetricLogger(
            efficiency_file,
            header=["game", "round", "num_iterations", "root_node_visits", "best_node_visits", "best_node_value", "avg_depth", "explored", "total_actions"]
        )

        self.combat_quality = MetricLogger(
            quality_file,
            header=["game", "round", "pu_before", "pu_after", "territories_before", "territories_after"]
        )

        global game_rules, territory_production, victory_cities, adjacency, turn_order
        game_rules = production_rules
        territory_production = terr_production
        victory_cities = vic_cities
        adjacency = adj
        turn_order = order


    def count_exhaustive_moves(self, units_that_can_attack):
        all_moves = 0
        quantity_ranges = []
        for group in units_that_can_attack:
            # Range from 0 to max_quantity (inclusive)
            unit = group["unit"]
            quantity_ranges.append(range(0, unit.quantity + 1))

        for quantities in product(*quantity_ranges):
            all_moves += 1

        return all_moves


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
                    
                    # legal_moves = self.generate_combat_moves_territory_based(ctf, ctf.whoAmI)
                    # save in a file, then save the graph image with the same number - run for 10 rounds
                    # img_file = f"smart_root_dumb_tree/combat_moves/graph_{ctf.game_num}_{round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    # with open(f"smart_root_dumb_tree/combat_moves/MOVES_{ctf.game_num}_{round}.txt", "w") as f:
                    #     for sub in legal_moves:
                    #         f.write("Attack: \n\t")
                    #         f.write(sub.__repr__())
                    #         f.write("\n")
        
                    # select a random attack and try playout
                    current_state = MCTSGameState(ctf)
                    # action = self.mcts_search(current_state, legal_moves)
                    profile_name = f"{self.model_name}/profiles/mcts_{ctf.game_num}_"
                    if ctf.round < 10:
                        profile_name += "0"
                    profile_name += round + ".prof"
                    action = self.profile_mcts(current_state, profile_name)
                    response = convert_combat_to_json(action)
                    # print("Sending:", response)

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
            nextAction = node.state.getNextAction()
            print(f"Action selected {nextAction}\n")
            if nextAction is not None:
                return self.expand(node, nextAction)
            else:
                # All actions tried, select best child using UCB1
                bestChild = node.best_child(self.exploration_constant)
                if bestChild is None:
                    return node
                node = bestChild
        
        return node
    
    def expand(self, parent, action):
        new_state = parent.state.clone()
        
        try:
            new_state.apply_combat_move(action)
            player = new_state.players[new_state.current_player]
            new_state.update_income(player)
            new_state.heuristic_combat_legal_moves(self.time_budget)
            
        except Exception as e:
            print(f"Error in expansion: {e}")
            return parent
        
        # Create child node
        child = MCTSNode(new_state, parent=parent, action=action)
        parent.children.append(child)
        
        return child

    def simulate(self, state, time_done):
        current_state = state.clone()
        depth = 0

        try:
            idx = turn_order.index(current_state.current_player)
            
            # Complete current round for remaining players
            if idx < len(turn_order) - 1:
                for i in range(idx + 1, len(turn_order)):
                    # print(f"\nSimulation for {turn_order[i]}\n")
                    current_state.current_player = turn_order[i]
                    
                    # Random purchase
                    # purchase_moves = current_state.purchase_legal_moves()
                    # if purchase_moves:
                    #     current_state.apply_purchase_move(random.choice(purchase_moves))
                    
                    # Random combat
                    combat_moves = current_state.heuristic_combat_legal_moves(self.time_budget)
                    if combat_moves:
                        current_state.apply_combat_move(random.choice(combat_moves))
                    
                    # Random non-combat
                    noncombat_moves = current_state.heuristic_non_combat_legal_moves(self.time_budget)
                    if noncombat_moves:
                        current_state.apply_noncombat_move(random.choice(noncombat_moves))
                    
                    # Place units
                    player = current_state.players[current_state.current_player]
                    # player.place_units()
                    current_state.update_income(player)
            
            current_state.round += 1
            depth += 1
            
            # Simulate future rounds
            time_left = self.time_budget - time_done
            start = time.time()
            while depth < self.max_depth and not current_state.is_terminal() and time.time() - start < time_left:
                for player_name in turn_order:
                    current_state.current_player = player_name
                    
                    # purchase_moves = current_state.purchase_legal_moves()
                    # if purchase_moves:
                    #     current_state.apply_purchase_move(random.choice(purchase_moves))
                    combat_moves = current_state.heuristic_combat_legal_moves(self.time_budget)
                    if combat_moves:
                        current_state.apply_combat_move(random.choice(combat_moves))
                    noncombat_moves = current_state.heuristic_non_combat_legal_moves(self.time_budget)
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
        return self.evaluate_state(current_state, depth), depth
    
    def backpropagate(self, node, reward):
        while node is not None:
            node.visits += 1
            node.value += reward
            
            # Flip reward for opponent's nodes (minimax)
            reward = -reward
            
            node = node.parent


    def mcts_search(self, initial_state):
        print("Generating moves")
        initial_state.heuristic_combat_legal_moves(self.time_budget)
        print(f"Moves generated {initial_state.actions}\n")
        root = MCTSNode(initial_state)
                
        start_time = time.time()
        iterations = 0
        # avg_depth = 0
        
        # while time.time() - start_time < self.time_budget:
            # 1. Selection and expansion
        selected_node = self.select(root)
        print(f"Moves generated after expansion {selected_node.state.actions}\n")
            
        #     # 3. Simulation (Playout)
        #     reward, depth = self.simulate(node.state, time.time() - start_time)
        #     avg_depth += depth
        #     # 4. Backpropagation
        #     self.backpropagate(node, reward)
            
        #     iterations += 1
        
        # print(f"MCTS ran {iterations} iterations in {self.time_budget}s")
        # print(f"Root node visits: {root.visits}")

        # if not root.children:
        #     print("Warning: No children expanded, returning random action")
        #     selected_action = random.choice(legal_actions)
        # else:
        #     best_child = max(root.children, key=lambda c: c.visits)
        #     selected_action = best_child.action
        #     print(f"Best action visits: {best_child.visits}, value: {best_child.value/best_child.visits:.3f}")
        #     print(f"Selected action : {selected_action}")
        #     best_child_value = best_child.value/best_child.visits
        #     avg_depth /= iterations
        #     actions_explored = len(root.children)
        #     total_actions = len(legal_actions)

        #     self.efficiency_metric.log(root.state.game_num, root.state.round, iterations, root.visits, best_child.visits, best_child_value, avg_depth, actions_explored, total_actions)
        
        # pu_before = initial_state.players[initial_state.current_player].PU
        # my_territories_before = sum(1 for t in initial_state.territories.values() if t.owner == initial_state.current_player)
        # initial_state.apply_combat_move(selected_action)
        # initial_state.update_income(initial_state.players[initial_state.current_player])
        # pu_after = initial_state.players[initial_state.current_player].PU
        # my_territories_after = sum(1 for t in initial_state.territories.values() if t.owner == initial_state.current_player)
        # self.combat_quality.log(initial_state.game_num, initial_state.round, pu_before, pu_after, my_territories_before, my_territories_after)

        # # how do i selected actions on multiple territories
            
        selected_action = []
        return selected_action
    
    def profile_mcts(self, initial_state, file):
        import cProfile
        with cProfile.Profile() as pr:
            result = self.mcts_search(initial_state)
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
            
        


    