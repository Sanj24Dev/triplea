from collections import deque
from dataclasses import dataclass
import random
import numpy as np
from torch.utils.data import Dataset
import torch


@dataclass
class SelfPlayExample:
    state_tensor: np.ndarray
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
        # evict oldest if over capacity
        if len(self.buffer) > self.max_size:
            self.buffer = self.buffer[-self.max_size:]  # keep newest

    def __len__(self):
        return len(self.buffer)

    def sample(self, n):
        examples = list(self.buffer)
        
        weights = []
        for ex in examples:
            # quality weight — more iterations = more reliable policy target
            quality = min(1.0, ex.num_iterations / 1000)
            
            # representation weight — short game players underrepresented
            representation = 1.0 / ex.game_length
            
            w = quality * representation
            weights.append(w)
        
        total = sum(weights)
        weights = [w / total for w in weights]
        n = min(n, len(examples))
        replace = n > len(examples)
        
        indices = np.random.choice(len(examples), size=n, replace=replace, p=weights)
        return [examples[i] for i in indices]
    
    # def sample(self, n):
    #     examples = list(self.buffer)
        
    #     # Short games weighted more — their examples are underrepresented
    #     weights = [1.0 / ex.game_length for ex in examples]
    #     total   = sum(weights)
    #     weights = [w / total for w in weights]

    #     n = min(n, len(examples))  # cap n
    #     replace = n > len(examples)  # only replace if we have to
    
    #     indices = np.random.choice(len(examples), size=n, 
    #                            replace=replace, p=weights)

    #     return [examples[i] for i in indices]
    
class SelfPlayDataset(Dataset):
    def __init__(self, examples):
        self.examples = examples

    def __len__(self):
        return len(self.examples)
    
    def __getitem__(self, idx):
        ex = self.examples[idx]
        return (
            torch.tensor(ex.state_tensor, dtype=torch.float32),
            torch.tensor(np.array(ex.move_feats), dtype=torch.float32),
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


