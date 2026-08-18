# multi front attack

import math
import random
from helper import convert_purchase_to_json, convert_multi_front_combat_to_json, convert_multi_front_noncombat_to_json
from collections import deque, defaultdict
import itertools
import time
import re
from itertools import product
import copy
import os
import subprocess
from ctf_graph import Territory, Player, MetricLogger, FACTORY_MAP, Unit, CaptureTheFlag
import pickle


import move_generator_cpp

game_rules = None
territory_production = None
victory_cities = None
adjacency = None
cpp_adjacency = None
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

def save_mcts_tree_png(root, logger, out_prefix, max_nodes=500, render_img=False):
    """
    Saves:
      - out_prefix + ".dot"
      - out_prefix + ".png" (if graphviz 'dot' is available)
    """
    # BFS traversal
    q = deque([root])
    node_id = {id(root): 0}
    parent_id = {id(root): -1}
    nodes = [root]
    edges = []

    while q and len(nodes) < max_nodes:
        n = q.popleft()
        for ch in n.children:
            if id(ch) not in node_id:
                node_id[id(ch)] = len(nodes)
                parent_id[id(ch)] = node_id[id(n)]
                nodes.append(ch)
                q.append(ch)
            edges.append((node_id[id(n)], node_id[id(ch)], ch.action))

    dot_path = out_prefix + ".dot"
    png_path = out_prefix + ".png"

    game = root.state.game_num
    round_num = root.state.round
    with open(dot_path, "w") as f:
        f.write("digraph MCTS {\n")
        f.write('  rankdir=TB;\n')
        f.write('  node [shape=box, fontsize=10];\n')

        for n in nodes:
            nid = node_id[id(n)]
            pid = parent_id[id(n)]
            avg = (n.value / n.visits) if n.visits else 0.0
            label = f"#{nid}\\nvis={n.visits}\\navg={avg:.3f}\\ntl={n.tree_level}"
            f.write(f'  n{nid} [label="{label}"];\n')
            logger.buffer(game, round_num, nid, pid, len(n.state.actions), n.tree_level, n.value, n.visits, avg)

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
        return []

    # units = [(name, data["cost"]) for name, data in game_rules.items() 
    #          if name not in {"fighter", "bomber", "aaGun", "factory"}]
    units = [(name, data["cost"]) for name, data in game_rules.items() 
             if name in {"infantry", "armour", "artillery"}]

    if ctf.round < 5:
        units = units + [(name, cost) for name, cost in units if name == "infantry"]
    elif ctf.round < 10:
        units = units + [(name, cost) for name, cost in units if name in {"infantry", "armour"}]
    elif ctf.round < 15:
        units = units + [(name, cost) for name, cost in units if name in {"armour", "artillery"}]
    else:
        units = units + [(name, cost) for name, cost in units if name == "armour"]
    units.sort(key=lambda x: x[1])  # sort by cost ascending

    purchase_dict = {}
    remaining = resources
    i = 0  # cycle index

    while True:
        # Cycle through unit types, skip if can't afford
        affordable = [(n, c) for n, c in units if c <= remaining]
        if not affordable:
            break
        # Pick the next unit in rotation
        name, cost = affordable[i % len(affordable)]
        purchase_dict[name] = purchase_dict.get(name, 0) + 1
        remaining -= cost
        i += 1

    if not purchase_dict:
        return []

    # print([(u, c) for u, c in purchase_dict.items()])
    return [{"purchase": purchase_dict, "cost": resources - remaining, "place_in": factories}]


def generate_legal_noncombat_moves(ctf, player):
    territories = copy.deepcopy(ctf.territories)
    move_seq = []

    # ---------- basics ----------
    my_territories = [t for t in territories.values() if t.owner == player]

    # frontier = my territory adjacent to non-owned (excluding factories as "enemy targets")
    my_frontier = set()
    for terr in my_territories:
        for n in ctf.neighbors.get(terr.name, []):
            # if territories[n].owner != player and n not in FACTORY_MAP.values():
            if territories[n].owner != player:
                my_frontier.add(terr.name)
                break

    home_factory = FACTORY_MAP[player]

    def count_defense_units(terr):
        return sum(u.quantity for u in terr.units if u.unit_type != "factory")

    def has_enemy_neighbor(name: str) -> bool:
        for n in ctf.neighbors.get(name, []):
            if territories[n].owner != player and n not in FACTORY_MAP.values():
                return True
        return False

    # staging score: how many frontier neighbors this tile borders
    staging_score = {}
    for terr in my_territories:
        staging_score[terr.name] = sum(1 for nb in ctf.neighbors.get(terr.name, []) if nb in my_frontier)

    # factory-adjacent score: how many victory cities adjacent (your code uses victory_cities as "factories/vc")
    factory_adj_score = {}
    for terr in my_territories:
        score = 0
        for nb in ctf.neighbors.get(terr.name, []):
            # if nb == home_factory:
            #     score += 3  # home factory specifically
            if nb in victory_cities:
                score += 1  # other victory cities
        factory_adj_score[terr.name] = score

    # ---------- distance-to-frontier (multi-source BFS) ----------
    dist_to_frontier = {name: float("inf") for name in territories.keys()}
    q = deque()
    for f in my_frontier:
        dist_to_frontier[f] = 0
        q.append(f)

    while q:
        cur = q.popleft()
        for nb in ctf.neighbors.get(cur, []):
            if dist_to_frontier[nb] > dist_to_frontier[cur] + 1:
                dist_to_frontier[nb] = dist_to_frontier[cur] + 1
                q.append(nb)
    # print("\nDistance to frontier:", [(t, dist_to_frontier[t]) for t in dist_to_frontier])

    dist_to_flag = {name: float("inf") for name in territories.keys()}
    q = deque()
    for f in territories.keys():
        if f == "Flag":
            dist_to_flag[f] = 0
            q.append(f)

    while q:
        cur = q.popleft()
        for nb in ctf.neighbors.get(cur, []):
            if dist_to_flag[nb] > dist_to_flag[cur] + 1:
                dist_to_flag[nb] = dist_to_flag[cur] + 1
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

        score += max(0, 5 - dist_to_flag.get(name, float("inf"))) * 20

        return score

    targets = list(my_territories)
    targets.sort(key=territory_priority, reverse=True)
    # print("Target priorities:", [(t.name, territory_priority(t)) for t in targets])
    # print("\n")


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

    

    # def quota(territory):
    #     name = territory.name
    #     qv = 1
    #     if name in my_frontier:
    #         qv = 5
    #     # staging / factory-adj tiles get medium quota (but frontier still dominates)
    #     if staging_score.get(name, 0) > 0 or factory_adj_score.get(name, 0) > 0:
    #         qv = max(qv, 3)
    #     return qv

    total_my_units = sum(count_defense_units(t) for t in my_territories)
    def quota(territory):
        name = territory.name
        
        if name == home_factory:
            base = 0.08  # always keep ~8% of army here
        elif name in my_frontier:
            # scale with enemy pressure on that tile
            enemy_threat = sum(
                count_defense_units(territories[n])
                for n in ctf.neighbors.get(name, [])
                if territories[n].owner != player
            )
            base_fraction = 0.05
            return max(3, min(enemy_threat + 2, int(total_my_units * 0.15)))
        elif staging_score.get(name, 0) > 0 or factory_adj_score.get(name, 0) > 0:
            base = 0.03
        elif name == "Flag":
            base = 0.02
        else:
            base = 0.01

        return max(1, int(total_my_units * base))
    

    def frontier_excess(name):
        my_strength = count_defense_units(territories[name])
        max_enemy_threat = max(
            (count_defense_units(territories[n])
            for n in ctf.neighbors.get(name, [])
            if territories[n].owner != player),
            default=0
        )
        # surplus beyond a safety buffer
        buffer = 2
        return max(0, my_strength - (max_enemy_threat + buffer))
    
    frontier_excess_map = {}
    for t in my_frontier:
        frontier_excess_map[t] = frontier_excess(t)

    # ---------- donors ----------
    # Don't drain frontier tiles, except allow draining home_factory (evacuation) specially below.
    donor_territories = []
    for t in my_territories:
        if count_defense_units(t) <= 0:
            continue
        if t.name in my_frontier and t.name != home_factory:
            if frontier_excess_map.get(t.name, 0) <= 0:
                continue
        donor_territories.append(t)

    # ---------- PASS 0: evacuate home factory before placement ----------
    # Keep a small garrison only if threatened.
    keep_min = 2 if has_enemy_neighbor(home_factory) else 0
    factory_terr = territories[home_factory]

    movable_from_factory = []
    for u in factory_terr.units:
        move_range = u.range
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
        
        donor_idx = 0
        # keep pushing units until target reaches quota or donors run out
        while count_defense_units(territories[terr_name]) < quota(terr):
            if donor_idx >= len(donor_territories):
                break
            donor = donor_territories[donor_idx]

            # for donor in donor_territories:
            if count_defense_units(donor) <= 0:
                donor_idx += 1
                continue

            if donor.name in my_frontier and frontier_excess_map.get(donor.name, 0) <= 0:
                donor_idx += 1
                continue
            if donor.name != home_factory and count_defense_units(donor) <= 0:
                donor_idx += 1
                continue

            # pick one unit from donor
            picked = None
            for u in donor.units:
                move_range = u.range
                if u.owner != player or u.quantity <= 0:
                    continue
                if u.unit_type == "factory" or move_range <= 0:
                    continue
                picked = u
                break

            if picked is None:
                donor_idx += 1
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
                donor_idx += 1
                continue

            move_seq.append({
                "delegate": "nonCombat",
                "from": donor.name,
                "to": dest,
                "units": picked.unit_type
            })

            # update deepcopy counts
            picked.quantity -= 1
            if donor.name in my_frontier:
                frontier_excess_map[donor.name] -= 1

                
    return move_seq


class MCTSGameState:
    """Compressed game state for MCTS"""
    def __init__(self, ctf):
        # Deep copy territories and their units
        self.territories = {}
        for name, territory in ctf.territories.items():
            # Create new Territory instance with copied data
            new_territory = move_generator_cpp.Territory()
            new_territory.name = territory.name
            new_territory.owner = territory.owner
            new_territory.units = []

            for unit in territory.units:
                # if unit.unit_type != "factory":
                cython_unit = move_generator_cpp.Unit()
                cython_unit.unit_type = unit.unit_type
                cython_unit.owner = unit.owner
                cython_unit.moved = unit.moved
                cython_unit.m_range = unit.range
                cython_unit.cost = unit.cost
                cython_unit.quantity = unit.quantity

                new_territory.add_unit(unit.unit_type, unit.owner, unit.quantity, unit.moved)
            

            
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
        # global cpp_adjacency
        # cpp_adjacency = {
        #     name: list(adjacency.neighbors(name))
        #     for name, _ in self.territories.items()
        # }
        # move_generator_cpp.set_adjacency(cpp_adjacency)
        # move_generator_cpp.set_dist_to_flag({t.name: t for t in self.territories.values()})
        self.set_terr_lists()
        # print("Round ", self.round)
        # for t in self.enemy_territories:
        #     print(t.name)
        

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
            for neighbor in cpp_adjacency.get(enemy_terr.name, []):
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
                1 for neighbor in cpp_adjacency.get(terr_name, [])
                if neighbor in victory_cities
            )
            priority_score += next_to_factory * 500
            
            # Production value
            priority_score += territory_production[terr_name] * 10
                        
            # Number of bordering friendly territories (easier to attack/hold)
            surrounded_by_me = sum(
                1 for neighbor in cpp_adjacency.get(terr_name, [])
                if self.territories[neighbor].owner == self.current_player
            )
            priority_score += surrounded_by_me * 50

            # distance to the victory cities? closer => better to attack

            enemy_neighbors = sum(1 for n in cpp_adjacency.get(terr_name, []) 
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

        has_factory = any(
            unit.unit_type == "factory" and unit.owner == player
            for terr in self.territories.values() if terr.owner == player
            for unit in terr.units
        )
        if not has_factory:
            return []

        units = [(name, data["cost"]) for name, data in game_rules.items()
                if name in {"infantry", "armour", "artillery"}]

        # Bias rotation based on round
        if self.round < 5:
            units = units + [(name, cost) for name, cost in units if name == "infantry"]
        elif self.round < 10:
            units = units + [(name, cost) for name, cost in units if name in {"infantry", "armour"}]
        elif self.round < 15:
            units = units + [(name, cost) for name, cost in units if name in {"armour", "artillery"}]
        units.sort(key=lambda x: x[1])

        purchase_dict = {}
        remaining = resources
        i = 0

        while True:
            affordable = [(n, c) for n, c in units if c <= remaining]
            if not affordable:
                break
            name, cost = affordable[i % len(affordable)]
            purchase_dict[name] = purchase_dict.get(name, 0) + 1
            remaining -= cost
            i += 1

        if not purchase_dict:
            return []

        attacks = [
            Attack(unit=Unit(name, player, 1), from_territory=None, quantity=count)
            for name, count in purchase_dict.items()
        ]

        return [Move(delegate="purchase", moves=attacks, strength=resources - remaining)]


    def heuristic_combat_legal_moves(self, time_budget):
        player = self.current_player
        self.actions = []
        self.actionIndex = 0
        start = time.time()

        # territories = {}
        self.set_terr_lists()
        my_territories = set(t.name for t in self.my_territories)
        enemy_territories = set(t.name for t in self.enemy_territories)
        # for territory_name, territory in self.territories.items():
        #     if territory.owner == player:
        #         my_territories.add(territory_name)
        #     else:
        #         enemy_territories.add(territory_name)

        # time_left = time_budget - (time.time() - start)
        # print(f"In round {self.round}")
        results = move_generator_cpp.heuristic_combat_legal_moves(
            player = self.current_player,
            territories = self.territories,
            my_territory_names = my_territories,
            enemy_territory_names = enemy_territories,
            excluded = self.excluded,
            time_budget = 0.001 # based on profiling info on median value
        )
        actions, self.excluded = results
        if actions != None and actions != []:
            # random.shuffle(actions)
            self.actions = actions
        else:
            self.actions.append(Move(delegate="combat", end_phase=True, strength=0))



    def heuristic_non_combat_legal_moves(self, time_budget):
        # my_territory_names = {t.name for t in self.my_territories}
        # enemy_territory_names = {t.name for t in self.enemy_territories}

        results = move_generator_cpp.heuristic_non_combat_legal_moves(
            self, FACTORY_MAP, 0.01
        )
        actions = results
        if actions != None and actions != []:
            grouped_moves = {}
            for action in actions:
                key = (action.to_terr, action.moves[0].from_territory, action.moves[0].unit.unit_type)
                if key not in grouped_moves:
                    grouped_moves[key] = action
                else:
                    grouped_moves[key].moves[0].quantity += action.moves[0].quantity
            # print(f"Non combat in R{self.round}: {list(grouped_moves.values())}")
            return list(grouped_moves.values())     
        else:
            return []

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
                move_generator_cpp.invalidate_reachability_for_territory(to)
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
        self.untried_actions = None 
        self.visits = 0
        self.value = 0.0
        self.avg_playout_depth = 0
        self.is_state_terminal = None
        self.tree_level = 0 # number of edges from the root before this node
        if parent:
            self.tree_level = parent.tree_level + 1

    def is_fully_expanded(self):
        return self.untried_actions is not None and len(self.untried_actions) == 0
    
    def is_terminal(self):
        if self.is_state_terminal is None:
            self.is_state_terminal = self.state.is_terminal()
        return self.is_state_terminal

    def best_child_uct(self, c_param=1.414):
        # in case there is still an unvisited child, prioritize it to ensure exploration
        unvisited = [child for child in self.children if child.visits == 0]
        if unvisited:
            return random.choice(unvisited)

        bestNode = None
        choices_weights = [
            (child.value / child.visits) + c_param * math.sqrt(2 * math.log(self.visits) / child.visits)
            for child in self.children
        ]
        # print(f"UCT values: {choices_weights}")
        if choices_weights != []:
            bestNode = self.children[choices_weights.index(max(choices_weights))]

        # bestNode = max(self.children,
        #    key=lambda c: (c.value / max(1, c.visits), c.visits))

        return bestNode


class MCTS:
    def __init__(self, model_name, efficiency_file, quality_file, rollout_file, tree_info, production_rules, terr_production, vic_cities, adj, order, territories, gamma=0.99, alpha=1e-3, epsilon=0.2, epsilon_decay=0.99995):
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.latest_legal_moves = []
        self.whoAmI = None
        
        # MCTS parameters
        self.time_budget = 1.0  # seconds per move
        self.iter_budget = 1000
        self.depth_budget = 2  # Maximum playout depth
        self.exploration_constant = 0  # UCB1 exploration parameter for non exploring mcts

        self.model_name = model_name
        # file paths to store metrics
        self.efficiency_metric = MetricLogger(
            efficiency_file,
            header=["game", "round", "num_iterations", "max_depth", "avg_depth", "time_taken", "num_children", "value"]
        )

        self.combat_quality = MetricLogger(
            quality_file,
            header=["game", "round", "pu_after", "territories_after"]
        )

        self.rollout_efficiency = MetricLogger(
            rollout_file,
            header=["game", "round", "iteration", "depth", "current_player", "terr_attacked_in_round (actions taken)"]
        )

        self.tree_info = MetricLogger(
            tree_info,
            header=["game", "round", "node_id", "parent_id", "n_legal", "tree_level", "val", "vis", "avg"]
        )

        self.rewards = MetricLogger(
            "mcts_heuristic_v2/metrics/rewards.csv",
            header=["game", "round", "depth_reached", "tree_depth", "is_terminal", "reward"]
        )

        global game_rules, territory_production, victory_cities, adjacency, turn_order
        # print(production_rules)
        game_rules = production_rules
        territory_production = terr_production
        victory_cities = vic_cities
        adjacency = adj
        turn_order = order

        global unit_move_ranges, unit_attack_points, unit_defense_points, unit_costs

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

        global cpp_adjacency
        cpp_adjacency = {
            name: list(adjacency.neighbors(name))
            for name, _ in territories.items()
        }
        move_generator_cpp.set_adjacency(cpp_adjacency)
        move_generator_cpp.set_dist_to_flag({t.name: t for t in territories.values()})

    def update_whoAmI(self, whoAmI):
        self.whoAmI = whoAmI

    def get_move(self, line, ctf, game_round):
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
                        # max_cost = max(move["cost"] for move in legal_moves)
                        # best_moves = [move for move in legal_moves if move["cost"] == max_cost]
                        move = legal_moves[0]
                        response = convert_purchase_to_json(move)
                    else:
                        response = []
                    # response = []
                elif move_type == "combat":
                    current_state = MCTSGameState(ctf)

                    # img_file = f"{self.model_name}/combat_moves/graph_{ctf.game_num}_{game_round}.png"
                    # ctf.fig.savefig(img_file, dpi=300, bbox_inches="tight")

                    profile_name = f"{self.model_name}/profiles/mcts_{ctf.game_num}_"
                    if int(game_round) < 10:
                        profile_name += "0"
                    profile_name += game_round + ".prof"
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



    def expand(self, node):
        # print(node.state.actions)
        action = node.state.getNextAction()
        # print(f"\tSelected: {action}")
        if action == None or action.end_phase == True:
            node.untried_actions = []
            # value, depth = self.simulate(node.state)
            return node
        else:
            new_state = node.state.clone()
            new_state.apply_combat_move([action])
            time_left = 0.01
            new_state.heuristic_combat_legal_moves(time_left)
            child = MCTSNode(new_state, parent=node, action=action)
            node.children.append(child)
            return child


    def pick_rollout_move(self, actions, whoAmI, cur_player, min_attacks_done, topk=3, epsilon=0.10):
        real = [a for a in actions if not getattr(a, "end_phase", False)]
        real_no_skips = [a for a in actions if (not getattr(a, "end_phase", False)) and getattr(a, "moves", None)]
        endp = [a for a in actions if getattr(a, "end_phase", False)]

        candidates = real_no_skips if real_no_skips else real
        if not candidates:
            return endp[0] if endp else actions[0]

        capital_moves = [a for a in candidates if a.to_terr in victory_cities]
        if capital_moves:
            # among capital-capturing moves, take the strongest one (highest strength)
            return max(capital_moves, key=lambda a: a.strength)

        def score(a):
            # crude proxy: prefer higher strength attacks, and attacks that move toward victory_cities
            proximity_bonus = 1.0 if a.to_terr in victory_cities else 0.0
            return a.strength + proximity_bonus

        ranked = sorted(candidates, key=score, reverse=True)
        # ranked = candidates
        k = min(topk, len(ranked))

        if random.random() < epsilon:
            return random.choice(ranked[:k])
        return ranked[0]


    def simulate(self, state, actions_before_this_state, debug=False):
        current_state = state.clone()
        depth = 0  
        if debug:
            snapshots = []
            template = CaptureTheFlag.template
            template_data = {
                "edges": list(template.G.edges()),
                "pos": dict(template.pos),
                "nodes": list(template.G.nodes()),
            } if template is not None else None

            snapshots.append({
                        "game_num": state.game_num,
                        "round": state.round,
                        "iter": self.iteration,
                        "depth": depth,
                        "current_player": current_state.current_player,
                        "territories": {
                            k: {
                                "owner": t.owner,
                                "units": [{"quantity": u.quantity, "unit_type": u.unit_type, "owner": u.owner} 
                                        for u in t.units]
                            }
                            for k, t in current_state.territories.items()
                        }
                    })
    
        try:
            # Simulate future rounds
            # time_left = self.time_budget - time_done
            # start = time.time()
            
            first_sim = True
            while depth < self.depth_budget and not current_state.is_terminal():
                # print(f"--- Simulation depth {depth}, player {current_state.current_player} ---")
                start_idx = turn_order.index(state.current_player)
                end_of_cycle = (start_idx - 1) % len(turn_order)
                idx = start_idx
                current_state.reset_moved_flags()   # reset moved status at the start of the round for all units
                while True:
                    current_state.current_player = turn_order[idx]
                    # print(f"Rollout - player: {current_state.current_player}")
                    if not first_sim:       # since the first sim would have already have atleast 1 terr in the excluded set, and the action would be execute in the expand phase
                        # do purchase
                        # print(f"Purchase phase for {current_state.current_player} at depth {depth}")
                        purchase_move = current_state.purchase_legal_moves()
                        if purchase_move != []:
                            current_state.apply_purchase_move(purchase_move[0])
                        current_state.excluded = set()
                        current_state.set_terr_lists()

                    # print(f"\n\texcluded: {current_state.excluded}, \n\tmy terr: {[t.name for t in current_state.my_territories]}, \n\tenemy terr: {[t.name for t in current_state.enemy_territories]}")
                    move_seq = []
                    while True:
                        current_state.heuristic_combat_legal_moves(0.01)
                        # actions successfully generated for the most important enemy territory
                        if current_state.actions:
                            mv = self.pick_rollout_move(current_state.actions, self.whoAmI, current_state.current_player, len(move_seq), topk=3)

                            if mv.end_phase == True:
                                break
                            if mv.moves is not None:     # count only real attacks
                                move_seq.append(mv)

                            current_state.apply_combat_move([mv])
                    if first_sim:
                        self.rollout_efficiency.buffer(state.game_num, state.round, self.iteration, depth, current_state.current_player, len(move_seq)+actions_before_this_state)
                    else:
                        self.rollout_efficiency.buffer(state.game_num, state.round, self.iteration, depth, current_state.current_player, len(move_seq))
                    if debug:
                        print(f" R{state.round} iter{self.iteration} d{depth} Combat move by {current_state.current_player}: {move_seq}\n")
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
                    
                    if current_state.is_terminal():
                        depth += 1
                        break
                    
                    # Round increments only after last player in the order finishes
                    if idx == end_of_cycle:
                        depth += 1

                        # if depth cap reached, break out early
                        if depth >= self.depth_budget:
                            break

                    idx = (idx + 1) % len(turn_order)
                    if idx == start_idx:
                        break

                if debug:
                    snapshots.append({
                        "game_num": state.game_num,
                        "round": state.round,
                        "iter": self.iteration,
                        "depth": depth,
                        "current_player": current_state.current_player,
                        "territories": {
                            k: {
                                "owner": t.owner,
                                "units": [{"quantity": u.quantity, "unit_type": u.unit_type, "owner": u.owner} 
                                        for u in t.units]
                            }
                            for k, t in current_state.territories.items()
                        }
                    })

        except Exception as e:
            print(f"Error in simulation: {e}")
            return -0.5, depth
        
        # Evaluate final state
        reward, is_terminal = move_generator_cpp.evaluate_state(
            current_state.territories, current_state.players, self.whoAmI,
            list(victory_cities), depth, self.depth_budget, state.round
        )
        if debug:
            snap_path = f"{self.model_name}/snapshots/g{state.game_num}_r{state.round}_iter{self.iteration}.pkl"
            os.makedirs(os.path.dirname(snap_path), exist_ok=True)
            with open(snap_path, "wb") as f:
                pickle.dump({
                    "template": template_data,
                    "snapshots": snapshots
                }, f)
            print(f"== Reward R{state.round} iter{self.iteration}  completed d{depth} {reward} reached terminal? {is_terminal}")
            self.rewards.log(state.game_num, state.round, depth, actions_before_this_state, is_terminal, reward)
        return reward, depth
        # return self.evaluate_state(current_state, depth), depth
    
    def backpropagate(self, node, reward):
        while node is not None:
            node.visits += 1
            node.value += reward
            node = node.parent


    def mcts_search(self, initial_state, file):
        initial_state.heuristic_combat_legal_moves(0.01)

        root = MCTSNode(initial_state)
        root.tree_level = 0
                
        start_time = 0
        end_time = 0
        avg_depth = 0
        import cProfile
        with cProfile.Profile() as pr:
            self.iteration = 0
            self.max_depth = 0
            start_time = time.time()
            while time.time() - start_time < self.time_budget:
            # ideally want to get iteration budget, but if it takes too long then stop 
            # while self.iteration < self.iter_budget:
                self.iteration += 1
                # print(self.iteration)
                # --- Selection: walk down until leaf or terminal ---
                node = root
                while node.is_fully_expanded() and not node.is_terminal():
                    best = node.best_child_uct(self.exploration_constant)
                    # print(f"== Iteration {self.iteration}, visiting node with action: {node.action}, visits: {node.visits}, value: {node.value}")
                    if best is None:
                        break
                    node = best

                # --- Expand or evaluate terminal ---
                if node.is_terminal():
                    value, depth = self.simulate(node.state, node.tree_level, False)  # or use known outcome
                else:
                    node = self.expand(node)   # expand leaf
                    value, depth = self.simulate(node.state, node.tree_level, False)  # rollout from new child
                self.max_depth = max(self.max_depth, depth)
                avg_depth = avg_depth + depth
                # --- Backprop always ---
                self.backpropagate(node, value)

            end_time = time.time()
        pr.dump_stats(file)

        # print("Selecting combat")
        avg_depth = avg_depth / max(1, self.iteration)
        game_num = root.state.game_num
        game_round = root.state.round
        # if game_num == 1 or game_num % 10 == 0:
        # tree_prefix = f"{self.model_name}/trees/tree_g{game_num}_r{game_round}"
        # os.makedirs(os.path.dirname(tree_prefix), exist_ok=True)
        # dot_file, png_file = save_mcts_tree_png(root, self.tree_info, tree_prefix, max_nodes=500, render_img=True)
        # print("Saved tree:", dot_file, png_file)

        # print(f"MCTS completed {self.iteration} iterations in {round(end_time - start_time, 2)} seconds. Max depth reached: {self.max_depth}")

        action_seq = []
        node = root
        depth = 0
        # print(f"Round {root.state.round}")
        while node.children != []:
            best_child = max(node.children, key=lambda c: c.visits)
            if best_child is None:
                break
            if best_child.action.moves is not None and best_child.action.end_phase == False and best_child.action.strength != 0:
                action_seq.append(best_child.action)
            if best_child.action.end_phase == True:
                break
            node = best_child
            depth += 1
            # print(f"Moved = {node.state.how_many_moved()}")

        avg_value = "undefined" if root.visits == 0 else root.value / root.visits
        time_taken = round(end_time - start_time, 2)
        self.efficiency_metric.buffer(game_num, game_round, self.iteration, self.max_depth, avg_depth, time_taken, len(root.children), avg_value)

        
        return action_seq

    
    def profile_mcts(self, initial_state, file):
        # import cProfile
        # with cProfile.Profile() as pr:
        result = self.mcts_search(initial_state, file)
        # pr.dump_stats(file)
        return result


    def evaluate_state(self, state, depth):
        if state.is_terminal():
            if state.am_i_winner(self.whoAmI):
                return 0.6 + 0.4 * (self.depth_budget - depth) / self.depth_budget 
            else:
                return -0.6 - 0.4 * (self.depth_budget - depth) / self.depth_budget

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
                    cost = u.cost
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
        score += 0.30 * terr_term
        score += 0.20 * vc_term
        score += 0.50 * tuv_term

        return max(-0.5, min(0.5, score))


    def on_game_end(self):
        self.efficiency_metric.flush()
        self.combat_quality.flush()
        self.rollout_efficiency.flush()
        self.tree_info.flush()

    