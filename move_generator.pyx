# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

import time
from collections import deque
import copy
import math

# =========================
# Global configuration
# =========================

# cdef dict _adjacency = {}
cdef dict unit_attack_values = {}
cdef dict unit_defense_values = {}
cdef dict unit_move_ranges = {}
cdef dict unit_costs = {}
cdef list _victory_cities = []

cdef dict _reachability_cache = {}

cdef dict _adjacency = {}
cdef dict _neighbors_within_2 = {}   # terr → set of all terrs within 2 hops
cdef dict dist_to_flag = {}
cdef set flagged_territories = set()

def set_adjacency(dict adj):
    global _adjacency, _neighbors_within_2, flagged_territories
    _adjacency = adj
    # precompute all territories within 2 hops (max move range you use)
    # used for selective cache invalidation
    for start in adj:
        within = set()
        for n1 in adj.get(start, []):
            within.add(n1)
            for n2 in adj.get(n1, []):
                within.add(n2)
        within.discard(start)
        _neighbors_within_2[start] = within
        if start == "Flag":
            flagged_territories.add(start)

def set_dist_to_flag(dict territories):
    global dist_to_flag
    dist_to_flag = _bfs_dist_to_frontier(flagged_territories, territories)
    # print("dist_to_flag:", dist_to_flag)

def set_unit_attack_values(dict values):
    global unit_attack_values
    unit_attack_values = values

def set_unit_defense_values(dict values):
    global unit_defense_values
    unit_defense_values = values

def set_unit_move_ranges(dict ranges):
    global unit_move_ranges
    unit_move_ranges = ranges

def set_unit_costs(dict costs):
    global unit_costs
    unit_costs = costs

def set_victory_cities(list cities):
    global _victory_cities
    _victory_cities = cities

# =========================
# Python-visible classes
# =========================

cdef class Unit:
    cdef public str unit_type
    cdef public str owner
    cdef public int quantity
    cdef public bint moved
    cdef public int m_range
    cdef public int cost
    cdef public int qty_moved

    def __init__(self, str unit_type="", str owner="", int quantity=1, bint moved=False, int qty_moved=0):
        self.unit_type = unit_type
        self.owner = owner
        self.quantity = quantity
        self.moved = moved
        self.m_range = unit_move_ranges.get(unit_type, 1)
        self.cost = unit_costs.get(unit_type, 0)
        self.qty_moved = qty_moved


cdef class Territory:
    cdef public str name
    cdef public str owner
    cdef public list units   # list[Unit]

    def __init__(self, str name="", str owner="", units=None):
        self.name = name
        self.owner = owner
        self.units = units if units is not None else []

    def fast_clone(self):
        c = Territory.__new__(Territory)
        c.name = self.name
        c.owner = self.owner
        c.units = []
        for u in self.units:
            c.units.append(Unit(u.unit_type, u.owner, u.quantity, u.moved, u.qty_moved))
        return c

    def add_unit(self, str unit_type="", str owner="", int quantity=1, bint moved=False, int qty_moved=0):
        for u in self.units:
            if u.unit_type == unit_type and u.owner == owner:
                u.quantity += quantity
                u.moved = moved
                u.qty_moved += qty_moved
                break
        else:
            self.units.append(Unit(unit_type, owner, quantity, moved, qty_moved))
        
    def remove_unit(self, str unit_type="", str owner="", int quantity=1):
        for u in self.units:
            if u.unit_type == unit_type and u.owner == owner:
                u.quantity -= quantity
                if u.quantity <= 0:
                    self.units.remove(u)
                break


cdef class UnitInfo:
    cdef public str from_territory
    cdef public Unit unit
    cdef public int quantity

    def __init__(self, str from_territory="", Unit unit=None, int quantity=0):
        self.from_territory = from_territory
        self.unit = unit if unit is not None else Unit()
        self.quantity = quantity


cdef class Attack:
    cdef public Unit unit
    cdef public str from_territory
    cdef public int quantity

    def __init__(self, Unit unit=None, str from_territory="", int quantity=0):
        self.unit = unit
        self.from_territory = from_territory
        self.quantity = quantity


cdef class Move:
    cdef public str delegate
    cdef public str to_terr
    cdef public list moves      # list[Attack]
    cdef public bint end_phase
    cdef public int strength

    def __init__(
        self,
        str delegate="combat",
        str to_terr=None,
        list moves=None,
        bint end_phase=False,
        int strength=0
    ):
        self.delegate = delegate
        self.to_terr = to_terr
        self.moves = moves if moves is not None else []
        self.end_phase = end_phase
        self.strength = strength

    def __repr__(self):
        if self.end_phase:
            return f"\n{self.delegate} delegate: END PHASE"
        lines = [f"\n{self.delegate} delegate on {self.to_terr}"]
        for m in self.moves:
            lines.append(f"\t{m.quantity}x {m.unit.unit_type} from {m.from_territory}")
        lines.append(f"\tstrength={self.strength}")
        return "\n".join(lines)





# =========================
# Reachability (BFS)
# =========================

def invalidate_reachability_for_territory(str changed_terr):
    """
    Call this after a territory changes owner.
    Removes cache entries whose BFS paths may have passed through changed_terr.
    Only entries where from_terr is within move_range hops of changed_terr
    could possibly be affected.
    """
    global _reachability_cache, _neighbors_within_2
    cdef set affected = _neighbors_within_2.get(changed_terr, set())
    cdef list to_delete = []
    cdef tuple key

    for key in _reachability_cache:
        from_terr, move_range = key
        # from_terr itself changed, or it's close enough that changed_terr
        # was a potential waypoint
        if from_terr == changed_terr or from_terr in affected:
            to_delete.append(key)

    for key in to_delete:
        del _reachability_cache[key]


cdef bint can_reach(
    str start,
    str target,
    int move_range,
    Unit unit,
    dict territories,
    set my_territories
):
    cdef list queue = [(start, 0)]
    cdef set visited = {start}
    if move_range <= 0 or unit.unit_type == "factory":
        return False

    while queue:
        current, dist = queue.pop(0)

        if dist >= move_range:
            continue

        for neighbor in _adjacency.get(current, []):
            if neighbor in visited:
                continue

            terr_owner = territories[neighbor].owner
            if neighbor == target:
                return True
  
            if terr_owner != unit.owner:
                continue  # Can't pass through enemy territory

            visited.add(neighbor)
            
            if dist + 1 < move_range:
                queue.append((neighbor, dist + 1))

    return False

cdef bint can_reach_cache_helper(
    str start,
    str target,
    int move_range,
    str player,
    dict territories,
    set my_territories
):
    cdef list queue = [(start, 0)]
    cdef set visited = {start}
    if move_range <= 0:
        return False

    while queue:
        current, dist = queue.pop(0)

        if dist >= move_range:
            continue

        for neighbor in _adjacency.get(current, []):
            if neighbor in visited:
                continue

            terr_owner = territories[neighbor].owner
            if neighbor == target:
                return True
  
            if terr_owner != player:
                continue  # Can't pass through enemy territory

            visited.add(neighbor)
            
            if dist + 1 < move_range:
                queue.append((neighbor, dist + 1))

    return False

cdef list build_reachability(
        set my_territory_names, 
        set enemy_territory_names,
        str player, 
        dict territories):
    global _reachability_cache
    cdef list move_ranges = [1,2]
    for terr in my_territory_names:
        for m in move_ranges:
            reachable = frozenset(
                target for target in enemy_territory_names
                if can_reach_cache_helper(terr, target, m, player, territories, my_territory_names)
            )
            _reachability_cache[(terr, m)] = reachable


cdef list get_reachable_units(
    str target,
    str player,
    dict territories,
    set my_territories
):
    cdef list reachable = []
    global _reachability_cache

    for from_terr_name in my_territories:
        terr = territories[from_terr_name]
        for unit in terr.units:
            if unit.owner != player:
                continue
            if unit.unit_type == "aaGun" or unit.unit_type == "factory":
                continue
            if unit.moved == True:
                continue

            
            move_range = unit_move_ranges.get(unit.unit_type, 1)
            key = (from_terr_name, move_range)

            if key not in _reachability_cache:
                # lazy build for just this (terr, move_range) pair
                _reachability_cache[key] = frozenset(
                    t for t in territories
                    if t != from_terr_name and
                    can_reach_cache_helper(from_terr_name, t, move_range, player, territories, my_territories)
                )

            if target in _reachability_cache.get(key, frozenset()):
                reachable.append(UnitInfo(from_terr_name, unit, unit.quantity))

            # if target in _reachability_cache.get(key, frozenset()):
            #     info = UnitInfo(from_terr_name, unit, unit.quantity)
            #     reachable.append(info)


    return reachable


# =========================
# Donor scoring (mirrors donor_score in heuristic_combat_legal_moves)
# =========================

cdef float donor_score(
    UnitInfo info,
    str target,
    str player,
    dict territories,
):
    cdef float score = 0.0
    cdef str n

    # adjacent to target → prefer
    if target in _adjacency.get(info.from_territory, []):
        score += 100.0

    # attack power
    score += 10.0 * unit_attack_values.get(info.unit.unit_type, 1)

    # is border territory → penalise (draining frontier is costly)
    for n in _adjacency.get(info.from_territory, []):
        if territories[n].owner != player:
            score -= 30.0
            break

    return score


# =========================
# Attack strength (with artillery support bonus)
# =========================

cdef int calculate_attack_strength(list unit_infos):
    """
    Mirrors calculate_attack_strength in MCTSGameState.
    Infantry supported 1:1 by artillery gets +1 attack.
    """
    cdef int infantry = 0
    cdef int artillery = 0
    cdef int strength = 0
    cdef int supported_inf, unsupported_inf, power
    for info in unit_infos:
        if info.unit.unit_type == "infantry":
            infantry += info.quantity
        elif info.unit.unit_type == "artillery":
            artillery += info.quantity

    supported_inf   = min(infantry, artillery)
    unsupported_inf = infantry - supported_inf

    for info in unit_infos:
        power = unit_attack_values.get(info.unit.unit_type, 1)
        if info.unit.unit_type == "infantry":
            strength += supported_inf * (power + 1)
            strength += unsupported_inf * power
        else:
            strength += info.quantity * power
    return strength


cdef int defender_strength(Territory terr, str player):
    """Total defense strength of enemy units on a territory."""
    cdef int strength = 0
    for unit in terr.units:
        if unit.owner != player and unit.unit_type != "factory":
            strength += unit_defense_values.get(unit.unit_type, 1) * unit.quantity
    return strength


# =========================
# Form attacks (group by from+unit_type, mirrors form_attacks)
# =========================

cdef list form_attacks(list unit_infos):
    """Group UnitInfo list into Attack objects, same from+unit_type merged."""
    cdef dict grouped = {}
    cdef tuple key

    for info in unit_infos:
        key = (info.from_territory, info.unit.unit_type)
        if key not in grouped:
            grouped[key] = Attack(info.unit, info.from_territory, 0)
        grouped[key].quantity += info.quantity

    return list(grouped.values())




def heuristic_combat_legal_moves(
    str player,
    dict territories,
    set my_territory_names,
    set enemy_territory_names,
    set excluded,
    float time_budget,
):
    cdef list actions = []
    cdef double start = time.time()
    cdef float strengthThreshold, maxThreshold, strengthThreshold_weak
    cdef int def_strength, currentStrength
    cdef list reachable, sorted_reachable
    cdef list unitsUpToStrength, sets, weak_sets
    cdef list attacks

    # global _reachability_cache
    # _reachability_cache.clear()
    # build_reachability(my_territory_names, enemy_territory_names, player, territories)
    # print(_reachability_cache)
    for enemy_territory_name in enemy_territory_names:
        if enemy_territory_name not in excluded:
            # ── gather attackers ──────────────────────────────────────────────
            reachable = get_reachable_units(enemy_territory_name, player, territories, my_territory_names)

            if time.time() - start > time_budget:
                break

            if not reachable:
                excluded.add(enemy_territory_name)
                continue

            # ── sort by donor_score (desc) ────────────────────────────────────
            sorted_reachable = sorted(
                reachable,
                key=lambda info: donor_score(info, enemy_territory_name, player, territories),
                reverse=True,
            )

            # ── defender strength ─────────────────────────────────────────────
            def_strength = defender_strength(territories[enemy_territory_name], player)

            # ── undefended: cheapest single unit capture ──────────────────────
            

            # ── incremental buildup ───────────────────────────────────────────
            strengthThreshold = 1.5
            maxThreshold      = 3.5
            sets              = []
            unitsUpToStrength = []
            
            all_units = []
            for info in sorted_reachable:
                for _ in range(info.quantity):
                    all_units.append(UnitInfo(info.from_territory, info.unit, 1))
                    # if calculate_attack_strength(all_units) >= (maxThreshold * def_strength) + 4:
                    #     break
                else:
                    continue
                break

            sets = []
            unitsUpToStrength = []
            strengthThreshold = 1.5

            for unit_info in all_units:
                unitsUpToStrength.append(unit_info)
                currentStrength = calculate_attack_strength(unitsUpToStrength)
                if (currentStrength > strengthThreshold * def_strength and
                        currentStrength < (maxThreshold * def_strength) + 4):
                    sets.append((form_attacks(unitsUpToStrength[:]), currentStrength))
                    strengthThreshold += 0.1

            # always include full force if it beats defender
            if all_units:
                currentStrength = calculate_attack_strength(all_units)
                if currentStrength > def_strength:
                    attacks = form_attacks(all_units)
                    if sets:
                        l = len(sets)
                        if sets[l-1][1] != currentStrength:
                            sets.append((attacks, currentStrength))
                    else:
                        sets.append((attacks, currentStrength))

            if time.time() - start > time_budget:
                if sets:
                    sets.reverse()
                    for atk_list, s in sets:
                        actions.append(Move(
                            delegate="combat",
                            to_terr=enemy_territory_name,
                            moves=atk_list,
                            strength=s,
                        ))

                    # skip move always included
                    actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[], strength=0))
                    excluded.add(enemy_territory_name)
                break

            # ── weak sets fallback ────────────────────────────────────────────
            # if not sets:
            #     weak_sets             = []
            #     unitsUpToStrength     = []
            #     strengthThreshold_weak = 0.75

            #     for info in sorted_reachable:
            #         for _ in range(info.quantity):
            #             unitsUpToStrength.append(UnitInfo(info.from_territory, info.unit, 1))
            #             currentStrength = calculate_attack_strength(unitsUpToStrength)

            #             if (currentStrength > strengthThreshold_weak * def_strength and
            #                     currentStrength <= def_strength):
            #                 attacks = form_attacks(unitsUpToStrength)
            #                 weak_sets.append((attacks, currentStrength))
            #                strengthThreshold_weak += 0.15
            #                if len(weak_sets) >= 3:
            #                    break
            #        if len(weak_sets) >= 3:
            #            break

            #    sets.extend(weak_sets)

            if time.time() - start > time_budget:
                if sets:
                    sets.reverse()
                    for atk_list, s in sets:
                        actions.append(Move(
                            delegate="combat",
                            to_terr=enemy_territory_name,
                            moves=atk_list,
                            strength=s,
                        ))

                    # skip move always included
                    actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[], strength=0))
                    excluded.add(enemy_territory_name)
                break

            # -- fallback
            if not sets:
                if def_strength == 0:
                    best = min(sorted_reachable, key=lambda x: unit_costs.get(x.unit.unit_type, 9999))
                    atk_list = form_attacks([UnitInfo(best.from_territory, best.unit, 1)])
                    s = calculate_attack_strength([UnitInfo(best.from_territory, best.unit, 1)])
                    actions.append(Move(
                        delegate="combat",
                        to_terr=enemy_territory_name,
                        moves=atk_list,
                        strength=s,
                    ))
                    # actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[], strength=0))
                    # excluded.add(enemy_territory_name)
                    # return actions, excluded

            # ── append moves (strongest first) ───────────────────────────────
            sets.reverse()
            for atk_list, s in sets:
                actions.append(Move(
                    delegate="combat",
                    to_terr=enemy_territory_name,
                    moves=atk_list,
                    strength=s,
                ))

            # skip move always included
            actions.append(Move(delegate="combat", to_terr=enemy_territory_name, moves=[], strength=0))
            excluded.add(enemy_territory_name)
            break
    return actions, excluded



cdef int _count_defense_units(Territory terr):
    cdef int total = 0
    cdef Unit u
    for u in terr.units:
        if u.unit_type != "factory":
            total += u.quantity
    return total



cdef dict _bfs_dist_to_frontier(set frontier, dict territories):
    """Multi-source BFS over all territory keys; returns dist dict."""
    cdef dict dist = {name: <int>2147483647 for name in territories}   # "inf"
    cdef object q = deque()
    cdef str cur, nb
    cdef int d

    for f in frontier:
        dist[f] = 0
        q.append(f)

    while q:
        cur = q.popleft()
        d   = dist[cur]
        for nb in _adjacency.get(cur, []):
            if dist[nb] > d + 1:
                dist[nb] = d + 1
                q.append(nb)

    return dist


cdef int _territory_priority(
    str name,
    set my_frontier_territories,
    dict territories,
    dict staging_score,
    dict factory_adj_score,
):
    cdef int score = 0
    cdef Territory t

    if name in my_frontier_territories:
        score += 1000
        t = territories[name]
        if _count_defense_units(t) == 0:
            score += 500

    score += staging_score.get(name, 0) * 200
    score += factory_adj_score.get(name, 0) * 100
    return score


cdef tuple _best_step_toward_frontier(
    object game_state,      # MoveGenerator / MCTSGameState instance
    Unit unit,
    str from_name,
    list targets,
    dict dist_to_frontier,
    set my_frontier_territories,
    dict staging_score,
    dict factory_adj_score,
):
    cdef str dest_name
    cdef int from_d, to_d, improvement, score
    cdef int best_score = -2147483647
    cdef object best = None
    global _reachability_cache


    from_d = dist_to_frontier.get(from_name, <int>2147483647)

    for dest in targets:
        dest_name = dest.name
        if dest_name == from_name:
            continue
        move_range = unit_move_ranges.get(unit.unit_type, 1)


        key = (from_name, move_range)

        if key not in _reachability_cache:
            # lazy build for just this (terr, move_range) pair
            _reachability_cache[key] = frozenset(
                t for t in game_state.territories
                if t != from_name and
                can_reach_cache_helper(from_name, t, move_range, game_state.current_player, game_state.territories, set(game_state.my_territories))
            )

        if dest_name not in _reachability_cache.get(key, frozenset()):
            continue


        to_d        = dist_to_frontier.get(dest_name, <int>2147483647)
        improvement = from_d - to_d          # positive = closer to frontier

        score = improvement * 100
        if dest_name in my_frontier_territories:
            score += 50
        score += staging_score.get(dest_name, 0) * 10
        score += factory_adj_score.get(dest_name, 0) * 5

        if score > best_score:
            best_score = score
            best       = dest_name

    return best, best_score


cdef int _frontier_excess(str name, dict territories, str player, int buffer=2):
    cdef int my_strength = _count_defense_units(territories[name])
    cdef int max_enemy_threat = 0
    cdef int threat
    for nb in _adjacency.get(name, []):
        if territories[nb].owner != player:
            threat = _count_defense_units(territories[nb])
            if threat > max_enemy_threat:
                max_enemy_threat = threat
    cdef int excess = my_strength - (max_enemy_threat + buffer)
    return excess if excess > 0 else 0


cdef int _quota(
    str name,
    set my_frontier_territories,
    dict staging_score,
    dict factory_adj_score,
    str home_factory,
    dict territories,
    str player,
    int total_my_units,
):
    cdef int enemy_threat, base

    if name == home_factory:
        return max(1, int(total_my_units * 0.08))

    if name in my_frontier_territories:
        enemy_threat = sum(
            _count_defense_units(territories[nb])
            for nb in _adjacency.get(name, [])
            if territories[nb].owner != player
        )
        return max(3, min(enemy_threat + 2, int(total_my_units * 0.15)))

    if staging_score.get(name, 0) > 0 or factory_adj_score.get(name, 0) > 0:
        return max(1, int(total_my_units * 0.03))

    return max(1, int(total_my_units * 0.01))

cdef bint _has_enemy_neighbor(str name, dict territories, str player, dict FACTORY_MAP):
    for n in _adjacency.get(name, []):
        if territories[n].owner != player and n not in FACTORY_MAP.values():
            return True
    return False

# =========================
# qty-snapshot helpers
# =========================

cdef int _count_defense_units_snap(str terr_name, dict qty_snap):
    """Read unit count from snapshot instead of Territory object."""
    cdef int total = 0
    cdef dict units = qty_snap.get(terr_name, {})
    for key, qty in units.items():
        if key[0] != "factory":   # key = (unit_type, owner)
            total += qty
    return total


cdef int _frontier_excess_snap(
    str name,
    dict qty_snap,
    dict territories,
    str player,
    int buffer=2,
):
    cdef int my_strength = _count_defense_units_snap(name, qty_snap)
    cdef int max_enemy_threat = 0
    cdef int threat
    for nb in _adjacency.get(name, []):
        if territories[nb].owner != player:
            threat = _count_defense_units_snap(nb, qty_snap)
            if threat > max_enemy_threat:
                max_enemy_threat = threat
    cdef int excess = my_strength - (max_enemy_threat + buffer)
    return excess if excess > 0 else 0


# =========================
# Rewritten non-combat move gen
# =========================

def heuristic_non_combat_legal_moves(object game_state, dict FACTORY_MAP, float time_budget):
    cdef dict   territories  = game_state.territories   # NO copy — read-only
    cdef list   my_territories = game_state.my_territories  # NO copy — read-only
    cdef str    player       = game_state.current_player
    cdef list   move_seq     = []
    cdef str    n, terr_name, dest, step, home_factory
    cdef Territory terr
    cdef Unit   u, picked
    cdef int    move_range, sent, excess_units, keep_min
    cdef int    donor_idx, min_keep, step_score
    cdef dict   qty_snap     = {}   # {terr_name: {(unit_type, owner): quantity}}

    global _reachability_cache
    # _reachability_cache.clear()

    # ── build quantity snapshot (the ONLY thing we'll mutate) ───────────────
    # This replaces deepcopy — flat numeric dict, no object cloning
    for terr_name, terr in territories.items():
        qty_snap[terr_name] = {}
        for u in terr.units:
            qty_snap[terr_name][(u.unit_type, u.owner)] = u.quantity

    # ── frontier detection (reads owner from real territories — never changes) 
    cdef set my_frontier_territories = set()
    for terr in my_territories:
        for n in _adjacency.get(terr.name, []):
            # if territories[n].owner != player and n not in FACTORY_MAP.values():
            if territories[n].owner != player:
                my_frontier_territories.add(terr.name)
                break


    home_factory = FACTORY_MAP[player]

    # ── pre-compute scoring maps ─────────────────────────────────────────────
    cdef dict staging_score     = {}
    cdef dict factory_adj_score = {}
    cdef int  score

    for terr in my_territories:
        staging_score[terr.name] = sum(
            1 for nb in _adjacency.get(terr.name, [])
            if nb in my_frontier_territories
        )
        score = 0
        for nb in _adjacency.get(terr.name, []):
            if nb == home_factory:
                score += 3
            elif nb in _victory_cities:
                score += 1
        factory_adj_score[terr.name] = score

    # ── BFS distance to frontier ─────────────────────────────────────────────
    # territories dict only used for keys here — safe to use real object
    cdef dict dist_to_frontier = _bfs_dist_to_frontier(my_frontier_territories, territories)

    # ── total units from snapshot ────────────────────────────────────────────
    cdef int total_my_units = sum(
        _count_defense_units_snap(t.name, qty_snap) for t in my_territories
    )

    # ── frontier excess map from snapshot ────────────────────────────────────
    cdef dict frontier_excess_map = {}
    for t in my_frontier_territories:
        frontier_excess_map[t] = _frontier_excess_snap(t, qty_snap, territories, player)

    # ── sorted target list ───────────────────────────────────────────────────
    # _territory_priority uses _count_defense_units internally on Territory obj
    # for the "empty frontier" bonus — but that's a one-time sort, minor cost,
    # and ownership never changes here so real objects are fine
    cdef list targets = list(my_territories)
    targets.sort(
        key=lambda t: _territory_priority(
            t.name,
            my_frontier_territories,
            territories,
            staging_score,
            factory_adj_score,
        ),
        reverse=True,
    )

    # ── donor list (use snapshot for unit counts) ────────────────────────────
    cdef list donor_territories = []
    for t in my_territories:
        if _count_defense_units_snap(t.name, qty_snap) <= 0:
            continue
        if t.name in my_frontier_territories and t.name != home_factory:
            if frontier_excess_map.get(t.name, 0) <= 0:
                continue
        donor_territories.append(t)

    donor_territories.sort(
        key=lambda t: _count_defense_units_snap(t.name, qty_snap) - _quota(
            t.name, my_frontier_territories, staging_score, factory_adj_score,
            home_factory, territories, player, total_my_units
        ),
        reverse=True,
    )

    # ── PASS 0: evacuate home factory ────────────────────────────────────────
    keep_min     = 2 if _has_enemy_neighbor(home_factory, territories, player, FACTORY_MAP) else 0
    excess_units = max(0, _count_defense_units_snap(home_factory, qty_snap) - keep_min)
    sent         = 0
    cdef dict factory_snap = qty_snap[home_factory]

    for u in territories[home_factory].units:
        move_range = unit_move_ranges.get(u.unit_type, 1)
        snap_qty   = factory_snap.get((u.unit_type, u.owner), 0)
        if u.owner != player or u.unit_type == "factory" or move_range <= 0 or snap_qty <= 0:
            continue
        while factory_snap.get((u.unit_type, u.owner), 0) > 0 and sent < excess_units:
            dest, score = _best_step_toward_frontier(
                game_state, u, home_factory, targets,
                dist_to_frontier, my_frontier_territories,
                staging_score, factory_adj_score,
            )
            if dest is None or score <= 0:
                break
            move_seq.append(Move(
                "noncombat",
                to_terr=dest,
                moves=[Attack(unit=u, from_territory=home_factory, quantity=1)],
            ))
            # decrement snapshot only — real Territory object untouched
            factory_snap[(u.unit_type, u.owner)] -= 1
            sent += 1

    # ── PASS 1: fill targets to quota ────────────────────────────────────────
    cdef tuple snap_key

    for terr in targets:
        terr_name = terr.name

        if _count_defense_units_snap(terr_name, qty_snap) >= _quota(
            terr_name, my_frontier_territories, staging_score, factory_adj_score,
            home_factory, territories, player, total_my_units
        ):
            continue

        donor_idx = 0
        while _count_defense_units_snap(terr_name, qty_snap) < _quota(
            terr_name, my_frontier_territories, staging_score, factory_adj_score,
            home_factory, territories, player, total_my_units
        ):
            if donor_idx >= len(donor_territories):
                break

            donor = donor_territories[donor_idx]

            # drain guard
            if donor.name in my_frontier_territories:
                if _count_defense_units_snap(donor.name, qty_snap) <= frontier_excess_map.get(donor.name, 0):
                    donor_idx += 1
                    continue
            else:
                min_keep = 2 if _has_enemy_neighbor(donor.name, territories, player, FACTORY_MAP) else 1
                if _count_defense_units_snap(donor.name, qty_snap) <= min_keep:
                    donor_idx += 1
                    continue

            # pick first movable unit that still has snapshot qty > 0
            picked    = None
            snap_key  = ("", "")
            for u in territories[donor.name].units:
                move_range = unit_move_ranges.get(u.unit_type, 1)
                if u.owner != player or u.unit_type == "factory" or move_range <= 0:
                    continue
                k = (u.unit_type, u.owner)
                if qty_snap[donor.name].get(k, 0) <= 0:
                    continue        # snapshot says exhausted — skip
                picked   = u
                snap_key = k
                break

            if picked is None:
                donor_idx += 1
                continue

            dest       = None
            move_range = unit_move_ranges.get(picked.unit_type, 1)
            key        = (donor.name, move_range)

            if key not in _reachability_cache:
                _reachability_cache[key] = frozenset(
                    t for t in territories
                    if t != donor.name and
                    can_reach_cache_helper(donor.name, t, move_range, player, territories, set(my_territories))
                )

            if terr_name in _reachability_cache.get(key, frozenset()):
                dest = terr_name
            else:
                step, step_score = _best_step_toward_frontier(
                    game_state, picked, donor.name, targets,
                    dist_to_frontier, my_frontier_territories,
                    staging_score, factory_adj_score,
                )
                if step is not None and step_score > 0:
                    dest = step

            if dest is None:
                donor_idx += 1
                continue

            move_seq.append(Move(
                "noncombat",
                to_terr=dest,
                moves=[Attack(unit=picked, from_territory=donor.name, quantity=1)],
            ))

            # decrement snapshot — real Territory object untouched
            qty_snap[donor.name][snap_key] -= 1
            # also credit the destination so it counts toward quota
            dest_key = (picked.unit_type, player)
            qty_snap[dest][(dest_key)] = qty_snap[dest].get(dest_key, 0) + 1

            if donor.name in my_frontier_territories:
                frontier_excess_map[donor.name] = max(0, frontier_excess_map.get(donor.name, 0) - 1)

    return move_seq



# =========================
# State evaluation
# =========================

def evaluate_state(dict territories, dict players, str whoAmI, list victory_cities_list, int depth, int depth_budget, int r):
    """
    Cython port of MCTS.evaluate_state().
    Call from Python as:
        move_generator_cpp.evaluate_state(
            state.territories, state.players, whoAmI,
            victory_cities, depth, depth_budget
        )
    """
    cdef str me = whoAmI
    cdef Territory terr
    cdef Unit u
    cdef str name, p
    cdef int my_count = 0, enemy_count = 0
    cdef int my_vc = 0, enemy_vc = 0
    cdef double my_tuv = 0.0, enemy_tuv = 0.0, p_tuv
    cdef double tuv_term, terr_term, vc_term, score
    cdef set vc_set = set(victory_cities_list)

    # --- terminal check ---
    cdef dict vc_owner_count = {}
    for name in vc_set:
        owner = territories[name].owner
        vc_owner_count[owner] = vc_owner_count.get(owner, 0) + 1
    for owner, count in vc_owner_count.items():
        if count == len(vc_set):
            if owner == me:
                return 0.5 + 0.5 * (depth_budget - depth) / depth_budget, True
            else:
                return -0.5 - 0.5 * (depth_budget - depth) / depth_budget, True

    flag_ownership_term = -1
    for name, terr in territories.items():
        if terr.owner == me:
            my_count += 1
            if name in vc_set:
                my_vc += 1
            if name == "Flag":
                flag_ownership_term = 1
        elif terr.owner != "Neutral":
            enemy_count += 1
            if name in vc_set:
                enemy_vc += 1


        for u in terr.units:
            if u.unit_type == "factory":
                continue
            if u.owner == me:
                my_tuv += u.quantity * u.cost
            elif u.owner != "Neutral":
                enemy_tuv += u.quantity * u.cost
                

    tuv_denom = my_tuv + enemy_tuv
    if tuv_denom < 1e-9:
        tuv_denom = 1e-9
    # my_income_share = sum(territory_production[t.name] for t in my_terrs) / max(1, total_income)
    # tuv_term = (my_tuv / max(1, my_tuv + enemy_tuv)) - my_income_share
    tuv_term = my_tuv / tuv_denom

    terr_denom = my_count + enemy_count
    if terr_denom < 1:
        terr_denom = 1
    terr_term = my_count/ <double>terr_denom

    vc_denom = my_vc + enemy_vc 
    vc_term = my_vc/ <double>vc_denom

    income = players[me].PU
    income_denom = sum(players[p].PU for p in players)
    enemy_income = sum(players[p].PU for p in players if p != me)
    income_term = income / income_denom if income_denom > 0 else 0

    # replace the proximity block with:
    shortest_dist_to_flag = float('inf')
    for name, terr in territories.items():
        if terr.owner == me:
            d = dist_to_flag.get(name, float('inf'))
            if d < shortest_dist_to_flag:
                shortest_dist_to_flag = d

    shortest_enemy_dist = float('inf')
    for name, terr in territories.items():
        if terr.owner != me and terr.owner != "Neutral":
            d = dist_to_flag.get(name, float('inf'))
            if d < shortest_enemy_dist:
                shortest_enemy_dist = d

    my_prox  = 1.0 / (1.0 + shortest_dist_to_flag)  if shortest_dist_to_flag < float('inf') else 0.0
    enemy_prox = 1.0 / (1.0 + shortest_enemy_dist) if shortest_enemy_dist < float('inf') else 0.0
    proximity_score = my_prox - enemy_prox   # now in [-1, 1]

    score = 0.20 * flag_ownership_term + 0.30 * vc_term + 0.50 * income_term
    scaled_score = 0.5 * score
    # print("R",r, " score=",score, "(", scaled_score, ") ", flag_ownership_term, vc_term, income_term, tuv_term)

    return scaled_score, False


