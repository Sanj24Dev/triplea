# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

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

def can_reach(
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



