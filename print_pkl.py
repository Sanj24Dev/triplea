import pickle
from pprint import pprint

with open("self_play_model/checkpoints/cnn/shared_buffer.pkl", "rb") as f:
    data = pickle.load(f)

print("Type:", type(data))

if isinstance(data, dict):
    print("Keys:", data.keys())
elif isinstance(data, list):
    print("Length:", len(data))

pprint(data)