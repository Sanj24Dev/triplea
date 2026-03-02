import json
import os
import time

COMBAT_MOVE_DICT = {}


def update_combat_dict(actions):
    COMBAT_MOVE_DICT_PATH = "moves/ctf_dict_combat_move.json"
    lock_path = COMBAT_MOVE_DICT_PATH + ".lock"
    while os.path.exists(lock_path):
        time.sleep(0.02)
    open(lock_path, "w").close()

    global COMBAT_MOVE_DICT

    try:
        with open(COMBAT_MOVE_DICT_PATH, "r") as f:
            COMBAT_MOVE_DICT = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        COMBAT_MOVE_DICT = {}

    updated = False

    for move in actions:
        # Skip end phase moves
        if move.end_phase:
            continue

        elif not move.moves:
            to_store = {
                "to": str(move.to_terr),
                "attacks": []
            }
            key = json.dumps(to_store, sort_keys=True)

            if key not in COMBAT_MOVE_DICT:
                # safer ID generation
                next_id = max(COMBAT_MOVE_DICT.values(), default=-1) + 1
                COMBAT_MOVE_DICT[key] = next_id
                updated = True
        else:
            atks = []
            for attack in move.moves:
                atks.append({
                    "from": str(attack.from_territory),
                    "unit": str(attack.unit.unit_type),
                    "quantity": int(attack.quantity)
                })
            to_store = {
                "to": str(move.to_terr),
                "attacks": atks
            }

            key = json.dumps(to_store, sort_keys=True)

            if key not in COMBAT_MOVE_DICT:
                # safer ID generation
                next_id = max(COMBAT_MOVE_DICT.values(), default=-1) + 1
                COMBAT_MOVE_DICT[key] = next_id
                updated = True

    if updated:
        with open(COMBAT_MOVE_DICT_PATH, "w") as f:
            json.dump(COMBAT_MOVE_DICT, f, indent=2)

    os.remove(lock_path)


def get_dict_len():
    global COMBAT_MOVE_DICT
    return len(COMBAT_MOVE_DICT)


def move_to_id(move):
    global COMBAT_MOVE_DICT
    id = -1
    atks = []
    for attack in move.moves:
        atks.append({
            "from": str(attack.from_territory),
            "unit": str(attack.unit.unit_type),
            "quantity": int(attack.quantity)
        })
    to_store = {
        "to": str(move.to_terr),
        "attacks": atks
    }

    key = json.dumps(to_store, sort_keys=True)
    if key in COMBAT_MOVE_DICT:
        id = COMBAT_MOVE_DICT[key]    

    return id

# def id_to_move(id):
#     global COMBAT_MOVE_DICT
#     move = None
#     k = None
#     for key, val in COMBAT_MOVE_DICT.items():
#         if val == id:
#             k = key
#             break
#     # if k is not None:
#     #     move = Move()
#     return k