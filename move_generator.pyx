# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

import time
from collections import deque

# =========================
# Python-visible classes
# =========================

cdef class Unit:
    cdef public str unit_type
    cdef public str owner
    cdef public int quantity
    cdef public bint moved
    cdef public int qty_moved

    def __init__(self, str unit_type="", str owner="", int quantity=1, bint moved=False, int qty_moved=0):
        self.unit_type = unit_type
        self.owner = owner
        self.quantity = quantity
        self.moved = moved
        self.qty_moved = qty_moved


cdef class Territory:
    cdef public str name
    cdef public str owner
    cdef public list units   # list[Unit]

    def __init__(self, str name="", str owner="", units=None):
        self.name = name
        self.owner = owner
        self.units = units if units is not None else []

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
# Global configuration
# =========================

cdef dict _adjacency = {}
cdef dict unit_attack_values = {}
cdef dict unit_defense_values = {}
cdef dict unit_move_ranges = {}
cdef dict unit_costs = {}
cdef list _victory_cities = []

cdef dict _reachability_cache = {}

def set_adjacency(dict adj):
    global _adjacency
    _adjacency = adj

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
# Reachability (BFS)
# =========================

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

    global _reachability_cache
    _reachability_cache.clear()
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
                    if calculate_attack_strength(all_units) >= (maxThreshold * def_strength) + 4:
                        break
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
            if unitsUpToStrength:
                currentStrength = calculate_attack_strength(unitsUpToStrength)
                if currentStrength > def_strength:
                    attacks = form_attacks(unitsUpToStrength)
                    if sets:
                        l = len(sets)
                        if sets[l-1][1] != currentStrength:
                            sets.append((attacks, currentStrength))
                    else:
                        sets.append((attacks, currentStrength))



            # ── weak sets fallback ────────────────────────────────────────────
            if not sets:
                weak_sets             = []
                unitsUpToStrength     = []
                strengthThreshold_weak = 0.35

                for info in sorted_reachable:
                    for _ in range(info.quantity):
                        unitsUpToStrength.append(UnitInfo(info.from_territory, info.unit, 1))
                        currentStrength = calculate_attack_strength(unitsUpToStrength)

                        if (currentStrength > strengthThreshold_weak * def_strength and
                                currentStrength <= def_strength):
                            attacks = form_attacks(unitsUpToStrength)
                            weak_sets.append((attacks, currentStrength))
                            strengthThreshold_weak += 0.15
                            if len(weak_sets) >= 3:
                                break
                    if len(weak_sets) >= 3:
                        break

                sets.extend(weak_sets)

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

