from typing import Dict, Tuple, List
import torch

NUM_CHANNELS = 12

CHANNEL_0 = torch.tensor([
    [1., 0., 1., 1., 1., 1., 1., 0., 1.],
    [0., 1., 0., 0., 0., 0., 0., 1., 0.],
    [1., 0., 1., 0., 0., 0., 1., 0., 1.],
    [1., 0., 0., 1., 0., 1., 0., 0., 1.],
    [1., 0., 0., 0., 1., 0., 0., 0., 1.],
    [1., 0., 0., 1., 0., 1., 0., 0., 1.],
    [1., 0., 1., 0., 0., 0., 1., 0., 1.],
    [0., 1., 0., 0., 0., 0., 0., 1., 0.],
    [1., 0., 1., 1., 1., 1., 1., 0., 1.]
])

CHANNEL_5 = torch.tensor([
    [1., 0., 0., 0., 0., 0., 0., 0., 1.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [0., 0., 0., 0., 0., 0., 0., 0., 0.],
    [1., 0., 0., 0., 0., 0., 0., 0., 1.]
])

CHANNEL_6 = torch.tensor([
    [2., 0., 0.4, 0.4, 0.4, 0.4, 0.4, 0., 2. ],
    [0., 0.4, 0., 0., 0., 0., 0., 0.4, 0. ],
    [0.4, 0., 0.4, 0., 0., 0., 0.4, 0., 0.4],
    [0.4, 0., 0., 0.4, 0., 0.4, 0., 0., 0.4],
    [0.4, 0., 0., 0., 3., 0., 0., 0., 0.4],
    [0.4, 0., 0., 0.4, 0., 0.4, 0., 0., 0.4],
    [0.4, 0., 0.4, 0., 0., 0., 0.4, 0., 0.4],
    [0., 0.4, 0., 0., 0., 0., 0., 0.4, 0. ],
    [2., 0., 0.4, 0.4, 0.4, 0.4, 0.4, 0., 2. ]
])

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
        grid_index,
        grid_shape,
        victory_cities,
        territory_production,
        turn_order
):
    H, W = grid_shape
    tensor = torch.zeros((NUM_CHANNELS, H, W), dtype=torch.float32)
    
    global CHANNEL_0, CHANNEL_5, CHANNEL_6
    tensor[0] = CHANNEL_0
    tensor[5] = CHANNEL_5
    tensor[6] = CHANNEL_6
    me = state.current_player
    territories = state.territories

    # Precompute my player index
    my_id = turn_order.index(me) if me in turn_order else -1

    # Precompute ownership → channel mapping
    owner_to_channel = {
        player: 1 + ((i - my_id) % len(turn_order))
        for i, player in enumerate(turn_order)
    }

    prod_dict = territory_production
    grid = grid_index
    vc = victory_cities

    for terr_name, terr in territories.items():

        cells = grid.get(terr_name)
        if not cells:
            continue

        owner_channel = owner_to_channel.get(terr.owner, None)

        # Unit counting (single pass)
        total = infantry = artillery = armour = moved = 0
        for unit in terr.units:
            if unit.unit_type == "factory":
                continue
            q = unit.quantity
            total += q

            ut = unit.unit_type
            if ut == "infantry":
                infantry += q
            elif ut == "artillery":
                artillery += q
            elif ut == "armour":
                armour += q
            
            if unit.moved:
                moved += unit.qty_moved

        total /= 10.0
        infantry /= 10.0
        artillery /= 10.0
        armour /= 10.0
        moved /= 10.0

        prod = prod_dict.get(terr_name, 0.0) / 5.0
        is_vc = terr_name in vc

        
        for r, c in cells:

            # tensor[0, r, c] = 1.0

            if owner_channel is not None:
                tensor[owner_channel, r, c] = 1.0

            # if is_vc:
            #     tensor[5, r, c] = 1.0

            # tensor[6, r, c] = prod
            tensor[7, r, c] = total
            tensor[8, r, c] = infantry
            tensor[9, r, c] = artillery
            tensor[10, r, c] = armour
            tensor[11, r, c] = moved

    return tensor