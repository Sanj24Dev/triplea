import time
import numpy as np
import os
import torch
import pickle
from torch.utils.data import DataLoader
import torch.nn.functional as F
from filelock import FileLock

from combat_policy_mcts_agent import P_MCTSNode
from nn_models.data.self_play_data import SelfPlayExample, SelfPlayDataset

PORT_ENV_VARS = ("PLAYER_1_PORT", "PLAYER_2_PORT", "PLAYER_3_PORT", "PLAYER_4_PORT")
MIN_EXAMPLES_TO_TRAIN = 32


def active_ports():
    """Collect active AI ports from environment variables."""
    ports: List[int] = []
    for k in PORT_ENV_VARS:
        v = os.getenv(k)
        if not v:
            continue
        try:
            ports.append(int(v))
        except ValueError:
            print(f"[WARN] Ignoring invalid port in {k}={v!r}")
    seen = set()
    out = []
    for p in ports:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


class SelfPlayTrainer():
    def __init__(self, net,
                 buffer, save_dir="self_play_model/checkpoints/gnn", device="cpu",
                 lr=1e-3, weight_decay=1e-4, batch_size=32,
                 epochs_per_iter=1, self_play_games=20, num_iterations=100,
                 temp_threshold=15
                 ):
        self.net = net
        self.buffer = buffer
        self.save_dir = save_dir
        self.device = device
        self.batch_size = batch_size
        self.epochs_per_iter = epochs_per_iter
        self.self_play_games = self_play_games
        self.num_iterations = num_iterations
        self.temp_threshold = temp_threshold

        os.makedirs(self.save_dir, exist_ok=True)

        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, weight_decay=weight_decay)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=num_iterations)
        self.history = []

    def save_checkpoint(self, iteration, tag):
        fname = os.path.join(
            self.save_dir,
            f"model_iter{iteration:04d}{('_' + tag) if tag else ''}.pt"
        )
        torch.save({
            "iteration": iteration,
            "model_state_dict": self.net.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "history": self.history,
        }, fname)
        print(f"  Checkpoint saved -> {fname}")
        return fname

    def load_checkpoint(self, path):
        ckpt = torch.load(path, map_location=self.device)
        self.net.load_state_dict(ckpt["model_state_dict"], strict=False)
        self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        self.history = ckpt.get("history", [])
        print(f"  [Checkpoint] loaded ← {path}")
        return ckpt["iteration"]

    def self_play_iteration(self, iteration):
        ckpt_path = os.path.join(self.save_dir, "latest.pt")
        torch.save({
            "iteration": iteration,
            "model_state_dict": self.net.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "history": self.history,
        }, ckpt_path)
        print(f"Iter {iteration} weights pushed → {ckpt_path}")

    def _train_on_loader(self, loader):
        self.net.train()
        total_policy_loss = 0.0
        total_value_loss  = 0.0
        n_batches         = 0

        # ── Unpack 7-tuple from GNN collate_fn ───────────────────────────
        for node_feats, edge_index, batch_vec, move_features_batch, probs, zs, mask in loader:
            node_feats          = node_feats.to(self.device)
            edge_index          = edge_index.to(self.device)
            batch_vec           = batch_vec.to(self.device)
            move_features_batch = move_features_batch.to(self.device)
            probs               = probs.to(self.device)
            zs                  = zs.to(self.device)
            mask                = mask.to(self.device)

            # ── Forward: pass batch vector so GNN can pool per-graph ─────
            log_p, v = self.net(node_feats, edge_index, move_features_batch, batch=batch_vec, mask=mask)

            policy_loss = -(torch.where(probs > 0, probs * log_p, torch.zeros_like(log_p))).sum(dim=-1).mean()
            value_loss  = F.mse_loss(v, zs)
            loss        = policy_loss + 0.5 * value_loss
 
            self.optimizer.zero_grad()
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(self.net.parameters(), 0.5)
            last_grad_norm = grad_norm.item()
            self.optimizer.step()

            total_policy_loss += policy_loss.item()
            total_value_loss  += value_loss.item()
            n_batches         += 1
            last_probs, last_v = probs.detach(), v.detach()

        return total_policy_loss / max(1, n_batches), total_value_loss / max(1, n_batches), last_probs, last_v, last_grad_norm

    def run(self):
        poll_interval = 300
        print("=" * 50)
        print("  Trainer process started — waiting for examples")
        print("=" * 50)

        iteration = 1

        latest = os.path.join(self.save_dir, "latest.pt")
        if os.path.exists(latest):
            self.load_checkpoint(latest)
            print(f"  Resumed from {latest}")

        while True:
            time.sleep(poll_interval)

            ports_active = active_ports()
            examples = []
            for p in ports_active:
                buffer_path = os.path.join(self.save_dir, f"shared_buffer_{p}.pkl")
                lock_path   = buffer_path + ".lock"

                with FileLock(lock_path):
                    if not os.path.exists(buffer_path):
                        continue
                    with open(buffer_path, "rb") as f:
                        ex = pickle.load(f)
                    os.remove(buffer_path)
                examples.extend(ex)

            if len(examples) == 0:
                print(f"  [Iter {iteration}] No new data, waiting...")
                continue
            self.buffer.add(examples)
            if len(self.buffer) < 1000:
                n_samples = min(len(self.buffer), 256)
                self.epochs_per_iter = 1
            elif len(self.buffer) < 5000:
                n_samples = min(len(self.buffer), 512)
                self.epochs_per_iter = 2
            else:
                n_samples = self.batch_size * 8
                self.epochs_per_iter = 3

            samples = self.buffer.sample(n_samples)
            loader  = DataLoader(
                SelfPlayDataset(samples),
                batch_size  = self.batch_size,
                shuffle     = True,
                num_workers = 0,
                collate_fn  = SelfPlayDataset.collate_fn,
            )

            pl, vl = 0.0, 0.0
            for epoch in range(self.epochs_per_iter):
                pl, vl, last_probs, last_v, grad_norm = self._train_on_loader(loader)
                self.scheduler.step()
            print(f"  [Iter {iteration}] policy_loss={pl:.4f}  value_loss={vl:.4f}  buffer={len(self.buffer)}")

            mask = last_probs > 0
            entropy_vals = []
            for i in range(last_probs.shape[0]):
                p = last_probs[i][mask[i]]
                if len(p) > 1:
                    h = -(p * torch.log(p + 1e-8)).sum()
                    h_norm = h / torch.log(torch.tensor(len(p), dtype=torch.float))
                    entropy_vals.append(h_norm.item())

            pi_entropy = np.mean(entropy_vals) if entropy_vals else 0.0
            v_std = last_v.std()
            v_mean = last_v.mean()
            current_lr = self.optimizer.param_groups[0]['lr']
            self.history.append({
                "iter": iteration,
                "policy_loss": pl,
                "value_loss": vl,
                "pi_entropy": pi_entropy.item(),
                "v_std": v_std.item(),
                "v_mean": v_mean.item(),
                "grad_norm": grad_norm,
                "lr": current_lr,
            })

            self.self_play_iteration(iteration)
            if iteration % 10 == 0:
                self.save_checkpoint(iteration, tag="")
            iteration += 1


# ── Instantiation ─────────────────────────────────────────────────────────────
from nn_models.gnn.policy_value_net import GNNPolicyValueNet
from nn_models.data.self_play_data import SelfPlayBuffer

SAVE_DIR   = "self_play_model/checkpoints/gnn"
DEVICE     = "cuda"

if __name__ == "__main__":
    net = GNNPolicyValueNet(
        node_feat_dim = 13,
        edge_feat_dim = 0,
        hidden_dim    = 64,
        num_layers    = 5,
        move_feat_dim = 7,
    ).to(DEVICE)

    buffer  = SelfPlayBuffer(max_size=20_000)
    trainer = SelfPlayTrainer(
        net             = net,
        buffer          = buffer,
        save_dir        = SAVE_DIR,
        device          = DEVICE,
        lr              = 1e-3,
        weight_decay    = 1e-3,
        batch_size      = 64,
        epochs_per_iter = 1,
        num_iterations  = 1000,
    )

    trainer.run()