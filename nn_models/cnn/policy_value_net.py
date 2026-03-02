import torch.nn as nn
import torch.nn.functional as F
import torch
import numpy as np

class ResidualBlock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x):
        residual = x
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.bn2(self.conv2(x))
        return F.relu(x + residual)

MOVE_FEAT_DIM = 6  # matches your encode_move_features output size

class PolicyValueNet(nn.Module):
    def __init__(self, in_channels, grid_shape, num_filters, num_res_blocks, move_feat_dim=MOVE_FEAT_DIM):
        super().__init__()
        # num_actions is GONE — no longer needed
        self.grid_shape = grid_shape
        H, W = grid_shape

        # Shared tower — unchanged
        self.input_conv = nn.Sequential(
            nn.Conv2d(in_channels, num_filters, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(num_filters),
            nn.ReLU(),
        )
        self.res_blocks = nn.Sequential(*[ResidualBlock(num_filters) for _ in range(num_res_blocks)])

        # Policy head — produces state embedding instead of fixed logits
        self.policy_conv = nn.Sequential(
            nn.Conv2d(num_filters, 2, kernel_size=1, bias=False),
            nn.BatchNorm2d(2),
            nn.ReLU(),
            nn.Flatten(),
        )
        self.state_embedding_fc = nn.Sequential(
            nn.Linear(2 * H * W, 128),
            nn.ReLU(),
        )

        # Move scorer — combines state embedding + move features → scalar score
        self.move_scorer = nn.Sequential(
            nn.Linear(128 + move_feat_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

        # Value head — unchanged
        self.value_conv = nn.Sequential(
            nn.Conv2d(num_filters, 1, kernel_size=1, bias=False),
            nn.BatchNorm2d(1),
            nn.ReLU(),
            nn.Flatten(),
        )
        self.value_fc = nn.Sequential(
            nn.Linear(H * W, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Tanh(),
        )

    def get_state_embedding(self, x):
        """Shared tower → state embedding vector."""
        x = self.input_conv(x)
        x = self.res_blocks(x)
        return self.state_embedding_fc(self.policy_conv(x))  # (B, 128)

    def score_move(self, state_tensor, move_feat, device="cpu"):
        """Score a single move given state. Used in get_priors."""
        self.eval()
        with torch.no_grad():
            x   = state_tensor.unsqueeze(0).to(device)
            emb = self.get_state_embedding(x)                          # (1, 128)
            mf  = torch.tensor(move_feat, dtype=torch.float32).unsqueeze(0).to(device)  # (1, 6)
            score = self.move_scorer(torch.cat([emb, mf], dim=-1))     # (1, 1)
        return score.item()

    def score_moves_batch(self, state_tensor, move_feats_list, device="cpu"):
        """
        Score all legal moves in one forward pass — much faster than calling
        score_move in a loop during get_priors.
        move_feats_list: list of np.ndarray, each shape (move_feat_dim,)
        """
        self.eval()
        with torch.no_grad():
            x   = state_tensor.unsqueeze(0).to(device)
            emb = self.get_state_embedding(x)                          # (1, 128)
            emb = emb.expand(len(move_feats_list), -1)                 # (N, 128)
            mf  = torch.tensor(np.stack(move_feats_list), dtype=torch.float32).to(device)  # (N, 6)
            scores = self.move_scorer(torch.cat([emb, mf], dim=-1))    # (N, 1)
        return torch.softmax(scores.squeeze(-1), dim=0).cpu().numpy()  # (N,) probs

    def predict_value(self, state_tensor, device="cpu"):
        """Value head only — used in simulate()."""
        self.eval()
        with torch.no_grad():
            x = state_tensor.unsqueeze(0).to(device)
            x = self.input_conv(x)
            x = self.res_blocks(x)
            v = self.value_fc(self.value_conv(x))
        return v.item()
    
    # def forward(self, x):
    #     x = self.input_conv(x)
    #     x = self.res_blocks(x)

    #     log_p = F.log_softmax(self.policy_fc(self.policy_conv(x)), dim=1)
    #     v = self.value_fc(self.value_conv(x)).squeeze(-1)
    #     return log_p, v
    
    # @torch.no_grad()
    # def predict(self, state_tensor, device="cpu"):
    #     self.eval()
    #     x = state_tensor.unsqueeze(0).to(device)  
    #     log_p, v = self.forward(x)
    #     return log_p.exp().squeeze(0).cpu().numpy(), v.item()
        

    # def score_move(self, state_tensor, move_feat, device):
    #     """Score a single (state, move) pair."""
    #     self.eval()
    #     with torch.no_grad():
    #         x = state_tensor.unsqueeze(0).to(device)
    #         state_emb = self.get_embedding(x)  # shared tower output, flattened
            
    #         mf = torch.tensor(move_feat).unsqueeze(0).to(device)
    #         combined = torch.cat([state_emb, mf], dim=-1)
    #         score = self.move_scorer(combined)  # small MLP head
    #     return score.item()