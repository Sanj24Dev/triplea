from collections import deque
from dataclasses import dataclass
import random
import numpy as np
from torch.utils.data import Dataset
import torch


@dataclass
class SelfPlayExample:
    state_tensor: np.ndarray
    pi: np.ndarray
    z: float

class SelfPlayBuffer:
    def __init__(self, max_size=50000):
        self.buffer = deque(maxlen=max_size)
        self.max_size = max_size

    def add(self, examples):
        self.buffer.extend(examples)

    def __len__(self):
        return len(self.buffer)
    
    def sample(self, n):
        return random.sample(self.buffer, min(n, len(self.buffer)))
    
class SelfPlayDataset(Dataset):
    def __init__(self, examples):
        self.examples = examples

    def __len__(self):
        return len(self.examples)
    
    def __getitem__(self, idx):
        ex = self.examples[idx]
        return (
            torch.tensor(ex.state_tensor, dtype=torch.float32),
            torch.tensor(ex.pi, dtype=torch.float32),
            torch.tensor(ex.z, dtype=torch.float32),
        )

    def collate_fn(batch):
        states, move_feats, probs, zs = zip(*batch)
        
        # Pad move_feats and probs to max number of moves in this batch
        max_moves = max(mf.shape[0] for mf in move_feats)
        
        padded_feats = torch.zeros(len(batch), max_moves, move_feats[0].shape[1])
        padded_probs = torch.zeros(len(batch), max_moves)
        mask         = torch.zeros(len(batch), max_moves, dtype=torch.bool)
        
        for i, (mf, pr) in enumerate(zip(move_feats, probs)):
            n = mf.shape[0]
            padded_feats[i, :n] = mf
            padded_probs[i, :n] = pr
            mask[i, :n]         = True
        
        return torch.stack(states), padded_feats, padded_probs, torch.tensor(zs), mask


