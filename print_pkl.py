import pickle
from pprint import pprint

data = []

with open("self_play_model/checkpoints/cnn/shared_buffer_5000.pkl", "rb") as f:
    d = pickle.load(f)
data.extend(d)

with open("self_play_model/checkpoints/cnn/shared_buffer_5001.pkl", "rb") as f:
    d = pickle.load(f)
data.extend(d)

with open("self_play_model/checkpoints/cnn/shared_buffer_5002.pkl", "rb") as f:
    d = pickle.load(f)
data.extend(d)

with open("self_play_model/checkpoints/cnn/shared_buffer_5003.pkl", "rb") as f:
    d = pickle.load(f)
data.extend(d)

print("Type:", type(data))

if isinstance(data, dict):
    print("Keys:", data.keys())
elif isinstance(data, list):
    print("Length:", len(data))

pprint(data)


# import torch

# ckpt = torch.load("self_play_model/checkpoints/cnn/latest.pt", map_location="cpu")

# print(type(ckpt))
# print(ckpt.keys())
