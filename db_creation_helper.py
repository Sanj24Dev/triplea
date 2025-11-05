import json


def update_puchase_dict(legal_moves):
    updated = False
    for move in legal_moves:
        # Represent move as a canonical string key
        key = json.dumps(move.get("purchase"), sort_keys=True)

        if key not in PURCHASE_MOVE_DICT:
            PURCHASE_MOVE_DICT[key] = len(PURCHASE_MOVE_DICT)
            updated = True

    # Save dictionary if new moves were added
    if updated:
        with open(PURCHASE_MOVE_DICT_PATH, "w") as f:
            json.dump(PURCHASE_MOVE_DICT, f, indent=2)

def get_purchase_move_id(move):
    key = json.dumps(move.get("purchase"), sort_keys=True)
    if key not in PURCHASE_MOVE_DICT:
        PURCHASE_MOVE_DICT[key] = len(PURCHASE_MOVE_DICT)
        with open(PURCHASE_MOVE_DICT_PATH, "w") as f:
            json.dump(PURCHASE_MOVE_DICT, f)
    return PURCHASE_MOVE_DICT[key]


def update_combat_dict(legal_moves):
    updated = False
    for move in legal_moves:
        # Represent move as a canonical string key
        to_store = {"from":move.get("from"), "to":move.get("to"), "steps":move.get("steps"), "units":move.get("units"), "path":move.get("path")}
        key = json.dumps(to_store, sort_keys=True)

        if key not in COMBAT_MOVE_DICT:
            COMBAT_MOVE_DICT[key] = len(COMBAT_MOVE_DICT)
            updated = True

    # Save dictionary if new moves were added
    if updated:
        with open(COMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(COMBAT_MOVE_DICT, f, indent=2)

def get_combat_move_id(move):
    key = json.dumps(move, sort_keys=True)
    if key not in COMBAT_MOVE_DICT:
        COMBAT_MOVE_DICT[key] = len(COMBAT_MOVE_DICT)
        with open(COMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(COMBAT_MOVE_DICT, f)
    return COMBAT_MOVE_DICT[key]

def update_noncombat_dict(legal_moves):
    updated = False
    for move in legal_moves:
        # Represent move as a canonical string key
        to_store = {"from":move.get("from"), "to":move.get("to"), "steps":move.get("steps"), "units":move.get("units"), "path":move.get("path")}
        key = json.dumps(to_store, sort_keys=True)

        if key not in NONCOMBAT_MOVE_DICT:
            NONCOMBAT_MOVE_DICT[key] = len(NONCOMBAT_MOVE_DICT)
            updated = True

    # Save dictionary if new moves were added
    if updated:
        with open(NONCOMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(NONCOMBAT_MOVE_DICT, f, indent=2)

def get_noncombat_move_id(move):
    key = json.dumps(move, sort_keys=True)
    if key not in NONCOMBAT_MOVE_DICT:
        NONCOMBAT_MOVE_DICT[key] = len(NONCOMBAT_MOVE_DICT)
        with open(NONCOMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(NONCOMBAT_MOVE_DICT, f)
    return NONCOMBAT_MOVE_DICT[key]

def save_delegate_json(state, player, move_type, pu_before_move, pu_after_move, ep, round_num=None, legal_moves=None, chosen_move=None, base_filename="_dataset.jsonl"):
    game_filename = f"{ep}game{base_filename}"
    base_filename = f"{ep}{move_type}{base_filename}"
    
    legal_ids = []
    chosen_id = {}
    if move_type == "purchase":
        legal_ids = [get_purchase_move_id(m) for m in legal_moves]
        chosen_id = get_purchase_move_id(chosen_move)
    elif move_type == "combat":
        for move in legal_moves:
            to_check = {"from":move.get("from"), "to":move.get("to"), "steps":move.get("steps"), "units":move.get("units"), "path":move.get("path")}
            legal_ids.append(get_combat_move_id(to_check))
        chosen_id = [get_combat_move_id(m) for m in chosen_move]
    elif move_type == "noncombat":
        for move in legal_moves:
            to_check = {"from":move.get("from"), "to":move.get("to"), "steps":move.get("steps"), "units":move.get("units"), "path":move.get("path")}
            legal_ids.append(get_noncombat_move_id(to_check))
        chosen_id = [get_noncombat_move_id(m) for m in chosen_move]
    entry = {
        "round": round_num,
        "player": player,
        "delegate": move_type,
        "pu_before_move": pu_before_move,
        "pu_after_move": pu_after_move,
        "state": {
            "node_features": state["node_features"].tolist(),
            "adjacency": state["adjacency"].tolist(),
            "global_features": state["global_features"].tolist()
        },
        "legal_moves": legal_ids,
        "chosen_move": chosen_id
        # ideally also isWinner
    }
    
    with open(base_filename, "a") as f:
        json.dump(entry, f)
        f.write("\n")
    with open(game_filename, "a") as f:
        json.dump(entry, f)
        f.write("\n")


PURCHASE_MOVE_DICT_PATH = "dict_purchase_move.json"
try:
    with open(PURCHASE_MOVE_DICT_PATH, "r") as f:
        PURCHASE_MOVE_DICT = json.load(f)
except FileNotFoundError:
    PURCHASE_MOVE_DICT = {}

COMBAT_MOVE_DICT_PATH = "dict_combat_move.json"
try:
    with open(COMBAT_MOVE_DICT_PATH, "r") as f:
        COMBAT_MOVE_DICT = json.load(f)
except FileNotFoundError:
    COMBAT_MOVE_DICT = {}

NONCOMBAT_MOVE_DICT_PATH = "dict_noncombat_move.json"
try:
    with open(NONCOMBAT_MOVE_DICT_PATH, "r") as f:
        NONCOMBAT_MOVE_DICT = json.load(f)
except FileNotFoundError:
    NONCOMBAT_MOVE_DICT = {}