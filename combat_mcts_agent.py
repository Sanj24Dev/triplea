# multi front attack

import math
import random
from helper import convert_purchase_to_json, convert_multi_front_combat_to_json, convert_multi_front_noncombat_to_json
from collections import deque, defaultdict
import itertools
import time
import re
from ctf_graph import Territory, Player, MetricLogger, FACTORY_MAP, Unit
from itertools import product
import copy
import os
import subprocess

game_rules = None
territory_production = None
victory_cities = None
adjacency = None
turn_order = None

class Attack:
    def __init__(self, unit, from_territory, quantity):
        self.unit = unit
        self.from_territory = from_territory
        self.quantity = quantity

    def __repr__(self):
        return f"Move units: {self.quantity}x{self.unit.unit_type} from {self.from_territory}"


class Move:
    def __init__(self, delegate=None, to_terr=None, moves=None, end_phase=False, strength=0):
        self.delegate = delegate
        self.to_terr = to_terr
        self.moves = moves
        self.strength = strength
        self.end_phase = end_phase

    def __repr__(self):
        if self.end_phase:
            return f"\n{self.delegate} delegate: END PHASE"

        lines = [f"\n{self.delegate} delegate on {self.to_terr}"]
        for attack in self.moves:
            lines.append(f"\t{attack}")
        lines.append(f"\tstrength={self.strength}")

        return "\n".join(lines)


def _safe(s: str, maxlen=60):
    s = s.replace('"', "'").replace("\n", " ")
    return s[:maxlen] + ("…" if len(s) > maxlen else "")

def attack_summary(move):
    """
    Returns string like: '2x inf, 1x arm'
    """
    if not getattr(move, "moves", None):
        return ""
    counts = defaultdict(int)
    for atk in move.moves:
        counts[atk.unit.unit_type] += atk.quantity
    return ", ".join(f"{qty}x {ut}" for ut, qty in counts.items())

def save_mcts_tree_png(root, out_prefix, max_nodes=500):
    """
    Saves:
      - out_prefix + ".dot"
      - out_prefix + ".png" (if graphviz 'dot' is available)
    """
    # BFS traversal
    q = deque([root])
    node_id = {id(root): 0}
    nodes = [root]
    edges = []

    while q and len(nodes) < max_nodes:
        n = q.popleft()
        for ch in n.children:
            if id(ch) not in node_id:
                node_id[id(ch)] = len(nodes)
                nodes.append(ch)
                q.append(ch)
            edges.append((node_id[id(n)], node_id[id(ch)], ch.action))

    dot_path = out_prefix + ".dot"
    png_path = out_prefix + ".png"

    with open(dot_path, "w") as f:
        f.write("digraph MCTS {\n")
        f.write('  rankdir=TB;\n')
        f.write('  node [shape=box, fontsize=10];\n')

        for n in nodes:
            nid = node_id[id(n)]
            avg = (n.value / n.visits) if n.visits else 0.0
            label = f"#{nid}\\nvis={n.visits}\\navg={avg:.3f}"
            f.write(f'  n{nid} [label="{label}"];\n')

        for a, b, act in edges:
            if act is None:
                el = ""
            else:
                if getattr(act, "end_phase", False):
                    el = "END"
                else:
                    summary = attack_summary(act)
                    el = f"{act.to_terr} | {summary}"
                el = _safe(el, 60)

            f.write(f'  n{a} -> n{b} [label="{el}"];\n')

        f.write("}\n")

    # Try render to PNG
    try:
        subprocess.run(["dot", "-Tpng", dot_path, "-o", png_path], check=True)
        return dot_path, png_path
    except Exception:
        return dot_path, None

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
    

def generate_legal_noncombat_moves(ctf, player):
    """
    Greedy noncombat:
      0) Evacuate home factory to make room for placement (keep small garrison if threatened)
      1) Fill empty frontier
      2) Reinforce frontier up to quota
      3) Reinforce staging (borders multiple frontiers)
      4) Reinforce factory-adjacent / victory-city ring
    Fallback: if target not reachable, move units toward frontier by reducing dist_to_frontier.
    """

    territories = copy.deepcopy(ctf.territories)
    move_seq = []

    # ---------- basics ----------
    my_territories = [t for t in territories.values() if t.owner == player]

    # frontier = my territory adjacent to non-owned (excluding factories as "enemy targets")
    my_frontier = set()
    for terr in my_territories:
        for n in ctf.G.neighbors(terr.name):
            if territories[n].owner != player and n not in FACTORY_MAP.values():
                my_frontier.add(terr.name)
                break

    home_factory = FACTORY_MAP[player]

    def count_defense_units(terr):
        return sum(u.quantity for u in terr.units if u.unit_type != "factory")

    def has_enemy_neighbor(name: str) -> bool:
        for n in ctf.G.neighbors(name):
            if territories[n].owner != player and n not in FACTORY_MAP.values():
                return True
        return False

    # staging score: how many frontier neighbors this tile borders
    staging_score = {}
    for terr in my_territories:
        staging_score[terr.name] = sum(1 for nb in ctf.G.neighbors(terr.name) if nb in my_frontier)

    # factory-adjacent score: how many victory cities adjacent (your code uses victory_cities as "factories/vc")
    factory_adj_score = {}
    for terr in my_territories:
        factory_adj_score[terr.name] = sum(1 for nb in ctf.G.neighbors(terr.name) if nb in victory_cities)

    # ---------- distance-to-frontier (multi-source BFS) ----------
    dist_to_frontier = {name: float("inf") for name in territories.keys()}
    q = deque()
    for f in my_frontier:
        dist_to_frontier[f] = 0
        q.append(f)

    while q:
        cur = q.popleft()
        for nb in ctf.G.neighbors(cur):
            if dist_to_frontier[nb] > dist_to_frontier[cur] + 1:
                dist_to_frontier[nb] = dist_to_frontier[cur] + 1
                q.append(nb)

    # ---------- target priority ----------
    def territory_priority(territory):
        name = territory.name
        score = 0

        # frontier first
        if name in my_frontier:
            score += 1000

            # empty frontier gets a big bump
            if count_defense_units(territories[name]) == 0:
                score += 500

        # staging next
        score += staging_score.get(name, 0) * 200

        # factory/victory-city ring next
        score += factory_adj_score.get(name, 0) * 100

        return score

    targets = list(my_territories)
    targets.sort(key=territory_priority, reverse=True)


    def best_step_toward_frontier(unit, from_name: str):
        """
        Pick a reachable MY-OWNED destination that reduces dist_to_frontier.
        Higher score = better step.
        """
        best = None
        best_score = -10**9

        from_d = dist_to_frontier.get(from_name, float("inf"))

        for dest in targets:
            dest_name = dest.name
            if dest_name == from_name:
                continue
            if not ctf.can_reach(unit, from_name, dest_name):
                continue

            to_d = dist_to_frontier.get(dest_name, float("inf"))
            improvement = from_d - to_d  # want positive

            # prefer real progress; ignore non-improving unless nothing else exists
            score = improvement * 100
            if dest_name in my_frontier:
                score += 50
            score += staging_score.get(dest_name, 0) * 10
            score += factory_adj_score.get(dest_name, 0) * 5

            if score > best_score:
                best_score = score
                best = dest_name
        return best, best_score

    

    def quota(territory):
        name = territory.name
        qv = 1
        if name in my_frontier:
            qv = 5
        # staging / factory-adj tiles get medium quota (but frontier still dominates)
        if staging_score.get(name, 0) > 0 or factory_adj_score.get(name, 0) > 0:
            qv = max(qv, 3)
        return qv

    # ---------- donors ----------
    # Don't drain frontier tiles, except allow draining home_factory (evacuation) specially below.
    donor_territories = []
    for t in my_territories:
        if count_defense_units(t) <= 0:
            continue
        if t.name in my_frontier and t.name != home_factory:
            continue
        donor_territories.append(t)

    # ---------- PASS 0: evacuate home factory before placement ----------
    # Keep a small garrison only if threatened.
    keep_min = 2 if has_enemy_neighbor(home_factory) else 0
    factory_terr = territories[home_factory]

    movable_from_factory = []
    for u in factory_terr.units:
        move_range = game_rules.get(u.unit_type, {}).get("move", 1)
        if u.owner == player and u.unit_type != "factory" and move_range > 0 and u.quantity > 0:
            movable_from_factory.append(u)

    excess = max(0, count_defense_units(factory_terr) - keep_min)
    sent = 0

    for unit in movable_from_factory:
        while unit.quantity > 0 and sent < excess:
            # try best high-priority targets first
            dest = None
            # for t in targets:
            #     if t.name == home_factory:
            #         continue
            #     if ctf.can_reach(unit, home_factory, t.name):
            #         dest = t.name
            #         break

            # fallback: step toward frontier
            # if dest is None:
            dest, score = best_step_toward_frontier(unit, home_factory)
            if dest is None or score <= 0:
                break

            move_seq.append({
                "delegate": "nonCombat",
                "from": home_factory,
                "to": dest,
                "units": unit.unit_type
            })
            unit.quantity -= 1  # safe: operates on deepcopy
            sent += 1

    # ---------- PASS 1: fill targets to quota (with step-to-frontier fallback) ----------

    for terr in targets:
        terr_name = terr.name

        # if already at/above quota, skip
        if count_defense_units(territories[terr_name]) >= quota(terr):
            continue

        # keep pushing units until target reaches quota or donors run out
        while count_defense_units(territories[terr_name]) < quota(terr):
            moved_one = False

            for donor in donor_territories:
                if count_defense_units(donor) <= 0:
                    continue

                # optional: don't drain donor to 0 (keeps map from hollowing out)
                # you can tune this; leaving it minimal:
                if donor.name != home_factory and count_defense_units(donor) <= 0:
                    continue

                # pick one unit from donor
                picked = None
                for u in donor.units:
                    move_range = game_rules.get(u.unit_type, {}).get("move", 1)
                    if u.owner != player or u.quantity <= 0:
                        continue
                    if u.unit_type == "factory" or move_range <= 0:
                        continue
                    picked = u
                    break

                if picked is None:
                    continue

                # try direct move to target
                dest = None
                if ctf.can_reach(picked, donor.name, terr_name):
                    dest = terr_name
                else:
                    # fallback: step toward frontier (prefer improving moves)
                    step, score = best_step_toward_frontier(picked, donor.name)
                    if step is not None and score > 0:
                        dest = step

                if dest is None:
                    continue

                move_seq.append({
                    "delegate": "nonCombat",
                    "from": donor.name,
                    "to": dest,
                    "units": picked.unit_type
                })

                # update deepcopy counts
                picked.quantity -= 1
                moved_one = True
                break  # re-check quota after each move

            if not moved_one:
                break  # no donors can contribute further
                
    return move_seq


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
        self.set_terr_lists()
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
    
    def am_i_winner(self, whoAmI):
        for territory_name in victory_cities:
            territory = self.territories[territory_name]
            owner = territory.owner
            if owner != whoAmI:
                return False
        return True
    

    def set_terr_lists(self):
        self.my_territories = [t for t_name, t in self.territories.items() if t.owner == self.current_player]
        self.enemy_territories = [t for t_name, t in self.territories.items() if t.owner != self.current_player]
        def territory_priority(territory):
            terr_name = territory.name 
            priority_score = 0
            
            # Victory city = highest priority, victory city are those with a factory, in this map
            if terr_name in victory_cities:
                priority_score += 1000

            next_to_factory = sum(
                1 for neighbor in adjacency.neighbors(terr_name)
                if neighbor in victory_cities
            )
            priority_score += next_to_factory * 500
            
            # Production value
            priority_score += territory_production[terr_name] * 10
                        
            # Number of bordering friendly territories (easier to attack/hold)
            surrounded_by_me = sum(
                1 for neighbor in adjacency.neighbors(terr_name)
                if self.territories[neighbor].owner == self.current_player
            )
            priority_score += surrounded_by_me * 5

            # distance to the victory cities? closer => better to attack

            enemy_neighbors = sum(1 for n in adjacency.neighbors(terr_name) 
                         if self.territories[n].owner == territory.owner)
            priority_score -= enemy_neighbors * 3

            unit_count = sum(u.quantity for u in territory.units if u.unit_type != "factory")
            # more the units, less priority (more costly to attack)
            priority_score += unit_count * 2

            return priority_score
        
        self.enemy_territories.sort(key=territory_priority, reverse=True)


    # functions for simulation
    def purchase_legal_moves(self):
        player = self.current_player
        resources = self.players[player].PU

        has_factory = False
        for terr_name, territory in self.territories.items():
            if territory.owner == player:
                for unit in territory.units:
                    if unit.unit_type == "factory" and unit.owner == player:
                        has_factory = True
                        break

        if has_factory == False:
            return []
        # Extract unit costs
        units = [(name, data["cost"]) for name, data in game_rules.items() if name not in {"fighter", "bomber", "aaGun"}]

        legal_moves = []
        min_cost = min(cost for _, cost in units)
        max_units = resources // min_cost

        # for the max_cost we can consider, we generate combinations of units with repetition
        # generate Moves with Attacks where to_terr is factory, from_terr is None, and attack has unit and quantity, and strength=cost

        for r in range(1, max_units + 1):
            for combo in itertools.combinations_with_replacement(units, r):
                total_cost = sum(cost for _, cost in combo)
                if total_cost <= resources:
                    attacks = []
                    for unit, cost in combo:
                        unit_to_add = Unit(unit, player, 1)  # quantity=1 since we create separate attack for each unit even if same type
                        attacks.append(Attack(unit=unit_to_add, from_territory=None, quantity=1))
                    
                    legal_moves.append(Move(delegate="purchase", moves=attacks, strength=total_cost))

        return legal_moves

    def check_reachability(self, unit, from_territory, to_territory):
        unit_type = unit.unit_type
        move_range = game_rules.get(unit_type, {}).get("move", 1)
        if move_range <= 0 or unit_type == "factory":
            return False
        
        # cache_key = (unit_type, from_territory, to_territory)
        # if cache_key in self._reachability_cache:
        #     return self._reachability_cache[cache_key]
        

        queue = deque([(from_territory, 0)])
        visited = set([from_territory])
        result = False

        while queue:
            current, steps = queue.popleft()
            if steps >= move_range:
                continue

            for neighbor in adjacency.neighbors(current):
                if neighbor in visited:
                    continue

                terr_owner = self.territories[neighbor].owner
                if neighbor == to_territory:
                    result = True
                    break
                if neighbor != to_territory:  # Not our target
                    if self.territories[neighbor].owner != self.current_player:
                        continue  # Can't pass through enemy territory
                visited.add(neighbor)
                
                if steps + 1 < move_range:
                    queue.append((neighbor, steps + 1))
            
        # self._reachability_cache[cache_key] = result
        return result

    def calculate_attack_strength(self, units):
        attacker_strength = 0
        infantry = sum(u["qty"] for u in units if u["unit"].unit_type == "infantry")
        artillery = sum(u["qty"] for u in units if u["unit"].unit_type == "artillery")
        supported_inf = min(infantry, artillery)   # 1:1 support
        unsupported_inf = infantry - supported_inf

        for u in units:
            unit_type = u["unit"].unit_type
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
            key = (u["from"], u["unit"].unit_type)
            if key not in grouped:
                grouped[key] = {
                    "from": u["from"],
                    "unit": u["unit"],
                    "count": 0
                }
            grouped[key]["count"] += u["qty"]
        
        # Convert to Attack objects
        attacks = []
        for group in grouped.values():
            attacks.append(
                Attack(
                    unit=group["unit"],
                    from_territory=group["from"],
                    quantity=group["count"]
                )
            )
        
        return attacks


    def heuristic_combat_legal_moves(self, time_budget):
        player = self.current_player
        self.actions = []
        self.actionIndex = 0
        start = time.time()
        self._reachability_cache = {}

        for enemy_territory in self.enemy_territories:
            enemy_territory_name = enemy_territory.name
            strengthThreshold = 1.1  # Start at 110% of defender
            maxThreshold = 3.5       # Stop at 350% of defend

            if enemy_territory_name not in self.excluded:
                # the territory isnt considered yet
                # Find all units that can reach this destination
                units_that_can_attack = [
                    {"from": from_terr.name, "unit": unit, "qty": unit.quantity}
                    for from_terr in self.my_territories
                    for unit in from_terr.units
                    if unit.owner == player
                    if unit.unit_type != "aaGun"
                    if unit.moved == False
                    if self.check_reachability(unit, from_terr.name, enemy_territory_name)
                ]
                # sort units based on (adjacent_to_target desc, attack_power desc, donor_is_border asc) - NEED TO FIX
                def attack_power(unit):
                    stats = game_rules.get(unit.unit_type, {})
                    return stats.get("attack", 1)

                def is_border_territory(terr_name: str) -> bool:
                    return any(self.territories[n].owner != player for n in adjacency.neighbors(terr_name))

                def adjacent_to_target(from_name: str, target_name: str) -> bool:
                    return target_name in adjacency.neighbors(from_name)

                def donor_score(x):
                    score = 0.0
                    if adjacent_to_target(x["from"], enemy_territory_name):
                        score += 100.0
                    score += 10.0 * attack_power(x["unit"])
                    if is_border_territory(x["from"]):
                        score -= 30.0
                    return score

                units_that_can_attack.sort(key=donor_score, reverse=True)
                
                if time.time() - start > time_budget:
                    return
                # If no units can reach the territory, skip
                if not units_that_can_attack:
                    self.excluded.add(enemy_territory_name)
                    continue

                # the territory is reachable 
                # Always include option to skip attack on this territory
                # self.actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[]))

                defender_strength = 0
                units_at_target = [u for u in enemy_territory.units if u.owner != player and u.unit_type != "factory"]
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
                if unitsUpToStrength and currentStrength>defender_strength:
                    attacks = self.form_attacks(unitsUpToStrength) 
                    if not sets or sets[-1][1] != currentStrength:
                        sets.append((attacks, currentStrength))

                if not sets:
                    weak_sets = []
                    unitsUpToStrength = []
                    strengthThreshold_weak = 0.35  # start chipping at ~35% of defense
                    for unit in units_that_can_attack:
                        unitsUpToStrength.append(unit)
                        currentStrength = self.calculate_attack_strength(unitsUpToStrength)

                        if currentStrength > strengthThreshold_weak * defender_strength and currentStrength <= defender_strength:
                            attacks = self.form_attacks(unitsUpToStrength)
                            weak_sets.append((attacks, currentStrength))
                            strengthThreshold_weak += 0.15
                            if len(weak_sets) >= 3:
                                break

                    # only add if we actually built chip candidates
                    sets.extend(weak_sets)

                if not sets:
                    if defender_strength == 0:
                        # pick the "cheapest" single-unit capture from the sorted donors
                        best = units_that_can_attack[0]

                        attacks = self.form_attacks([{"from": best["from"], "unit": best["unit"], "qty": 1}])
                        strength = self.calculate_attack_strength([{"from": best["from"], "unit": best["unit"], "qty": 1}])

                        self.actions.append(Move(delegate="combat",
                                                to_terr=enemy_territory_name,
                                                moves=attacks,
                                                strength=strength))

                        self.excluded.add(enemy_territory_name)
                        return

                sets.reverse()
                for unitSet, strength in sets:
                    self.actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=unitSet, strength=strength))

                # Always include option to skip attack on this territory
                self.actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[]))

                self.excluded.add(enemy_territory_name)
                
                return 

        self.actions.append(Move(delegate="combat", end_phase=True, strength=0))

               
    def heuristic_non_combat_legal_moves(self, time_budget):
        territories = copy.deepcopy(self.territories)
        my_territories = copy.deepcopy(self.my_territories)
        player = self.current_player
        move_seq = []

        my_frontier_territories = set()
        for terr in my_territories:
            for n in adjacency.neighbors(terr.name):
                if self.territories[n].owner != self.current_player and n not in FACTORY_MAP.values():
                    my_frontier_territories.add(terr.name)
                    break
        
        home_factory = FACTORY_MAP[player]

        def count_defense_units(terr):
            return sum(u.quantity for u in terr.units if u.unit_type != "factory")

        def has_enemy_neighbor(name: str) -> bool:
            for n in adjacency.neighbors(name):
                if territories[n].owner != player and n not in FACTORY_MAP.values():
                    return True
            return False

        # staging score: how many frontier neighbors this tile borders
        staging_score = {}
        for terr in my_territories:
            staging_score[terr.name] = sum(1 for nb in adjacency.neighbors(terr.name) if nb in my_frontier_territories)

        # factory-adjacent score: how many victory cities adjacent (your code uses victory_cities as "factories/vc")
        factory_adj_score = {}
        for terr in my_territories:
            factory_adj_score[terr.name] = sum(1 for nb in adjacency.neighbors(terr.name) if nb in victory_cities)

        # ---------- distance-to-frontier (multi-source BFS) ----------
        dist_to_frontier = {name: float("inf") for name in territories.keys()}
        q = deque()
        for f in my_frontier_territories:
            dist_to_frontier[f] = 0
            q.append(f)

        while q:
            cur = q.popleft()
            for nb in adjacency.neighbors(cur):
                if dist_to_frontier[nb] > dist_to_frontier[cur] + 1:
                    dist_to_frontier[nb] = dist_to_frontier[cur] + 1
                    q.append(nb)

        # ---------- target priority ----------
        def territory_priority(territory):
            name = territory.name
            score = 0
            if name in my_frontier_territories:
                score += 1000
                if count_defense_units(territories[name]) == 0:
                    score += 500
            score += staging_score.get(name, 0) * 200
            score += factory_adj_score.get(name, 0) * 100
            return score

        targets = list(my_territories)
        targets.sort(key=territory_priority, reverse=True)    

        
        def best_step_toward_frontier(unit, from_name: str):
            best = None
            best_score = -10**9

            from_d = dist_to_frontier.get(from_name, float("inf"))

            for dest in targets:
                dest_name = dest.name
                if dest_name == from_name:
                    continue
                if not self.check_reachability(unit, from_name, dest_name):
                    continue

                to_d = dist_to_frontier.get(dest_name, float("inf"))
                improvement = from_d - to_d  # want positive

                # prefer real progress; ignore non-improving unless nothing else exists
                score = improvement * 100
                if dest_name in my_frontier_territories:
                    score += 50
                score += staging_score.get(dest_name, 0) * 10
                score += factory_adj_score.get(dest_name, 0) * 5

                if score > best_score:
                    best_score = score
                    best = dest_name
            return best, best_score

        def quota(territory):
            name = territory.name
            qv = 1
            if name in my_frontier_territories:
                qv = 5
            # staging / factory-adj tiles get medium quota (but frontier still dominates)
            if staging_score.get(name, 0) > 0 or factory_adj_score.get(name, 0) > 0:
                qv = max(qv, 3)
            return qv

        # ---------- donors ----------
        # Don't drain frontier tiles, except allow draining home_factory (evacuation) specially below.
        donor_territories = []
        for t in my_territories:
            if count_defense_units(t) <= 0:
                continue
            if t.name in my_frontier_territories and t.name != home_factory:
                continue
            donor_territories.append(t)
        # print(donor_territories)
        # ---------- PASS 0: evacuate home factory before placement ----------
        # Keep a small garrison only if threatened.
        # keep_min = 2 if has_enemy_neighbor(home_factory) else 0
        # factory_terr = territories[home_factory]

        # movable_from_factory = []
        # for u in factory_terr.units:
        #     move_range = game_rules.get(u.unit_type, {}).get("move", 1)
        #     if u.owner == player and u.unit_type != "factory" and move_range > 0 and u.quantity > 0:
        #         movable_from_factory.append(u)
        
        # excess = max(0, count_defense_units(factory_terr) - keep_min)
        # sent = 0

        # for unit in movable_from_factory:
        #     while unit.quantity > 0 and sent < excess:
        #         # try best high-priority targets first
        #         dest = None
        #         dest, score = best_step_toward_frontier(unit, home_factory)
        #         if dest is None or score <= 0:
        #             break
                
        #         attack = Attack(unit=unit, from_territory=home_factory, quantity=1)
        #         mv = Move("noncombat", to_terr=dest, moves=[attack])
        #         print(f"noncombat gen from factory: {mv}")
        #         move_seq.append(mv)
        #         unit.quantity -= 1  # safe: operates on deepcopy
        #         sent += 1
        # ---------- PASS 1: fill targets to quota (with step-to-frontier fallback) ----------

        for terr in targets:
            terr_name = terr.name
            if count_defense_units(territories[terr_name]) >= quota(terr):
                continue

            while count_defense_units(territories[terr_name]) < quota(terr):
                moved_one = False

                for donor in donor_territories:
                    if count_defense_units(donor) <= 0:
                        continue
                    if donor.name != home_factory and count_defense_units(donor) <= 0:
                        continue

                    # pick one unit from donor
                    picked = None
                    for u in donor.units:
                        move_range = game_rules.get(u.unit_type, {}).get("move", 1)
                        if u.owner != player or u.quantity <= 0:
                            continue
                        if u.unit_type == "factory" or move_range <= 0:
                            continue
                        picked = u
                        break

                    if picked is None:
                        continue

                    dest = None
                    if self.check_reachability(picked, donor.name, terr_name):
                        dest = terr_name
                    else:
                        # fallback: step toward frontier (prefer improving moves)
                        step, score = best_step_toward_frontier(picked, donor.name)
                        if step is not None and score > 0:
                            dest = step

                    if dest is None:
                        continue
                    mv = Move("noncombat", to_terr=dest, moves=[Attack(unit=picked, from_territory=donor.name, quantity=1)])
                    # print(f"noncombat gen: {mv}")
                    move_seq.append(mv)

                    # update deepcopy counts
                    picked.quantity -= 1
                    moved_one = True
                    break  # re-check quota after each move

                if not moved_one:
                    break  # no donors can contribute further

        return move_seq

    def apply_purchase_move(self, move):
        player = self.current_player
        if not move or not move.moves:
            return 
        
        self.players[player].PU -= move.strength  
        for attack in move.moves:
            unit_type = attack.unit.unit_type
            quantity = attack.quantity
            self.players[player].unplaced[unit_type] = self.players[player].unplaced.get(unit_type, 0) + quantity

    def apply_combat_move(self, moves):
        for move in moves:
            if move.end_phase:
                # Don't change state, just signal to stop attacking
                # The game state stays the same
                return
            me = self.current_player
            if not move.moves:
                continue

            to = move.to_terr
            to_territory = self.territories[to]
            attacks = move.moves
            if not attacks:  
                continue
            
            defender_strength = 0
            units_at_target = [u for u in to_territory.units if u.owner != me and u.unit_type != "factory"]
            # assuming all the units at target belong to the terr owner = all previous battles resolved
            for unit in units_at_target:
                unit_type = unit.unit_type
                stats = game_rules.get(unit_type, {})
                power = stats.get("defense", 1)
                defender_strength += unit.quantity * power

            attacker_strength = move.strength
            
            for attack in attacks:
                frm = attack.from_territory
                unit_type = attack.unit.unit_type
                quantity = attack.quantity
                from_territory = self.territories[frm]
                from_territory.remove_unit(unit_type, me, quantity)
                if attacker_strength > defender_strength:
                    to_territory.add_unit(unit_type, me, quantity, moved=True)  # move all attacking units in if we win


            if attacker_strength > defender_strength:
                # win: move attackers in and clear defenders, then flip owner
                defender_owner = to_territory.owner
                for u in units_at_target:
                    to_territory.remove_unit(u.unit_type, defender_owner, u.quantity)
                to_territory.owner = me
            else:
                # lose/weak: attrition - spend attacker_strength to remove defender units
                remaining = attacker_strength
                defender_owner = to_territory.owner

                # sort defenders by defense power (cheapest to kill first)
                defenders = []
                for u in units_at_target:
                    d = game_rules.get(u.unit_type, {}).get("defense", 1)
                    defenders.append((d, u))
                defenders.sort(key=lambda x: x[0])

                for d_power, u in defenders:
                    if remaining <= 0:
                        break
                    # each unit costs d_power to remove
                    kill = min(u.quantity, int(remaining // max(1, d_power)))
                    if kill > 0:
                        to_territory.remove_unit(u.unit_type, defender_owner, kill)
                        remaining -= kill * d_power

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
            unit_type = attack.unit.unit_type
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

    def count_combat_units(self, whoAmI):
        count = 0
        for territory in self.territories.values():
            if territory.owner == whoAmI:
                for unit in territory.units:
                    if unit.unit_type != "factory" and unit.owner == whoAmI:
                        count += unit.quantity
        return count
    
    def reset_moved_flags(self):
        for territory in self.territories.values():
            for unit in territory.units:
                unit.moved = False


class MCTSNode:
    def __init__(self, state, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.untried_actions = None  # Lazy initialization
        self.visits = 0
        self.value = 0.0
        self.avg_playout_depth = 0

    def is_fully_expanded(self):
        return self.untried_actions is not None and len(self.untried_actions) == 0
    
    def is_terminal(self):
        return self.state.is_terminal()
    
    def best_child(self, c_param=1.414):
        bestNode = None
        choices_weights = [
            (child.value / child.visits) + c_param * math.sqrt(2 * math.log(self.visits) / child.visits)
            for child in self.children
        ]
        if choices_weights is not None:
            bestNode = self.children[choices_weights.index(max(choices_weights))]

        # bestNode = max(self.children,
        #    key=lambda c: (c.value / max(1, c.visits), c.visits))

        return bestNode


class MCTS:
    def __init__(self, model_name, reduction_file, efficiency_file, quality_file, rollout_file, production_rules, terr_production, vic_cities, adj, order, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.latest_legal_moves = []
        self.whoAmI = None
        
        # MCTS parameters
        self.time_budget = 1.0  # seconds per move
        self.max_depth = 5  # Maximum playout depth
        self.exploration_constant = 0.5  # UCB1 exploration parameter

        self.model_name = model_name
        # file paths to store metrics
        self.reduction_metric = MetricLogger(
            reduction_file,
            header=["game", "round", "total_moves", "pruned_moves"]
        )
        self.efficiency_metric = MetricLogger(
            efficiency_file,
            header=["game", "round", "num_iterations", "value"]
        )

        self.combat_quality = MetricLogger(
            quality_file,
            header=["game", "round", "pu_after", "territories_before", "territories_after"]
        )

        self.rollout_efficiency = MetricLogger(
            rollout_file,
            header=["game", "round", "iteration", "depth", "current_player", "terr_attacked_in_round (actions taken)"])

        global game_rules, territory_production, victory_cities, adjacency, turn_order
        game_rules = production_rules
        territory_production = terr_production
        victory_cities = vic_cities
        adjacency = adj
        turn_order = order

        # for logging purposes
        self.iteration = 0
        self.combat_done_flag = False
        self.terr_before_combat = 0
        self.terr_after_combat = 0
        self.pu_after_combat = 0

    def update_whoAmI(self, whoAmI):
        self.whoAmI = whoAmI

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
        print("\nGame ", ctf.game_num, " Round ", ctf.round, " [", ctf.whoAmI, "] ", line)
        isCombat = False
        try:
            m = re.search(r"\[MY_MOVE\] (\w+)", line)
            if m:
                move_type = m.group(1)
                if move_type == "purchase":
                    # ctf.round = int(round)
                    legal_moves = generate_legal_purchase_moves(ctf, ctf.whoAmI)

                    if legal_moves:
                        max_cost = max(move["cost"] for move in legal_moves)
                        best_moves = [move for move in legal_moves if move["cost"] == max_cost]
                        move = random.choice(best_moves)
                        response = convert_purchase_to_json(move)
                    else:
                        # print("No legal purchase moves available.")
                        response = []
                    # response = []
                elif move_type == "combat":
                    self.terr_before_combat = sum(1 for t in ctf.territories.values() if t.owner == ctf.whoAmI)
                    current_state = MCTSGameState(ctf)
                    # img_file = f"{self.model_name}/combat_moves/graph_{ctf.game_num}_{round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    profile_name = f"{self.model_name}/profiles/mcts_{ctf.game_num}_"
                    if ctf.round < 10:
                        profile_name += "0"
                    profile_name += round + ".prof"
                    action = self.profile_mcts(current_state, profile_name)
                    response = convert_multi_front_combat_to_json(action)
                    isCombat = True
                elif move_type == "noncombat":
                    # img_file = f"multi_front_attack/noncombat_moves/graph_{ctf.game_num}_{round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    legal_move = generate_legal_noncombat_moves(ctf, ctf.whoAmI)
                    if legal_move:
                        # moves = random.choice(legal_moves)
                        response = convert_multi_front_noncombat_to_json(legal_move)
                    else:
                        # print("No legal noncombat moves available.")
                        response = []  
                else:
                    # print("Unsupported move type:", move_type)
                    response = []

            return response, isCombat    
        except Exception as e:
            print(e)
            time.sleep(4)
            return [], isCombat


    def select(self, init_node):
        node = init_node
        while not node.is_terminal():
            nextAction = node.state.getNextAction()
            # print(f"Action selected {nextAction}\n")
            if nextAction is not None and nextAction.end_phase != True:
                return self.expand(node, nextAction)
            elif node.children != []:
                # All actions tried, select best child using UCB1
                # print(len(node.children))
                bestChild = node.best_child(self.exploration_constant)
                if bestChild is None:
                    return node
                node = bestChild
            else:
                return node
        # print("\tselected")
        return node
    
    def expand(self, parent, action):
        new_state = parent.state.clone()
        
        try:
            new_state.apply_combat_move([action])
            new_state.heuristic_combat_legal_moves(self.time_budget)
            
        except Exception as e:
            print(f"Error in expansion: {e}")
            return parent
        
        # Create child node
        child = MCTSNode(new_state, parent=parent, action=action)
        parent.children.append(child)
        # print("\texpanded")
        return child
    
    def pick_rollout_move(self, actions, whoAmI, cur_player, min_attacks_done, topk=3):
        # Separate actions
        real = [a for a in actions if (not getattr(a, "end_phase", False)) and getattr(a, "moves", None)]
        empties = [a for a in actions if (not getattr(a, "end_phase", False)) and not getattr(a, "moves", None)]
        endp = [a for a in actions if getattr(a, "end_phase", False)]

        # If I'm the player, force some pressure early
        if cur_player == whoAmI and min_attacks_done < 2:
            if real:
                k = min(topk, len(real))
                # depth, player, attacks_done, n_actions_total, n_actions_real, picked_type
                # print(f"\tRollout move selection - player: {cur_player}, attacks_done: {min_attacks_done}, actions_total: {len(actions)}, actions_real: {len(real)}, picked_type: real")
                return random.choice(real[:k])
            # print(f"\tRollout move selection - player: {cur_player}, attacks_done: {min_attacks_done}, actions_total: {len(actions)}, actions_real: {len(real)}, picked_type: empty/end")
            # if no real attacks exist, allow empty or end
            return empties[0] if empties else (endp[0] if endp else actions[0])

        # For others: normal rollout behavior (top-k real if exists, else anything)
        if real:
            # print(f"\tRollout move selection - player: {cur_player}, attacks_done: {min_attacks_done}, actions_total: {len(actions)}, actions_real: {len(real)}, picked_type: real")
            k = min(topk, len(real))
            return random.choice(real[:k])
        # print(f"\tRollout move selection - player: {cur_player}, attacks_done: {min_attacks_done}, actions_total: {len(actions)}, actions_real: {len(real)}, picked_type: empty/end")
        return endp[0] if endp else actions[0]


    def simulate(self, state, time_done):
        current_state = state.clone()
        depth = 0  
    
        try:
            # Simulate future rounds
            # time_left = self.time_budget - time_done
            # start = time.time()
            
            first_sim = True
            while depth < self.max_depth and not current_state.is_terminal():
                start_idx = turn_order.index(state.current_player)
                end_of_cycle = (start_idx - 1) % len(turn_order)
                idx = start_idx
                current_state.reset_moved_flags()   # reset moved status at the start of the round for all units
                while True:
                    current_state.current_player = turn_order[idx]
                    # print(f"Rollout - player: {current_state.current_player}")
                    if not first_sim:       # since the first sim would have already have atleast 1 terr in the excluded set, and the action would be execute in the expand phase
                        # do purchase
                        purchase_moves = current_state.purchase_legal_moves()
                        if purchase_moves:
                            max_cost = max(move.strength for move in purchase_moves)
                            best_moves = [move for move in purchase_moves if move.strength == max_cost]
                            # print(best_moves)
                            move = random.choice(best_moves)
                            current_state.apply_purchase_move(move)
                        current_state.excluded = set()
                        current_state.set_terr_lists()

                    # print(f"\n\texcluded: {current_state.excluded}, \n\tmy terr: {[t.name for t in current_state.my_territories]}, \n\tenemy terr: {[t.name for t in current_state.enemy_territories]}")
                    move_seq = []
                    while True:
                        current_state.heuristic_combat_legal_moves(self.time_budget)
                        # actions successfully generated for the most important enemy territory
                        if current_state.actions:
                            # do the best move since that would be the strongest if the territories and units are ordered correctly
                            # best_move = current_state.actions[0]
                            # k = min(3, len(current_state.actions))
                            # mv = random.choice(current_state.actions[:k])
                            mv = self.pick_rollout_move(current_state.actions, self.whoAmI, current_state.current_player, len(move_seq), topk=3)

                            if getattr(mv, "end_phase", False):
                                break
                            if getattr(mv, "moves", None):     # count only real attacks
                                move_seq.append(mv)

                            current_state.apply_combat_move([mv])
                    if first_sim:
                        self.rollout_efficiency.log(state.game_num, state.round, self.iteration, depth, current_state.current_player, len(move_seq)+1)
                    else:
                        self.rollout_efficiency.log(state.game_num, state.round, self.iteration, depth, current_state.current_player, len(move_seq))
                    # print(f" Combat move: {move_seq}\n")
                    noncombat_moves = current_state.heuristic_non_combat_legal_moves(self.time_budget)
                    # print(f" Non-combat moves: {noncombat_moves}\n\n")
                    for mv in noncombat_moves:
                        current_state.apply_noncombat_move(mv)

                    player = current_state.players[current_state.current_player]
                    # place the purchased items for whoami at the end of the current round before simulating the next round, since that is when they would actually be placed in the real game
                    if first_sim:
                        first_sim = False
                    player.place_units()
                    current_state.update_income(player)

                    # if first_sim:
                    #     first_sim = False
                    
                    if current_state.is_terminal():
                        depth += 1
                        break
                    
                    # Round increments only after last player in the order finishes
                    if idx == end_of_cycle:
                        depth += 1

                        # if depth cap reached, break out early
                        if depth >= self.max_depth:
                            break

                    idx = (idx + 1) % len(turn_order)
                    if idx == start_idx:
                        break

                    # if idx == 0:
                    #     current_state.round += 1


        except Exception as e:
            print(f"Error in simulation: {e}")
            return -0.5, depth
        
        # Evaluate final state
        return self.evaluate_state(current_state, depth), depth
    
    def backpropagate(self, node, reward):
        while node is not None:
            node.visits += 1
            node.value += reward
            node = node.parent


    def mcts_search(self, initial_state):
        # print("Generating moves")
        initial_state.heuristic_combat_legal_moves(self.time_budget)
        # print(f"Moves generated {initial_state.actions}\n")
        root = MCTSNode(initial_state)
                
        start_time = time.time()
        self.iteration = 0
        # avg_depth = 0
        
        while time.time() - start_time < self.time_budget:
            self.iteration += 1
            # print(f"Iter: {self.iteration}")
            # 1. Selection and expansion
            selected_node = self.select(root)
            # print(f"Moves generated after expansion {selected_node.state.actions}\n")
            reward, depth = self.simulate(selected_node.state, time.time() - start_time)
        
            selected_node.avg_playout_depth = (selected_node.avg_playout_depth * (selected_node.visits) + depth) / (selected_node.visits + 1) if selected_node.visits + 1 > 0 else 0
            self.backpropagate(selected_node, reward)
            
            
            # print(f"Action: {selected_node.state.actions}")
        
        print(f"MCTS ran {self.iteration} iterations in {self.time_budget}s")
        print(f"Root node visits: {root.visits}")

        # tree_prefix = f"{self.model_name}/trees/tree_g{root.state.game_num}_r{root.state.round}"
        # os.makedirs(os.path.dirname(tree_prefix), exist_ok=True)
        # dot_file, png_file = save_mcts_tree_png(root, tree_prefix, max_nodes=500)
        # print("Saved tree:", dot_file, png_file)

        action_seq = []
        node = root
        while node.children != []:
            best_child = max(node.children, key=lambda c: c.visits)
            if best_child is None:
                break
            if best_child.action.moves is not None and best_child.action.end_phase == False and best_child.action.strength != 0:
                action_seq.append(best_child.action)
            if best_child.action.end_phase == True:
                break
            node = best_child

        avg_value = root.value / root.visits
        self.efficiency_metric.log(root.state.game_num, root.state.round, self.iteration, avg_value)
        return action_seq

    
    def profile_mcts(self, initial_state, file):
        # import cProfile
        # with cProfile.Profile() as pr:
        result = self.mcts_search(initial_state)
        # pr.dump_stats(file)
        return result

    # def evaluate_state(self, state, depth):
    #     # Thesis: max playout depth = 10
    #     max_d = self.max_depth

    #     if state.is_terminal():
    #         if state.am_i_winner():
    #             return 0.6 + 0.4 * (max_d - depth) / max_d
    #         else:
    #             return -0.6 - 0.4 * (max_d - depth) / max_d

    #     # 4-player adaptation: "allied" = me, "enemy" = everyone else
    #     allied = 0
    #     enemy = 0
    #     me = state.current_player  # in your state, this is "whoAmI"

    #     for terr in state.territories.values():
    #         for u in terr.units:
    #             if u.unit_type == "factory":
    #                 continue
    #             if u.owner == me:
    #                 allied += u.quantity
    #             else:
    #                 enemy += u.quantity

    #     total = allied + enemy
    #     if total == 0:
    #         return 0.0

    #     return (allied - enemy) / (total * 2)


    def evaluate_state(self, state, depth):
        if state.is_terminal():
            if state.am_i_winner(self.whoAmI):
                return 0.6 + 0.4 * (self.max_depth - depth) / self.max_depth
            else:
                return -0.6 - 0.4 * (self.max_depth - depth) / self.max_depth

        me = self.whoAmI

        my_terrs = [t for t in state.territories.values() if t.owner == me]
        enemy_terrs = [t for t in state.territories.values()
                    if t.owner != me and t.owner != "Neutral"]

        my_count = len(my_terrs)
        enemy_count = len(enemy_terrs)

        my_vc_count = sum(1 for t in my_terrs if t.name in victory_cities)
        enemy_vc_count = sum(1 for t in enemy_terrs if t.name in victory_cities)

        # --- TUV evaluation ---
        def tuv(territories, owner):
            total = 0.0
            for terr in territories.values():
                for u in terr.units:
                    if u.owner != owner:
                        continue
                    if u.unit_type == "factory":
                        continue
                    stats = game_rules.get(u.unit_type, {})
                    cost = stats.get("cost", 1)
                    total += u.quantity * cost
            return total

        my_tuv = tuv(state.territories, me)
        enemy_tuv = 0.0
        for p in state.players.keys():
            if p != me and p != "Neutral":
                enemy_tuv += tuv(state.territories, p)

        tuv_term = (my_tuv - enemy_tuv) / max(1e-9, (my_tuv + enemy_tuv))

        terr_term = (my_count - enemy_count) / max(1, (my_count + enemy_count))
        vc_term = (my_vc_count - enemy_vc_count) / max(1, (my_vc_count + enemy_vc_count + 1))
        
        score = 0.0
        score += 0.50 * terr_term
        score += 0.20 * vc_term
        score += 0.30 * tuv_term

        return max(-0.5, min(0.5, score))



    