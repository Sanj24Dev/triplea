# multi front attack

import math
import random
from collections import deque, defaultdict
import itertools
import time
import re
from itertools import product
import copy
import os
import subprocess
import numpy as np
import pickle
import torch

from helper import convert_purchase_to_json, convert_multi_front_combat_to_json, convert_multi_front_noncombat_to_json, get_combat_action_ids
from ctf_graph import Territory, Player, MetricLogger, FACTORY_MAP, Unit
from nn_models.utils.encoding import get_encoded_state
from nn_models.utils.move_db import update_combat_dict, move_to_id, id_to_move
from nn_models.data.self_play_data import SelfPlayExample

from filelock import FileLock

import move_generator_cpp

game_rules = None
territory_production = None
victory_cities = None
adjacency = None
turn_order = None

unit_move_ranges = None
unit_attack_points = None
unit_defense_points = None
unit_costs = None

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

def save_mcts_tree_png(root, out_prefix, max_nodes=500, render_img=False):
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
            label = f"#{nid}\\nvis={n.visits}\\navg={avg:.3f}\\np={n.prior:.3f}"
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
    if render_img:
        try:
            subprocess.run(["dot", "-Tpng", dot_path, "-o", png_path], check=True)
            return dot_path, png_path
        except Exception:
            return dot_path, None
    else:
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
            # new_territory = Territory(name, territory.owner)
            # new_territory.properties = territory.properties.copy()
            new_territory = move_generator_cpp.Territory()
            new_territory.name = territory.name
            new_territory.owner = territory.owner
            new_territory.units = []

            for unit in territory.units:
                if unit.unit_type != "factory":
                    cython_unit = move_generator_cpp.Unit()
                    cython_unit.unit_type = unit.unit_type
                    cython_unit.owner = unit.owner
                    cython_unit.moved = unit.moved
                    cython_unit.quantity = unit.quantity

                    new_territory.add_unit(unit.unit_type, unit.owner, unit.quantity, unit.moved)
            
            
            # Copy units
            # for unit in territory.units:
            #     new_territory.add_unit(
            #         unit.unit_type,
            #         unit.owner,
            #         unit.quantity,
            #         unit.properties.copy(),
            #         unit.moved
            #     )
            
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
        cpp_adjacency = {
            name: list(adjacency.neighbors(name))
            for name, _ in self.territories.items()
        }
        move_generator_cpp.set_adjacency(cpp_adjacency)

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
    
    def get_reachable_enemy_territories(self):
        reachable = []
        my_terr_names = {t.name for t in self.my_territories}
        
        for enemy_terr in self.enemy_territories:
            # an enemy terr is reachable if any of its neighbors is mine
            for neighbor in adjacency.neighbors(enemy_terr.name):
                if neighbor in my_terr_names:
                    reachable.append(enemy_terr)
                    break
        
        return reachable

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
            priority_score += surrounded_by_me * 50

            # distance to the victory cities? closer => better to attack

            enemy_neighbors = sum(1 for n in adjacency.neighbors(terr_name) 
                         if self.territories[n].owner == territory.owner)
            priority_score -= enemy_neighbors * 30

            unit_count = sum(u.quantity for u in territory.units if u.unit_type != "factory")
            # more the units, less priority (more costly to attack)
            priority_score -= unit_count * 2

            return priority_score
        
        self.enemy_territories = self.get_reachable_enemy_territories()
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


    def heuristic_combat_legal_moves(self, time_budget):
        player = self.current_player
        self.actions = []
        self.actionIndex = 0
        start = time.time()

        # territories = {}
        my_territories = set()
        enemy_territories = set()
        for territory_name, territory in self.territories.items():
            if territory.owner == player:
                my_territories.add(territory_name)
            else:
                enemy_territories.add(territory_name)

        # time_left = time_budget - (time.time() - start)
        # print(f"In round {self.round}")
        results = move_generator_cpp.heuristic_combat_legal_moves(
            player = self.current_player,
            territories = self.territories,
            my_territory_names = my_territories,
            enemy_territory_names = enemy_territories,
            excluded = self.excluded,
            time_budget = time_budget
        )
        actions, self.excluded = results
        if actions != None and actions != []:
            self.actions = actions
        else:
            self.actions.append(Move(delegate="combat", end_phase=True, strength=0))


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
                    to_territory.add_unit(unit_type, me, quantity, True, quantity)  # move all attacking units in if we win


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

    def how_many_moved(self):
        m = 0
        for t, terr in self.territories.items():
            m += sum(u.qty_moved for u in terr.units)
        return m

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


class P_MCTSNode:
    # __slots__ = ["state", "parent", "action", "action_id", "children", "visits", "value", "prior"]
    def __init__(self, state, parent=None, action=None, prior=1.0, action_id=0):
        self.state = state
        self.parent = parent
        self.action = action
        self.action_id = action_id
        self.children = []
        self.untried_actions = None 
        self.visits = 0
        self.value = 0.0
        self.value_output = 0.0
        self.prior = prior
        self.p_prior = 0.5 * prior  # to reduce multiplication in best_child function
        self.node_priors = None

        self.is_state_terminal = None

    def is_fully_expanded(self):
        return self.untried_actions is not None and len(self.untried_actions) == 0
    
    def is_terminal(self):
        if self.is_state_terminal is None:
            self.is_state_terminal = self.state.is_terminal()
        return self.is_state_terminal

    def is_leaf(self):
        return len(self.children) == 0
    
    # def puct_score(self, c_puct=1.5):
    #     if self.visits == 0:
    #         return float("inf")
    #     q = self.value / self.visits
    #     u = c_puct * self.prior * math.sqrt(self.parent.visits) / (1 + self.visits)
    #     return q + u
    
    def best_child_puct(self, c_puct=1.5):
        parent_visits_sqrt = math.sqrt(self.visits)
        best = None
        best_score = -float("inf")
        for child in self.children:
            v = child.visits
            if v == 0:
                return child  # inf score, no need to check others
            q = child.value / v
            u = child.p_prior * parent_visits_sqrt / (1 + v)
            score = q + u
            if score > best_score:
                best_score = score
                best = child
        return best


class PolicyGuidedMCTS:
    def __init__(
            self, 
            model_name, port, net,
            efficiency_file, quality_file, 
            production_rules, terr_production, vic_cities, adj, order, 
            # move_to_id, id_to_move,
            device="cuda",
            ):

        self.latest_legal_moves = []
        self.episode_examples = []   # current game examples
        self.last_pi = []            # set after each mcts_search
        self.shared_buffer_path = f"{model_name}/checkpoints/gnn/shared_buffer_{port}.pkl"
        self.weight_path = f"{model_name}/checkpoints/gnn/latest.pt"
        self.games_played = 0
        self.whoAmI = None
        self.curr_game_len = 0
        
        # MCTS parameters
        self.time_budget = 2.0  # seconds per move
        self.iteration_budget = 1000
        self.max_depth = 5  # Maximum playout depth
        self.c_puct = 1.5 
        self.dirchlet_alpha = 0.3
        self.dirichlet_eps = 0.25

        self.model_name = model_name
        self.port = port
        self.net = net.to(device)
        self.device = device

        # file paths to store metrics
        self.efficiency_metric = MetricLogger(
            efficiency_file,
            header=["game", "round", "num_iterations", "max_depth", "time_taken", "num_children", "value"]
        )

        self.combat_quality = MetricLogger(
            quality_file,
            header=["game", "round", "pu_after", "territories_after"]
        )

        self.entropy_logger = MetricLogger(
            f"{model_name}/metrics/entropy.csv",
            header=["port", "game", "round", "depth", "num_children", "entropy_ratio", "q_spread", "concentration"]
        )

        self.value_metrics = MetricLogger(
            f"{model_name}/metrics/value_metrics.csv",
            header=["game", "player", "z", "num_examples", "value_mean", "value_std", "percent_full_iter"]
        )

        global game_rules, territory_production, victory_cities, adjacency, turn_order
        game_rules = production_rules
        territory_production = terr_production
        victory_cities = vic_cities
        adjacency = adj
        turn_order = order

        global unit_move_ranges, unit_attack_points, unit_defense_points, unit_costs
        # cpp_adjacency = {
        #     name: list(adjacency.neighbors(name))
        #     for name in self.territories
        # }
        # move_generator_cpp.set_adjacency(cpp_adjacency)
        unit_move_ranges = {name: data.get("move", 1) for name, data in game_rules.items()}
        move_generator_cpp.set_unit_move_ranges(unit_move_ranges)
        unit_attack_points = {name: data.get("attack", 0) for name, data in game_rules.items()}
        move_generator_cpp.set_unit_attack_values(unit_attack_points)
        unit_defense_points = {name: data.get("defense", 0) for name, data in game_rules.items()}
        move_generator_cpp.set_unit_defense_values(unit_defense_points)
        unit_costs = {name: data.get("cost", 1) for name, data in game_rules.items()}
        move_generator_cpp.set_unit_costs(unit_costs)

        # for logging purposes
        self.iteration = 0
        self.max_depth = 0
        self.combat_done_flag = False
        self.terr_before_combat = 0
        self.terr_after_combat = 0
        self.pu_after_combat = 0

    def update_whoAmI(self, whoAmI):
        self.whoAmI = whoAmI

    def get_move(self, line, ctf, round):
        line = line.strip()
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
                        response = []
                    # response = []
                elif move_type == "combat":
                    current_state = MCTSGameState(ctf)

                    # img_file = f"{self.model_name}/combat_moves/graph_{ctf.game_num}_{round}_{self.port}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")

                    profile_name = f"{self.model_name}/profiles/mcts_{self.port}_{ctf.game_num}_"
                    if ctf.round < 10:
                        profile_name += "0"
                    profile_name += round + ".prof"
                    action = self.profile_mcts(current_state, profile_name)

                    # print(f"Actions selected: {action_ids}")
                    # print(action)
                    response = convert_multi_front_combat_to_json(action)
                    isCombat = True
                elif move_type == "noncombat":
                    # img_file = f"multi_front_attack/noncombat_moves/graph_{ctf.game_num}_{round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")
                    legal_move = generate_legal_noncombat_moves(ctf, ctf.whoAmI)
                    if legal_move:
                        response = convert_multi_front_noncombat_to_json(legal_move)
                    else:
                        response = []  
                else:
                    response = []

            return response, isCombat    
        except Exception as e:
            print(e)
            time.sleep(4)
            return [], isCombat



    def encode(self, state):
        return get_encoded_state(
            state, adjacency, turn_order,
            victory_cities, territory_production
            )
    
    def encode_move_features(self, action, state) -> np.ndarray:
        return np.array([
            action.strength / 10.0,
            sum(a.quantity for a in action.moves) / 10.0,
            1.0 if action.to_terr in victory_cities else 0.0,
            territory_production.get(action.to_terr, 0) / 5.0,
            # atack breadth => how many terr are attacking this terr
            len(action.moves) / 5.0,
            1.0 if not action.moves else 0.0,

            action.strength / max(1.0, sum(
                u.quantity * game_rules.get(u.unit_type, {}).get("defense", 1)
                for u in state.territories[action.to_terr].units
                if u.unit_type != "factory"
            )),



        ], dtype=np.float32)
    
    def get_priors(self, state, legal_actions):
        valid = [(move_to_id(a), a) for a in legal_actions if not a.end_phase]
        if not valid:
            return {}

        move_feats = [self.encode_move_features(a, state) for _, a in valid]
        data = self.encode(state)
        node_feats = data.x
        edge_index = data.edge_index
        probs = self.net.score_moves_batch(node_feats, edge_index, move_feats, self.device)

        return {aid: float(p) for (aid, _), p in zip(valid, probs)}

    
    def expand(self, node):
        if node.node_priors is None:
            actions = node.state.actions
            priors = self.get_priors(node.state, actions)
            is_root = node.parent is None
            if is_root and self.dirichlet_eps > 0:
                aids = list(priors.keys())
                noise = np.random.dirichlet([self.dirchlet_alpha] * len(aids))
                
                for i, aid in enumerate(aids):
                    priors[aid] = (1 - self.dirichlet_eps) * priors[aid] + self.dirichlet_eps * noise[i]
            node.node_priors = priors

        # print(node.state.actions)
        action = node.state.getNextAction()
        # print(f"\tSelected: {action}")
        if action == None or action.end_phase == True:
            node.untried_actions = []
            value = self.simulate(node.state)
            return node, value
        else:
            aid = move_to_id(action)
            prior = node.node_priors.get(aid, 1e-6)
            new_state = node.state.clone()
            new_state.apply_combat_move([action])
            # time_left = self.time_budget - (time.time() - start_time)
            # prit(time_left)
            time_left = 0.01
            new_state.heuristic_combat_legal_moves(time_left)
            update_combat_dict(new_state.actions)
            child = P_MCTSNode(state=new_state, parent=node, 
                            action=action, prior=prior, action_id=aid)
            node.children.append(child)
            value = self.simulate(child.state)
            child.value_output = value
            return child, value


    def simulate(self, state):
        tensor = self.encode(state)
        value = self.net.predict_value(tensor.x, tensor.edge_index, self.device)
        return float(value)
        
    
    def backpropagate(self, node, reward):
        depth = 0
        while node is not None:
            node.visits += 1
            node.value += reward
            node = node.parent
            depth += 1
        self.max_depth = max(getattr(self, 'max_depth', 0), depth - 1)

    def mcts_search(self, initial_state, file):
        initial_state.heuristic_combat_legal_moves(0.01)
        update_combat_dict(initial_state.actions)
        # print("updated dict")

        root = P_MCTSNode(initial_state)
        # if initial_state.actions:
        #     self.expand(root, initial_state.actions)
                
        start_time = 0
        end_time = 0
        import cProfile
        with cProfile.Profile() as pr:
            self.iteration = 0
            self.max_depth = 0
            start_time = time.time()
            # while time.time() - start_time < self.time_budget:
            # ideally want to get iteration budget, but if it takes too long then stop 
            while self.iteration < self.iteration_budget and time.time() - start_time < 10.0:
                self.iteration += 1
                # print(self.iteration)
                # --- Selection: walk down until leaf or terminal ---
                node = root
                while node.is_fully_expanded() and not node.is_leaf() and not node.is_terminal():
                    best = node.best_child_puct(self.c_puct)
                    if best is None:
                        break
                    node = best

                # --- Expand or evaluate terminal ---
                if node.is_terminal():
                    value = self.simulate(node.state)  # or use known outcome
                else:
                    node, value = self.expand(node)   # expand leaf

                # --- Backprop always ---
                self.backpropagate(node, value)

            end_time = time.time()
        pr.dump_stats(file)


        
        game_num = root.state.game_num
        game_round = root.state.round
        if game_num == 1 or game_num % 10 == 0:
            tree_prefix = f"{self.model_name}/trees/tree_g{root.state.game_num}_r{root.state.round}_{self.port}"
            os.makedirs(os.path.dirname(tree_prefix), exist_ok=True)
            dot_file, png_file = save_mcts_tree_png(root, tree_prefix, max_nodes=500, render_img=True)
        # print("Saved tree:", dot_file, png_file)

        # print(f"MCTS completed {self.iteration} iterations in {round(end_time - start_time, 2)} seconds. Max depth reached: {self.max_depth}")

        action_seq = []
        node = root
        depth = 0
        # print(f"Round {root.state.round}")
        while node.children != []:
            # best_child = max(node.children, key=lambda c: c.visits)
            max_visits = max(c.visits for c in node.children)
            best_children = [c for c in node.children if c.visits == max_visits]
            
            if len(best_children) == 1:
                best_child = best_children[0]
            else:
                # Tiebreak 1: Q value (avg value = value/visits)
                max_q = max(c.value / max(c.visits, 1) for c in best_children)
                best_q = [c for c in best_children if c.value / max(c.visits, 1) == max_q]
                
                if len(best_q) == 1:
                    best_child = best_q[0]
                else:
                    # Tiebreak 2: prior
                    best_child = max(best_q, key=lambda c: c.prior)

            if best_child is None:
                break

            
            total_visits = sum(c.visits for c in node.children)
            move_pi = [(c.action, c.visits/total_visits) for c in node.children]
            data = self.encode(node.state)

            # if depth >= 1 and len(node.children) >= 2:
            visit_counts = np.array([c.visits for c in node.children])
            visited = visit_counts[visit_counts > 0]
            if depth > 0:
                if len(visited) >= 2:
                    probs = visited / visited.sum()
                    entropy_ratio = -(probs * np.log(probs + 1e-8)).sum() / np.log(len(probs))
                    entropy_ratio = round(entropy_ratio, 4)
                    q_values = [child.value/child.visits for child in node.children if child.visits > 0]
                    q_spread = round(max(q_values) - min(q_values), 4)
                    concentration = round(visit_counts.max() / visit_counts.sum(), 4)
                    self.entropy_logger.log(self.port, game_num, game_round, depth, len(node.children), entropy_ratio, q_spread, concentration)
            

            move_feats = [self.encode_move_features(m, node.state) for m, _ in move_pi]
            pi = [p for _, p in move_pi]
            self.episode_examples.append({
                "node_feats": data.x,           # tensor (N, F)
                "edge_index": data.edge_index,  # tensor (2, E)
                "move_feats": move_feats,
                "pi": pi,
                "player": self.whoAmI,
                "round_num": game_round,
                "num_iterations": self.iteration, 
                "value_output": node.value_output,
                "z": None
            })

            
            if best_child.action.moves is not None and best_child.action.end_phase == False and best_child.action.strength != 0:
                action_seq.append(best_child.action)
            if best_child.action.end_phase == True:
                break
            node = best_child
            depth += 1
            # print(f"Moved = {node.state.how_many_moved()}")

        avg_value = root.value / root.visits
        time_taken = round(end_time - start_time, 2)
        self.efficiency_metric.log(game_num, game_round, self.iteration, self.max_depth, time_taken, len(root.children), avg_value)

        
        return action_seq

    
    def profile_mcts(self, initial_state, file):
        # import cProfile
        # with cProfile.Profile() as pr:
        result = self.mcts_search(initial_state, file)
        # pr.dump_stats(file)
        return result

 
    def on_game_end(self, z_raw, my_game_length, final_round, game_num):
        
        completed = [
            SelfPlayExample(
                node_feats  = ex["node_feats"],
                edge_index  = ex["edge_index"],
                move_feats=ex["move_feats"],
                pi=ex["pi"],
                round_num=ex["round_num"],
                game_length=my_game_length,
                num_iterations=ex["num_iterations"],
                z = z_raw,
                # z=z_raw * (ex["round_num"] / final_round),
            )
            for ex in self.episode_examples
            if ex["pi"]  # skip if no pi recorded
        ]
        
        if completed:
            self._dump_to_shared_buffer(completed)
            
        value_mean_per_game = round(np.mean([ex["value_output"] for ex in self.episode_examples]), 4)
        value_std_per_game  = round(np.std([ex["value_output"]  for ex in self.episode_examples]), 4)
        percent_full_iter = 100 * round(sum([1 for ex in self.episode_examples if ex["num_iterations"] == 1000]) / len(self.episode_examples), 4)
        self.value_metrics.log(game_num, self.port, z_raw, len(completed), value_mean_per_game, value_std_per_game, percent_full_iter)
        self.episode_examples = []
        # self.games_played += 1
        
        # Sync weights every 5 games
        # if self.games_played % 5 == 0:
        # self._sync_weights()

    def _dump_to_shared_buffer(self, examples):
        lock_path = self.shared_buffer_path + ".lock"
        
        with FileLock(lock_path):
            existing = []
            if os.path.exists(self.shared_buffer_path):
                with open(self.shared_buffer_path, "rb") as f:
                    existing = pickle.load(f)
            existing.extend(examples)
            with open(self.shared_buffer_path, "wb") as f:
                pickle.dump(existing, f)

    def _sync_weights(self):
        if os.path.exists(self.weight_path):
            self.net.load_state_dict(
                torch.load(self.weight_path, map_location=self.device), strict=False
            )
            print(f"[{self.whoAmI}] Synced weights")
    