#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <queue>
#include <string>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <iostream>

namespace py = pybind11;


struct Territory {
    std::string owner;
};

struct Unit {
    std::string owner;
    std::string type;   // "armour" or other
};

struct UnitInfo {
    std::string from_territory;
    Unit unit;
    int quantity;
};

using AdjacencyList = std::unordered_map<std::string, std::vector<std::string>>;
using TerritoryMap  = std::unordered_map<std::string, Territory>;

// Global adjacency list stored in C++
static AdjacencyList adjacency;

// Function to initialize/set the adjacency list once
void set_adjacency(const AdjacencyList& adj) {
    adjacency = adj;
}

// Function to clear adjacency (optional, for cleanup)
void clear_adjacency() {
    adjacency.clear();
}

bool can_reach(
    const std::string& from_territory,
    const std::string& to_territory,
    int move_range,
    const Unit& unit,
    const TerritoryMap& territories,
    // const AdjacencyList& adjacency,
    const std::unordered_set<std::string>& my_territories
) {
    std::queue<std::pair<std::string, int>> queue;
    std::unordered_set<std::string> visited;

    queue.emplace(from_territory, 0);
    visited.insert(from_territory);
    // std::cout << from_territory << " " << unit.type << " : ";
    while (!queue.empty()) {
        auto [current, steps] = queue.front();
        queue.pop();

        if (steps >= move_range)
            continue;

        auto it = adjacency.find(current);
        if (it == adjacency.end())
            continue;

        for (const std::string& neighbor : it->second) {
            if (visited.count(neighbor))
                continue;

            const std::string& terr_owner = territories.at(neighbor).owner;

            if (unit.type == "armour") {
                // Friendly or Neutral
                if (terr_owner == unit.owner || terr_owner == "Neutral") {
                    // allowed
                }
                // Enemy
                else {
                    if (neighbor != to_territory)
                        continue;
                }
            }
            else {
                // Non-armour units
                if (neighbor != to_territory &&
                    my_territories.count(neighbor) == 0) {
                    continue;
                }
            }

            visited.insert(neighbor);
            // std::cout << neighbor << " ";
            if (neighbor == to_territory)
                return true;

            queue.emplace(neighbor, steps + 1);
        }
    }

    return false;
}

// Get all units that can reach a target territory
std::vector<UnitInfo> get_reachable_units(
    const std::string& target_territory,
    const std::string& player,
    const TerritoryMap& territories,
    const std::unordered_set<std::string>& my_territories,
    const std::vector<UnitInfo>& all_units,  // All player's units with their locations
    const std::unordered_map<std::string, int>& unit_move_ranges  // unit_type -> move_range
) {
    // for (auto i : all_units) {
    //     std::cout << i.unit.type << std::endl;
    // }

    std::vector<UnitInfo> reachable_units;
    
    for (const auto& unit_info : all_units) {
        // Skip if not owned by player
        if (unit_info.unit.owner != player)
            continue;
        
        // Skip AA guns
        if (unit_info.unit.type == "aaGun")
            continue;
        
        // Get move range for this unit type
        int move_range = 1;  // default
        auto it = unit_move_ranges.find(unit_info.unit.type);
        if (it != unit_move_ranges.end()) {
            move_range = it->second;
        }
        
        // Check if this unit can reach the target
        // std::cout << "Checking " << unit_info.unit.type << " to " << target_territory << "\t";
        if (can_reach(
            unit_info.from_territory,
            target_territory,
            move_range,
            unit_info.unit,
            territories,
            my_territories
        )) {
            reachable_units.push_back(unit_info);
        }
        // std::cout << std::endl;
    }

    // for (auto i : reachable_units) {
    //     std::cout << i.unit.type << std::endl;
    // }
    return reachable_units;
}



PYBIND11_MODULE(reachability_cpp, m) {
    py::class_<Unit>(m, "Unit")
        .def(py::init<>())
        .def_readwrite("owner", &Unit::owner)
        .def_readwrite("type", &Unit::type);

    py::class_<Territory>(m, "Territory")
        .def(py::init<>())
        .def_readwrite("owner", &Territory::owner);

    py::class_<UnitInfo>(m, "UnitInfo")
        .def(py::init<>())
        .def_readwrite("from_territory", &UnitInfo::from_territory)
        .def_readwrite("unit", &UnitInfo::unit)
        .def_readwrite("quantity", &UnitInfo::quantity);

    m.def("set_adjacency", &set_adjacency,
          "Set the global adjacency list (call once at game start)");
    
    m.def("clear_adjacency", &clear_adjacency,
          "Clear the global adjacency list (optional cleanup)");

    m.def("can_reach_fast", &can_reach,
          "Fast BFS reachability check");
    
    m.def("get_reachable_units", &get_reachable_units,
          "Get all units that can reach a target territory");
}