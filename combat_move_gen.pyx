# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdlib cimport malloc, free
from libcpp.vector cimport vector
from libcpp.string cimport string
from libcpp.unordered_map cimport unordered_map
from libcpp.unordered_set cimport unordered_set
from libcpp.queue cimport queue
from libcpp.pair cimport pair
from cpython cimport bool
import time

# C++ structs
cdef extern from "<string>" namespace "std":
    cdef cppclass string:
        string()
        string(const char*)
        const char* c_str()

# Python-visible classes
cdef class Unit:
    cdef public str owner
    cdef public str unit_type
    
    def __init__(self, str owner="", str type=""):
        self.owner = owner
        self.unit_type = type

cdef class Territory:
    cdef public str owner
    cdef public object units  # List of units
    
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

cdef class Move:
    cdef public str delegate
    cdef public str to_terr
    cdef public list moves
    cdef public bool end_phase
    cdef public int strength
    
    def __init__(self, str delegate=None, str to_terr=None, 
                 list moves=None, bool end_phase=False, int strength=0):
        self.delegate = delegate if delegate is not None else "combat"
        self.to_terr = to_terr
        self.moves = moves if moves is not None else []
        self.end_phase = end_phase
        self.strength = strength
    
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

# Global adjacency stored as Python dict for now (can optimize further)
cdef dict _adjacency = {}

def set_adjacency(dict adj):
    """Set the global adjacency list"""
    global _adjacency
    _adjacency = adj

def clear_adjacency():
    """Clear the global adjacency list"""
    global _adjacency
    _adjacency = {}

cdef bool can_reach(
    str from_territory,
    str to_territory,
    int move_range,
    Unit unit,
    dict territories,
    set my_territories
):
    """Check if a unit can reach target territory using BFS"""
    cdef list queue_list = [(from_territory, 0)]
    cdef set visited = {from_territory}
    cdef str current, neighbor, terr_owner
    cdef int steps, idx
    cdef list neighbors
    
    idx = 0
    while idx < len(queue_list):
        current, steps = queue_list[idx]
        idx += 1
        
        if steps >= move_range:
            continue
        
        neighbors = _adjacency.get(current, [])
        
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            
            terr_owner = territories[neighbor].owner
            
            if unit.unit_type == "armour":
                if terr_owner == unit.owner or terr_owner == "Neutral":
                    pass  # allowed
                else:
                    if neighbor != to_territory:
                        continue
            else:
                if neighbor != to_territory and neighbor not in my_territories:
                    continue
            
            visited.add(neighbor)
            if neighbor == to_territory:
                return True
            
            queue_list.append((neighbor, steps + 1))
    
    return False

cdef list get_reachable_units(
    str target_territory,
    str player,
    dict territories,
    set my_territories,
    list all_units,
    dict unit_move_ranges
):
    """Get all units that can reach a target territory"""
    cdef list reachable_units = []
    cdef UnitInfo unit_info
    cdef int move_range
    
    for unit_info in all_units:
        if unit_info.unit.owner != player:
            continue
        
        if unit_info.unit.unit_type == "aaGun":
            continue
        
        move_range = unit_move_ranges.get(unit_info.unit.unit_type, 1)
        
        if can_reach(
            unit_info.from_territory,
            target_territory,
            move_range,
            unit_info.unit,
            territories,
            my_territories
        ):
            reachable_units.append(unit_info)
    
    return reachable_units

cdef void generate_combinations_recursive(
    list units,
    list result,
    list current,
    int index
):
    """Generate all quantity combinations recursively"""
    cdef int qty, sum_qty, i
    cdef UnitInfo unit_info
    
    if index == len(units):
        # Skip empty combinations
        sum_qty = 0
        for qty in current:
            sum_qty += qty
        if sum_qty > 0:
            result.append(current[:])  # Make a copy
        return
    
    unit_info = units[index]
    
    # Try all quantities from 0 to max for this unit
    for qty in range(unit_info.quantity + 1):
        current.append(qty)
        generate_combinations_recursive(units, result, current, index + 1)
        current.pop()

cdef list generate_combinations(list units):
    """Generate all quantity combinations"""
    cdef list result = []
    cdef list current = []
    generate_combinations_recursive(units, result, current, 0)
    return result

cdef int calculate_strength_from_moves(
    list moves_list,
    dict unit_attack_values
):
    """Calculate total attack strength from moves list"""
    cdef int total_strength = 0
    cdef dict attack_dict
    cdef Unit unit
    cdef double attack_value
    cdef int quantity
    
    for attack_dict in moves_list:
        unit = attack_dict["unit"]
        quantity = attack_dict["quantity"]
        attack_value = unit_attack_values.get(unit.unit_type, 0.0)
        total_strength += int(attack_value * quantity)
    
    return total_strength

def combat_legal_moves(
    str player,
    dict territories,
    set my_territories,
    list all_units,
    dict unit_move_ranges,
    dict unit_attack_values,
    float time_budget
):
    """Generate all legal combat moves"""
    cdef list legal_moves = []
    cdef list reachable, combinations, moves_list
    cdef str enemy_territory_name
    cdef Territory enemy_territory
    cdef Move move
    cdef list quantities
    cdef int i, qty
    cdef UnitInfo unit_info
    cdef dict attack_dict

    start_time = time.time()
    
    # For each enemy territory
    for enemy_territory_name, enemy_territory in territories.items():
        if enemy_territory.owner == player:
            continue
        
        # Get units that can attack this territory
        reachable = get_reachable_units(
            enemy_territory_name,
            player,
            territories,
            my_territories,
            all_units,
            unit_move_ranges
        )

        if time.time() - start_time > time_budget:
            return legal_moves
        
        if not reachable:
            continue
        
        # Generate all quantity combinations
        combinations = generate_combinations(reachable)
        
        # Create a move for each combination
        for quantities in combinations:
            moves_list = []
            
            for i in range(len(quantities)):
                qty = quantities[i]
                if qty > 0:
                    unit_info = reachable[i]
                    # Create dict matching your Python format
                    attack_dict = {
                        "unit": unit_info.unit,
                        "from": unit_info.from_territory,
                        "quantity": qty
                    }
                    moves_list.append(attack_dict)
            
            strength = calculate_strength_from_moves(moves_list, unit_attack_values)
            
            move = Move(
                delegate="combat",
                to_terr=enemy_territory_name,
                moves=moves_list,
                end_phase=False,
                strength=strength
            )
            legal_moves.append(move)
            
            if time.time() - start_time > time_budget:
                return legal_moves
        
        # Add option to skip attack on this territory (empty moves)
        skip_move = Move(
            delegate="combat",
            to_terr=enemy_territory_name,
            moves=[],
            end_phase=False,
            strength=0
        )
        legal_moves.append(skip_move)
    
    # Add end phase move
    end_move = Move(
        delegate="combat",
        to_terr=None,
        moves=None,
        end_phase=True,
        strength=0
    )
    legal_moves.append(end_move)
    
    return legal_moves