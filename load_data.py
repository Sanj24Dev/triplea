import os
import numpy as np
import torch
from torch_geometric.data import Data, Dataset, DataLoader

class PurchaseGraphDataset(Dataset):
    """
    Loads saved .npz graph samples for supervised training.
    Each sample contains:
        - node_features: (N, F)
        - adjacency: (N, N)
        - global_features: (G,)
        - legal_moves: list[int]
        - chosen_move: int
    """

    def __init__(self, root_dir, transform=None, pre_transform=None):
        super().__init__(root=None, transform=transform, pre_transform=pre_transform)
        self.root_dir = root_dir
        self.files = [
            os.path.join(root_dir, f)
            for f in sorted(os.listdir(root_dir))
            if f.endswith(".npz")
        ]

    def len(self):
        return len(self.files)

    def get(self, idx):
        data_npz = np.load(self.files[idx], allow_pickle=True)

        node_features = torch.tensor(data_npz["node_features"], dtype=torch.float)
        adj = torch.tensor(data_npz["adjacency"], dtype=torch.float)

        # Convert adjacency → edge_index
        edge_index = adj.nonzero().t().contiguous()

        # Global features (delegate info)
        global_features = torch.tensor(data_npz["global_features"], dtype=torch.float)

        # Labels
        legal_moves = torch.tensor(data_npz["legal_moves"], dtype=torch.long)
        chosen_move = torch.tensor(data_npz["chosen_move"], dtype=torch.long)

        # (optional) store player, PU deltas, round
        pu_before = float(data_npz["pu_before_move"])
        pu_after = float(data_npz["pu_after_move"])
        pu_delta = pu_after - pu_before
        round_num = int(data_npz["round"])
        player = str(data_npz["player"])

        # Build PyTorch Geometric Data object
        data = Data(
            x=node_features,         # Node features
            edge_index=edge_index,   # Graph edges
            y=chosen_move,           # Target label (move ID)
            global_features=global_features,  # Optional
            legal_moves=legal_moves,          # Legal move IDs
            pu_delta=torch.tensor([pu_delta]),
            round=torch.tensor([round_num]),
            player=player
        )

        return data


# ====================
# Example Usage
# ====================
if __name__ == "__main__":
    dataset_path = "purchase_data/game1"
    dataset = PurchaseGraphDataset(dataset_path)

    print(f"Loaded {len(dataset)} samples from {dataset_path}")

    # Example: inspect first sample
    data = dataset[0]
    print("\n--- Example sample ---")
    print("Nodes:", data.x.shape)
    print("Edges:", data.edge_index.shape)
    print("Global features:", data.global_features.shape)
    print("Legal moves:", data.legal_moves)
    print("Chosen move:", data.y.item())
    print("PU delta:", data.pu_delta.item())

    # Create a DataLoader for batching
    loader = DataLoader(dataset, batch_size=8, shuffle=True)

    for batch in loader:
        print("\nBatch shapes:")
        print("x:", batch.x.shape)
        print("edge_index:", batch.edge_index.shape)
        print("y:", batch.y.shape)
        break
