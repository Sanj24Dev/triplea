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
