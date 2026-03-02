import time
import numpy as np
import os
import torch
import pickle
from torch.utils.data import DataLoader
import torch.nn.functional as F

from combat_policy_mcts_agent import P_MCTSNode
from nn_models.data.self_play_data import SelfPlayExample, SelfPlayDataset

class SelfPlayTrainer():
    def __init__(self, net,
                #  mcts_factory, state_factory,
                buffer, save_dir="self_play_model/checkpoints/cnn", device="cpu", 
                lr=1e-3, weight_decay=1e-4, batch_size=64, 
                epochs_per_iter=5, self_play_games=20, num_iterations=100,
                temp_threshold=15
                ):
        self.net = net
        # self.mcts_factory = self.mcts_factory
        # self.state_factory = self.state_factory
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
        print(f"  Checkoint saved -> {fname}")
        return fname

    def load_checkpoint(self, path):
        ckpt = torch.load(path, map_location=self.device)
        self.net.load_state_dict(ckpt["model_state_dict"])
        self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        self.history = ckpt.get("history", [])
        print(f"  [Checkpoint] loaded ← {path}")
        return ckpt["iteration"]
 
    def self_play_iteration(self, iteration):
        ckpt_path = os.path.join(self.save_dir, "latest.pt")
        torch.save(self.net.state_dict(), ckpt_path)
        print(f"Iter {iteration} weights pushed")

    def train_epoch(self):
        self.net.train()
        buffer_path = os.path.join(self.save_dir, "shared_buffer.pkl")
        lock_path = buffer_path + ".lock"

        while os.path.exists(lock_path):
            time.sleep(0.05)
        
        if not os.path.exists(buffer_path):
            return 0.0, 0.0

        open(lock_path, "w").close()    # lock
        with open(buffer_path, "rb") as f:
            examples = pickle.load(f)
        os.remove(lock_path)            # unlock

        if len(examples) < self.batch_size:
            return 0.0, 0.0
        
        self.buffer.add(examples)
        samples = self.buffer.sample(self.batch_size * 10)
        loader = DataLoader(SelfPlayDataset(samples), batch_size=self.batch_size, shuffle=True, num_workers=0, collate_fn=SelfPlayDataset.collate_fn)

        total_policy_loss = 0.0
        total_value_loss = 0.0
        n_batches = 0

        for state_tensors, move_features_batch, probs, zs in loader:
            state_tensors = state_tensors.to(self.device)
            move_features_batch = move_features_batch.to(self.device)
            probs = probs.to(self.device)
            zs = zs.to(self.device)

            log_p, v = self.net(state_tensors, move_features_batch)
            policy_loss = -(probs * log_p).sum(dim=-1).mean()
            value_loss = F.mse_loss(v, zs)
            loss = policy_loss + value_loss

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
            self.optimizer.step()

            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            n_batches += 1

        return total_policy_loss / max(1, n_batches), total_value_loss / max(1, n_batches)

    def run(self):
        poll_interval = 15
        print("=" * 50)
        print("  Trainer process started — waiting for examples")
        print("=" * 50)

        iteration = 0

        latest = os.path.join(self.save_dir, "latest.pt")
        if os.path.exists(latest):
            self.load_checkpoint(latest)
            print(f"  Resumed from {latest}")

        while True:
            time.sleep(poll_interval)
            iteration += 1

            pl, vl = 0.0, 0.0
            for epoch in range(self.epochs_per_iter):
                pl, vl = self.train_epoch()
            
            if pl == 0.0:
                print(f"  [Iter {iteration}] Buffer too small, waiting...")
                continue

            self.scheduler.step()
            print(f"  [Iter {iteration}] policy_loss={pl:.4f}  value_loss={vl:.4f}  buffer={len(self.buffer)}")

            self.history.append({
                "iter": iteration,
                "policy_loss": pl,
                "value_loss": vl,
            })

            # Push weights for agents to sync
            self.self_play_iteration(iteration)

            # Full checkpoint every 10 iters
            if iteration % 10 == 0:
                self.save_checkpoint(iteration, tag="")


from nn_models.cnn.policy_value_net import PolicyValueNet
from nn_models.data.self_play_data import SelfPlayBuffer

SAVE_DIR    = "self_play_model/checkpoints/cnn"
DEVICE      = "cpu"
GRID_SHAPE  = (9, 9)

if __name__ == "__main__":
    net = PolicyValueNet(
        in_channels   = 12,
        grid_shape    = GRID_SHAPE,
        num_filters   = 64,
        num_res_blocks= 5,
        move_feat_dim = 6,
    ).to(DEVICE)

    buffer  = SelfPlayBuffer(max_size=100_000)
    trainer = SelfPlayTrainer(
        net             = net,
        buffer          = buffer,
        save_dir        = SAVE_DIR,
        device          = DEVICE,
        lr              = 1e-3,
        weight_decay    = 1e-4,
        batch_size      = 256,
        epochs_per_iter = 5,
        num_iterations  = 1000,
    )

    trainer.run()  # blocks forever, polling for examples