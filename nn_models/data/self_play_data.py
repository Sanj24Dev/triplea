from collections import deque
from dataclasses import dataclass
import random
import numpy as np
from torch.utils.data import Dataset
import torch

@dataclass
class SelfPlayExample:
    node_feats: np.ndarray      # (N, F)
    edge_index: np.ndarray      # (2, E)
    move_feats: np.ndarray
    pi: np.ndarray
    round_num: int
    game_length: int
    num_iterations: int
    z: float

class SelfPlayBuffer:
    def __init__(self, max_size=50000):
        self.buffer = deque(maxlen=max_size)
        self.max_size = max_size

    def add(self, examples):
        self.buffer.extend(examples)
        if len(self.buffer) > self.max_size:
            self.buffer = self.buffer[-self.max_size:]

    def __len__(self):
        return len(self.buffer)

    def sample(self, n):
        examples = list(self.buffer)

        weights = []
        for ex in examples:
            quality = min(1.0, ex.num_iterations / 1000)
            # z_bonus = 1.2 if ex.z > 0 else 1.0
            # w = quality # * z_bonus
            w = (1.0 / ex.game_length) * quality
            weights.append(w)

        total = sum(weights)
        weights = [w / total for w in weights]
        n = min(n, len(examples))
        replace = n > len(examples)

        indices = np.random.choice(len(examples), size=n, replace=replace, p=weights)
        return [examples[i] for i in indices]


class SelfPlayDataset(Dataset):
    def __init__(self, examples):
        self.examples = examples

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        ex = self.examples[idx]
        return (
            ex.node_feats.clone().float(),
            ex.edge_index.clone().long(),
            torch.tensor(np.array(ex.move_feats), dtype=torch.float32),
            torch.tensor(ex.pi, dtype=torch.float32),
            torch.tensor(ex.z, dtype=torch.float32),
        )
        # return (
        #     ex.node_feats.clone().float(),
        #     ex.edge_index.clone().long(),
        #     torch.tensor(np.array(ex.move_feats), dtype=torch.float32),
        #     torch.tensor(ex.pi, dtype=torch.float32),
        #     torch.tensor(ex.z, dtype=torch.float32),
        #     ex.round_num,
        #     ex.game_length,
        #     ex.num_iterations,
        # )

    def collate_fn(batch):
        node_feats_list, edge_index_list, move_feats, probs, zs = zip(*batch)

        # ── Pack graphs into a flat PyG-style batch ──────────────────────
        node_offset = 0
        all_node_feats = []
        all_edge_index = []
        all_batch_vec  = []

        for i, (nf, ei) in enumerate(zip(node_feats_list, edge_index_list)):
            nf = nf.float()
            ei = ei.long()
            n_nodes = nf.shape[0]

            all_node_feats.append(nf)                           # (N_i, F)
            all_edge_index.append(ei + node_offset)             # shift by offset
            all_batch_vec.append(torch.full((n_nodes,), i, dtype=torch.long))

            node_offset += n_nodes

        batched_node_feats = torch.cat(all_node_feats, dim=0)   # (sum N_i, F)
        batched_edge_index = torch.cat(all_edge_index, dim=1)   # (2, sum E_i)
        batch_vec          = torch.cat(all_batch_vec,  dim=0)   # (sum N_i,)

        # ── Pad move features and policy targets ─────────────────────────
        max_moves = max(mf.shape[0] for mf in move_feats)

        padded_feats = torch.zeros(len(batch), max_moves, move_feats[0].shape[1])
        padded_probs = torch.zeros(len(batch), max_moves)
        mask         = torch.zeros(len(batch), max_moves, dtype=torch.bool)

        for i, (mf, pr) in enumerate(zip(move_feats, probs)):
            mf = mf.float()
            pr = pr.float()
            n = mf.shape[0]
            padded_feats[i, :n] = mf
            padded_probs[i, :n] = pr
            mask[i, :n]         = True

        # 7-tuple: node_feats, edge_index, batch_vec,
        #          move_feats, probs, zs, mask
        return (
            batched_node_feats,
            batched_edge_index,
            batch_vec,
            padded_feats,
            padded_probs,
            torch.tensor(zs, dtype=torch.float32),
            mask,
        )