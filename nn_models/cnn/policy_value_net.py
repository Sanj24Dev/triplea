import torch.nn as nn
import torch.nn.functional as F
import torch

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

class PolicyValueNet(nn.Module):
    def __init__(self, in_channels, grid_shape, num_actions, num_filters, num_res_blocks):
        super().__init__()
        self.grid_shape = grid_shape
        self.num_actions = num_actions
        H, W = self.grid_shape

        self.input_conv = nn.Sequential(
            nn.Conv2d(in_channels, num_filters, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(num_filters),
            nn.ReLU(),
        )

        self.res_blocks = nn.Sequential(*[ResidualBlock(num_filters) for _ in range(num_res_blocks)])

        self.policy_conv = nn.Sequential(
            nn.Conv2d(num_filters, 2, kernel_size=1, bias=False),
            nn.BatchNorm2d(2),
            nn.ReLU(),
            nn.Flatten(),
        )
        self.policy_fc = nn.Linear(2 * H * W, num_actions)        

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
    
    def forward(self, x):
        x = self.input_conv(x)
        x = self.res_blocks(x)

        log_p = F.log_softmax(self.policy_fc(self.policy_conv(x)), dim=1)
        v = self.value_fc(self.value_conv(x)).squeeze(-1)
        return log_p, v
    
    @torch.no_grad()
    def predict(self, state_tensor, device="cpu"):
        self.eval()
        x = state_tensor.unsqueeze(0).to(device)  
        log_p, v = self.forward(x)
        return log_p.exp().squeeze(0).cpu().numpy(), v.item()
        