import torch_geometric.nn as pyg_nn
import torch.nn as nn
import torch.nn.functional as F
import torch
import numpy as np

class GNNPolicyValueNet(nn.Module):
    def __init__(self, node_feat_dim, edge_feat_dim, hidden_dim, num_layers, move_feat_dim):
        super().__init__()

        # GNN tower — replaces CNN + residual blocks
        self.gnn_layers = nn.ModuleList([
            pyg_nn.GATConv(
                node_feat_dim if i == 0 else hidden_dim,
                hidden_dim,
                heads=4,
                concat=False,   # average heads → hidden_dim
            )
            for i in range(num_layers)
        ])
        self.bns = nn.ModuleList([
            nn.BatchNorm1d(hidden_dim) for _ in range(num_layers)
        ])

        # Global graph embedding for value head — pool all nodes
        self.global_pool_fc = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
        )

        # State embedding for policy head — same as before
        self.state_embedding_fc = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
        )

        # Move scorer — unchanged from CNN version
        self.move_scorer = nn.Sequential(
            nn.Linear(128 + move_feat_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

        # Value head — unchanged
        self.value_fc = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Tanh(),
        )

    # def get_graph_embedding(self, node_feats, edge_index, batch=None):
    #     """
    #     node_feats: (N_nodes, node_feat_dim)
    #     edge_index: (2, E)
    #     batch:      (N_nodes,) — which graph each node belongs to (for batching)
    #     Returns:    (B, hidden_dim) — one embedding per graph
    #     """
    #     x = node_feats
    #     for gnn, bn in zip(self.gnn_layers, self.bns):
    #         x = F.relu(bn(gnn(x, edge_index)))
        
    #     # Pool all node embeddings → single graph embedding
    #     # Mean pool: (N_nodes, hidden) → (B, hidden)
    #     x = pyg_nn.global_mean_pool(x, batch)
    #     return x

    def get_state_embedding(self, node_feats, edge_index, batch=None):
        graph_emb = self.get_graph_embedding(node_feats, edge_index, batch)
        return self.state_embedding_fc(graph_emb)   # (B, 128)

    def get_graph_embedding(self, node_feats, edge_index, batch=None):
        x = node_feats

        for gnn, bn in zip(self.gnn_layers, self.bns):
            x = F.relu(bn(gnn(x, edge_index)))

        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        x = pyg_nn.global_mean_pool(x, batch)
        return x

    # def score_moves_batch(self, node_feats, edge_index, move_feats_list, device="cpu"):
    #     """Inference — same interface as CNN version."""
    #     self.eval()
    #     with torch.no_grad():
    #         emb = self.get_state_embedding(node_feats, edge_index)     # (1, 128)
    #         emb = emb.expand(len(move_feats_list), -1)                 # (N, 128)
    #         mf  = torch.tensor(np.stack(move_feats_list), dtype=torch.float32).to(device)
    #         scores = self.move_scorer(torch.cat([emb, mf], dim=-1))
    #     return torch.softmax(scores.squeeze(-1), dim=0).cpu().numpy()


    def score_moves_batch(self, node_feats, edge_index, move_feats_list, device="cpu"):
        self.eval()
        device = next(self.parameters()).device 

        with torch.no_grad():
            node_feats = node_feats.to(device)
            edge_index = edge_index.to(device)

            emb = self.get_state_embedding(node_feats, edge_index)  # (1, 128)
            emb = emb.expand(len(move_feats_list), -1)

            mf = torch.tensor(np.stack(move_feats_list), dtype=torch.float32, device=device)

            scores = self.move_scorer(torch.cat([emb, mf], dim=-1))

        return torch.softmax(scores.squeeze(-1), dim=0).cpu().numpy()

    # def predict_value(self, node_feats, edge_index, device="cpu"):
    #     """Inference — value only."""
    #     self.eval()
    #     with torch.no_grad():
    #         graph_emb = self.get_graph_embedding(node_feats, edge_index)
    #         v = self.value_fc(self.global_pool_fc(graph_emb))
    #     return v.item()

    def predict_value(self, node_feats, edge_index, device="cpu"):
        self.eval()
        device = next(self.parameters()).device

        with torch.no_grad():
            node_feats = node_feats.to(device)
            edge_index = edge_index.to(device)

            graph_emb = self.get_graph_embedding(node_feats, edge_index)
            v = self.value_fc(self.global_pool_fc(graph_emb))

        return v.item()

    def forward(self, node_feats, edge_index, move_features_batch, batch=None, mask=None):
        """Training forward pass."""
        graph_emb = self.get_graph_embedding(node_feats, edge_index, batch)  # (B, hidden)

        # Policy
        emb = self.state_embedding_fc(graph_emb)                             # (B, 128)
        N   = move_features_batch.shape[1]
        emb_expanded = emb.unsqueeze(1).expand(-1, N, -1)                    # (B, N, 128)
        combined = torch.cat([emb_expanded, move_features_batch], dim=-1)    # (B, N, 134)
        scores   = self.move_scorer(combined).squeeze(-1)                    # (B, N)
        if mask is not None:
            scores = scores.masked_fill(~mask, float("-inf"))
        log_p = F.log_softmax(scores, dim=-1)                                # (B, N)

        # Value
        v = self.value_fc(self.global_pool_fc(graph_emb)).squeeze(-1)        # (B,)

        return log_p, v