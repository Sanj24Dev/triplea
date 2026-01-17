#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <queue>
#include <string>
#include <algorithm>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <iostream>
#include <chrono>

namespace py = pybind11;

struct Territory {
    std::string owner;
};

struct Unit {
    std::string owner;
    std::string type;
    
    bool operator==(const Unit& other) const {
        return owner == other.owner && type == other.type;
    }
};

// Hash function for Unit (needed for unordered_set)
namespace std {
    template <>
    struct hash<Unit> {
        size_t operator()(const Unit& u) const {
            return hash<string>()(u.owner) ^ (hash<string>()(u.type) << 1);
        }
    };
}

struct UnitInfo {
    std::string from_territory;
    Unit unit;
    int quantity;
};

struct AttackUnit {
    std::string unit_type;
    std::string from_territory;
    int quantity;
};

struct Move {
    std::string delegate;
    std::string to_terr;
    std::vector<AttackUnit> moves;
    bool end_phase;
    int strength;
    
    Move() : delegate("combat"), end_phase(false), strength(0) {}
};

using AdjacencyList = std::unordered_map<std::string, std::vector<std::string>>;
using TerritoryMap  = std::unordered_map<std::string, Territory>;

// Global adjacency list stored in C++
static AdjacencyList adjacency;
static std::unordered_map<std::string, int> unit_move_ranges;
static std::unordered_map<std::string, double> unit_attack_values;

void set_adjacency(const AdjacencyList& adj) {
    adjacency = adj;
}

void set_unit_move_ranges(const std::unordered_map<std::string, int>& move_ranges) {
    unit_move_ranges = move_ranges;
}

void set_unit_attack_values(const std::unordered_map<std::string, double>& attack_values) {
    unit_attack_values = attack_values;
}

void clear_adjacency() {
    adjacency.clear();
}

bool can_reach(
    const std::string& from_territory,
    const std::string& to_territory,
    int move_range,
    const Unit& unit,
    const TerritoryMap& territories,
    const std::unordered_set<std::string>& my_territories
) {
    std::queue<std::pair<std::string, int>> queue;
    std::unordered_set<std::string> visited;

    queue.emplace(from_territory, 0);
    visited.insert(from_territory);

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
                if (terr_owner == unit.owner || terr_owner == "Neutral") {
                    // allowed
                }
                else {
                    if (neighbor != to_territory)
                        continue;
                }
            }
            else {
                if (neighbor != to_territory &&
                    my_territories.count(neighbor) == 0) {
                    continue;
                }
            }

            visited.insert(neighbor);
            if (neighbor == to_territory)
                return true;

            queue.emplace(neighbor, steps + 1);
        }
    }

    return false;
}

std::vector<UnitInfo> get_reachable_units(
    const std::string& target_territory,
    const std::string& player,
    const TerritoryMap& territories,
    const std::unordered_set<std::string>& my_territories,
    const std::vector<UnitInfo>& all_units
) {
    std::vector<UnitInfo> reachable_units;
    
    for (const auto& unit_info : all_units) {
        if (unit_info.unit.owner != player)
            continue;
        
        if (unit_info.unit.type == "aaGun")
            continue;
        
        int move_range = 1;
        auto it = unit_move_ranges.find(unit_info.unit.type);
        if (it != unit_move_ranges.end()) {
            move_range = it->second;
        }
        
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
    }

    return reachable_units;
}

// Helper function to generate all quantity combinations
void generate_combinations(
    const std::vector<UnitInfo>& units,
    std::vector<std::vector<int>>& result,
    std::vector<int>& current,
    size_t index
) {
    if (index == units.size()) {
        // Skip empty combinations
        int sum = 0;
        for (int q : current) sum += q;
        if (sum > 0) {
            result.push_back(current);
        }
        return;
    }
    
    // Try all quantities from 0 to max for this unit
    for (int qty = 0; qty <= units[index].quantity; ++qty) {
        current.push_back(qty);
        generate_combinations(units, result, current, index + 1);
        current.pop_back();
    }
}

int calculate_strength(
    const std::vector<AttackUnit>& moves
) {
    int total_strength = 0;
    
    for (const auto& attack : moves) {
        auto it = unit_attack_values.find(attack.unit_type);
        if (it != unit_attack_values.end()) {
            total_strength += it->second * attack.quantity;
        }
    }
    
    return total_strength;
}

std::vector<Move> combat_legal_moves(
    const std::string& player,
    const TerritoryMap& territories,
    const std::unordered_set<std::string>& my_territories,
    const std::vector<UnitInfo>& all_units,
    const float time_budget
) {
    using Clock = std::chrono::steady_clock;
    auto start = Clock::now();
    std::vector<Move> legal_moves;
    
    // For each enemy territory
    for (const auto& [enemy_territory_name, enemy_territory] : territories) {
        if (enemy_territory.owner == player)
            continue;
        
        // Get units that can attack this territory
        std::vector<UnitInfo> reachable = get_reachable_units(
            enemy_territory_name,
            player,
            territories,
            my_territories,
            all_units
        );
        
        if (reachable.empty()) {
            continue;
        }

        if (std::chrono::duration<float>(Clock::now() - start).count() > time_budget)
            return legal_moves;

        // Add option to skip attack on this territory (empty moves)
        Move skip_move;
        skip_move.to_terr = enemy_territory_name;
        skip_move.strength = 0;
        legal_moves.push_back(skip_move);

        // Generate all quantity combinations
        std::vector<std::vector<int>> combinations;
        std::vector<int> current;
        generate_combinations(reachable, combinations, current, 0);
        
        // Create a move for each combination
        for (const auto& quantities : combinations) {
            Move move;
            move.to_terr = enemy_territory_name;
            
            for (size_t i = 0; i < quantities.size(); ++i) {
                if (quantities[i] > 0) {
                    AttackUnit attack;
                    attack.unit_type = reachable[i].unit.type;
                    attack.from_territory = reachable[i].from_territory;
                    attack.quantity = quantities[i];
                    move.moves.push_back(attack);
                }
            }
            move.strength = calculate_strength(move.moves);
            legal_moves.push_back(move);

            if (std::chrono::duration<float>(Clock::now() - start).count() > time_budget)
                return legal_moves;
        }
        
        
    }
    
    // Add end phase move
    Move end_move;
    end_move.end_phase = true;
    end_move.strength = 0;
    legal_moves.push_back(end_move);
    
    return legal_moves;
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

    py::class_<AttackUnit>(m, "AttackUnit")
        .def(py::init<>())
        .def_readwrite("unit_type", &AttackUnit::unit_type)
        .def_readwrite("from_territory", &AttackUnit::from_territory)
        .def_readwrite("quantity", &AttackUnit::quantity);

    py::class_<Move>(m, "Move")
        .def(py::init<>())
        .def_readwrite("delegate", &Move::delegate)
        .def_readwrite("to_terr", &Move::to_terr)
        .def_readwrite("moves", &Move::moves)
        .def_readwrite("end_phase", &Move::end_phase)
        .def_readwrite("strength", &Move::strength); 

    m.def("set_adjacency", &set_adjacency,
          "Set the global adjacency list (call once at game start)");

    m.def("set_unit_move_ranges", &set_unit_move_ranges,
          "Set the global move ranges (call once at game start)");
    
    m.def("set_unit_attack_values", &set_unit_attack_values,
          "Set the global attack values (call once at game start)");
    
    m.def("clear_adjacency", &clear_adjacency,
          "Clear the global adjacency list (optional cleanup)");

    m.def("can_reach_fast", &can_reach,
          "Fast BFS reachability check");
    
    m.def("get_reachable_units", &get_reachable_units,
          "Get all units that can reach a target territory");
    
    m.def("combat_legal_moves", &combat_legal_moves,
          "Generate all legal combat moves");
}