from torch_geometric.data import Data
import torch

def get_encoded_state(state, adjacency, turn_order, victory_cities, territory_production):
    nodes = sorted(state.territories.keys())
    node_to_idx = {n: i for i, n in enumerate(nodes)}
    
    me    = state.current_player
    my_id = turn_order.index(me)
    
    node_feats = []
    for name in nodes:
        terr = state.territories[name]
        
        owner_oh = [0.0] * len(turn_order)
        if terr.owner in turn_order:
            ch = (turn_order.index(terr.owner) - my_id) % len(turn_order)
            owner_oh[ch] = 1.0
        
        total = infantry = artillery = armor = 0
        for u in terr.units:
            if u.unit_type == "factory": continue
            total += u.quantity
            if u.unit_type == "infantry":  infantry  += u.quantity
            if u.unit_type == "artillery": artillery += u.quantity
            if u.unit_type == "armor":     armor     += u.quantity
        
        node_feats.append([
            1.0,                                          # is valid
            *owner_oh,                                    # 4 ownership channels
            1.0 if name in victory_cities else 0.0,
            territory_production.get(name, 0) / 5.0,
            total / 10.0, infantry / 10.0,
            artillery / 10.0, armor / 10.0,
            state.players[me].PU / 50.0,
            state.round / 20.0,
        ])
    
    # Build edge index from adjacency graph
    src, dst = [], []
    for u in adjacency.nodes():
        for v in adjacency.neighbors(u):
            if u in node_to_idx and v in node_to_idx:
                src.append(node_to_idx[u])
                dst.append(node_to_idx[v])
    
    
    node_feats = torch.tensor(node_feats, dtype=torch.float32)
    edge_index  = torch.tensor([src, dst], dtype=torch.long)

    # Wrap in PyG Data object — this is the only addition
    return Data(x=node_feats, edge_index=edge_index)