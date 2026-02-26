from ast import Dict, Tuple
import torch

NUM_CHANNELS = 12

def build_grid_index_ctf():
    grid_index = {
        "RussianBase": [(0, 0)], "RussianStartLeft": [(0,2)], "TopBar": [(0,3), (0,4), (0,5)], "ItalianStartRight": [(0,6)], "ItalianBase": [(0,8)],
        "RussianStart": [(1, 1)], "ItalianStart": [(1, 7)],
        "RussianStartRight": [(2, 0)], "RussianStepOne": [(2,2)], "ItalianStepOne": [(2,6)], "ItalianStartLeft": [(2,8)],
        "LeftBar": [(3, 0), (4, 0), (5, 0)], "RussianStepTwo": [(3,3)], "ItalianStepTwo": [(3,5)], "RightBar": [(3,8), (4,8), (5,8)],
        "Flag": [(4, 4)],
        "ChineseStepTwo": [(5, 3)], "GermanStepTwo": [(5, 5)],
        "ChineseStartLeft": [(6, 0)], "ChineseStepOne": [(6,2)], "GermanStepOne": [(6,6)], "GermanStartRight": [(6,8)],
        "ChineseStart": [(7, 1)], "GermanStart": [(7, 7)],
        "ChineseBase": [(8, 0)], "ChineseStartRight": [(8,2)], "BottomBar": [(8,3), (8,4), (8,5)], "GermanStartLeft": [(8,6)], "GermanBase": [(8,8)],
    }
    return grid_index

def get_encoded_state(
        state,
        grid_index: Dict[str, [Tuple[int, int]]],
        grid_shape: Tuple[int, int],
        victory_cities: set,
        territory_production: Dict[str, float],
        turn_order: list
):
    H, W = grid_shape
    tensor = torch.zeros((NUM_CHANNELS, H, W), dtype=torch.float32)
    
    me = state.current_player
    my_pu = state.players[me].PU if me in state.players else 0

    for terr_name, terr in state.territories.items():
        if terr_name not in grid_index:
            continue

        for (r,c) in grid_index[terr_name]:
            # Ch 0: valid territory
            tensor[0, r, c] = 1.0
            
            # Ch 1-4: ownership
            my_id = turn_order.index(me) if me in turn_order else -1
            for i in range(len(turn_order)):
                player = turn_order[i]
                # channel is relative to me
                ch_id = (i - my_id) % len(turn_order) 
                if player == terr.owner:
                    tensor[1 + ch_id, r, c] = 1.0
                    break
            
            # Ch 5: victory city
            if terr_name in victory_cities:
                tensor[5, r, c] = 1.0
            
            # Ch 6: production value (normalized)
            tensor[6, r, c] = territory_production.get(terr_name, 0.0) / 5.0

            # Ch 7: unit counts
            total, infantry, artillery, armour = 0, 0, 0, 0
            for unit in terr.units:
                if unit.unit_type == "Factory":
                    continue
                total += unit.quantity
                if unit.type == "infantry":
                    infantry += unit.quantity
                elif unit.type == "artillery":
                    artillery += unit.quantity
                elif unit.type == "armour":
                    armour += unit.quantity

            tensor[7, r, c] = total / 10.0
            tensor[8, r, c] = infantry / 10.0
            tensor[9, r, c] = artillery / 10.0
            tensor[10, r, c] = armour / 10.0

    # Ch 11: my PU (broadcasted)
    tensor[11, :, :] = my_pu / 50.0
    return tensor