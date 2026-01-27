# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

import time

# =========================
# Python-visible classes
# =========================

cdef class Unit:
    cdef public str unit_type
    cdef public str owner

    def __init__(self, str unit_type="", str owner=""):
        self.unit_type = unit_type
        self.owner = owner


cdef class Territory:
    cdef public str owner
    cdef public list units   # list[Unit]

    def __init__(self, str owner="", units=None):
        self.owner = owner
        self.units = units if units is not None else []


cdef class UnitInfo:
    cdef public str from_territory
    cdef public Unit unit
    cdef public int quantity

    def __init__(self, str from_territory="", Unit unit=None, int quantity=0):
        self.from_territory = from_territory
        self.unit = unit if unit is not None else Unit()
        self.quantity = quantity


cdef class Attack:
    cdef public str unit_type
    cdef public str from_territory
    cdef public int quantity

    def __init__(self, str unit_type="", str from_territory="", int quantity=0):
        self.unit_type = unit_type
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


# =========================
# Global configuration
# =========================

cdef dict _adjacency = {}
cdef dict unit_attack_values = {}
cdef dict unit_move_ranges = {}
cdef dict unit_costs = {}

def set_adjacency(dict adj):
    global _adjacency
    _adjacency = adj

def set_unit_attack_values(dict values):
    global unit_attack_values
    unit_attack_values = values

def set_unit_move_ranges(dict ranges):
    global unit_move_ranges
    unit_move_ranges = ranges

def set_unit_costs(dict costs):
    global unit_costs
    unit_costs = costs


# =========================
# Reachability
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

    while queue:
        current, dist = queue.pop(0)

        if dist >= move_range:
            continue

        for neighbor in _adjacency.get(current, []):
            if neighbor in visited:
                continue

            terr_owner = territories[neighbor].owner

            # combat rules
            if unit.unit_type == "armour":
                if terr_owner not in (unit.owner, "Neutral") and neighbor != target:
                    continue
            else:
                if neighbor != target and neighbor not in my_territories:
                    continue

            if neighbor == target:
                return True

            visited.add(neighbor)
            queue.append((neighbor, dist + 1))

    return False


cdef list get_reachable_units(
    str target,
    str player,
    dict territories,
    set my_territories,
    list all_units
):
    cdef list reachable = []

    for info in all_units:
        if info.unit.owner != player:
            continue
        if info.unit.unit_type == "aaGun":
            continue

        move_range = unit_move_ranges.get(info.unit.unit_type, 1)

        if can_reach(
            info.from_territory,
            target,
            move_range,
            info.unit,
            territories,
            my_territories
        ):
            reachable.append(info)

    return reachable


# =========================
# Combat strength
# =========================

cdef int attack_strength(list unit_infos):
    cdef int strength = 0
    for info in unit_infos:
        power = int(unit_attack_values.get(info.unit.unit_type, 0))
        strength += power * info.quantity
    return strength


# =========================
# Combat move generation
# =========================

def combat_legal_moves(
    str player,
    dict territories,
    set my_territories,
    list all_units,
    float time_budget
):
    cdef list legal_moves = []
    cdef double start = time.time()

    for terr_name, terr in territories.items():
        if terr.owner == player:
            continue

        # --- skip move ---
        legal_moves.append(
            Move(
                delegate="combat",
                to_terr=terr_name,
                moves=[],
                end_phase=False,
                strength=0
            )
        )

        reachable = get_reachable_units(
            terr_name, player, territories, my_territories, all_units
        )

        if not reachable:
            continue

        if time.time() - start > time_budget:
            break

        # defender strength
        defender = 0
        for u in terr.units:
            if u.owner != player:
                defender += int(unit_attack_values.get(u.unit_type, 0))

        # pick cheapest single attacker if undefended
        if defender == 0:
            info = min(
                reachable,
                key=lambda x: unit_costs.get(x.unit.unit_type, 9999)
            )
            legal_moves.append(
                Move(
                    delegate="combat",
                    to_terr=terr_name,
                    moves=[Attack(info.unit.unit_type, info.from_territory, 1)],
                    strength=int(unit_attack_values.get(info.unit.unit_type, 0))
                )
            )
            continue

        # incremental buildup
        current = []
        for info in reachable:
            for _ in range(info.quantity):
                current.append(
                    UnitInfo(info.from_territory, info.unit, 1)
                )
                s = attack_strength(current)
                if s > defender:
                    attacks = [
                        Attack(u.unit.unit_type, u.from_territory, u.quantity)
                        for u in current
                    ]
                    legal_moves.append(
                        Move(
                            delegate="combat",
                            to_terr=terr_name,
                            moves=attacks,
                            strength=s
                        )
                    )
                    break

    # end phase
    legal_moves.append(
        Move(delegate="combat", end_phase=True)
    )

    return legal_moves


# =========================
# Non-combat move generation
# =========================

def non_combat_legal_moves(
    str player,
    dict territories,
    set my_territories,
    list all_units,
    float time_budget
):
    cdef list legal_moves = []
    cdef double start = time.time()

    for terr_name in my_territories:

        legal_moves.append(
            Move(
                delegate="noncombat",
                to_terr=terr_name,
                moves=[],
                strength=0
            )
        )

        reachable = get_reachable_units(
            terr_name, player, territories, my_territories, all_units
        )

        if reachable:
            info = reachable[0]
            legal_moves.append(
                Move(
                    delegate="noncombat",
                    to_terr=terr_name,
                    moves=[Attack(info.unit.unit_type, info.from_territory, 1)],
                    strength=0
                )
            )

        if time.time() - start > time_budget:
            break

    return legal_moves
