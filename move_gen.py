import json
import itertools

def load_game(filename="gameInfo/Capture The Flag.json"):
    with open(filename, "r") as f:
        return json.load(f)

def get_factories(game_data, player):
    """Return list of territories where the player has a factory."""
    factories = []
    for unit in game_data["starting_units"]:
        if unit["owner"] == player and unit["unit"] == "factory":
            factories.append(unit["territory"])
    return factories

def generate_legal_purchase_moves(game_data, player):
    rules = game_data["production_rules"]
    resources = game_data["initial_resources"][player]
    factories = get_factories(game_data, player)

    if not factories:
        return []  # can't build if no factory

    # Extract unit costs
    units = [(rule["unit"], rule["cost"]) for rule in rules.values()]

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
                    "place_in": factories  # player chooses where later
                })

    return legal_moves




game_data = load_game()
# territories = game_data["territories"]
# print(territories)
# connections = game_data["connections"]
# print(connections)
# players = game_data["players"]
# print(players)
# units = game_data["units"]
# print(units)
# production_rules = game_data["production_rules"]
# print(production_rules)
# starting_ownership = game_data["starting_ownership"]
# print(starting_ownership)
# starting_units = game_data["starting_units"]
# print(starting_units)
# initial_resources = game_data["initial_resources"]
# print(initial_resources)
# victory_cities = game_data["victory_cities"]
# print(victory_cities) 


legal_purchase_moves = generate_legal_purchase_moves(game_data, "Russians")
print(legal_purchase_moves)



# For a given player on their Combat Move step:

# Choose a unit in a territory they own.

# Check movement range (e.g., infantry = 1, armour = 2, fighters = 4, bombers = 6).

# Follow connections to adjacent territories (land or sea depending on unit type).

# Any move that ends in an enemy-controlled territory (or neutral if allowed) is a legal combat move.

# Example: If Russians have infantry in RussianStart, they can move to RussianStartLeft, RussianStartRight, or RussianStepOne if those are enemy territories.

# Multi-unit moves: several units from the same or different territories can be combined to attack the same enemy territory.