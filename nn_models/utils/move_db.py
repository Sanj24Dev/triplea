import json


COMBAT_MOVE_DICT_PATH = "moves/dict_combat_move.json"
try:
    with open(COMBAT_MOVE_DICT_PATH, "r") as f:
        COMBAT_MOVE_DICT = json.load(f)
except FileNotFoundError:
    COMBAT_MOVE_DICT = {}


def update_combat_dict(legal_moves):
    updated = False
    for move in legal_moves:
        to_terr = move.to_terr
        for attack in move.moves:
            # Represent move as a canonical string key
            to_store = {"from": attack.from_terr, "to": to_terr, "unit": attack.unit, "quantity": attack.quantity}
            key = json.dumps(to_store, sort_keys=True)

            if key not in COMBAT_MOVE_DICT:
                COMBAT_MOVE_DICT[key] = len(COMBAT_MOVE_DICT)
                updated = True

    # Save dictionary if new moves were added
    if updated:
        with open(COMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(COMBAT_MOVE_DICT, f, indent=2)

def get_dict_len():
    return len(COMBAT_MOVE_DICT)
