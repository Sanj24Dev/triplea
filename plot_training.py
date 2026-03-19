import torch
import pandas as pd
import matplotlib.pyplot as plt

# ---- Load checkpoint ----
ckpt = torch.load("self_play_model/checkpoints/cnn/latest.pt", map_location="cpu")

history = ckpt["history"]

state_dict = ckpt["model_state_dict"]
total = sum(p.numel() for p in state_dict.values())
print(f"Total parameters: {total:,}")

# Convert to dataframe
df = pd.DataFrame(history)
# print(df.head())

print("Loaded iterations:", len(df))

# Optional smoothing
df_smooth = df.rolling(10).mean()
# df_smooth = df

# ---- Plot ----
fig, axes = plt.subplots(3, 2, figsize=(12, 10))

axes[0,0].plot(df["iter"], df_smooth["policy_loss"])
axes[0,0].set_title("Policy Loss")

axes[0,1].plot(df["iter"], df_smooth["value_loss"])
axes[0,1].set_title("Value Loss")

axes[1,0].plot(df["iter"], df_smooth["pi_entropy"])
axes[1,0].set_title("Policy Entropy")

axes[1,1].plot(df["iter"], df_smooth["v_mean"], label="Value Mean")
axes[1,1].plot(df["iter"], df_smooth["v_std"], label="Value Std")
axes[1,1].legend()
axes[1,1].set_title("Value Statistics")

axes[2,0].plot(df["iter"], df_smooth["grad_norm"])
axes[2,0].set_title("Gradient Norm")

axes[2,1].plot(df["iter"], df_smooth["lr"])
axes[2,1].set_title("Learning Rate")

for ax in axes.flat:
    ax.set_xlabel("Iteration")
    ax.grid(True)

plt.tight_layout()
plt.show()