p = "[INFO] Game stopped [PlayerId named: Chinese]"
parts = p.strip().split(" ")
print(parts[5].split("]")[0])