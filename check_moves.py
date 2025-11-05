import json

def check_dataset_integrity(filepath):
    invalid_records = []
    total = 0
    valid = 0

    with open(filepath, "r") as f:
        for i, line in enumerate(f, start=1):
            try:
                record = json.loads(line)
                legal_moves = record.get("legal_moves", [])
                chosen_move = record.get("chosen_move")

                # chosen_move can be a list or a single item
                if isinstance(chosen_move, list):
                    all_valid = all(m in legal_moves for m in chosen_move)
                else:
                    all_valid = chosen_move in legal_moves

                if all_valid:
                    valid += 1
                else:
                    invalid_records.append({
                        "line": i,
                        "chosen_move": chosen_move,
                        "legal_moves": legal_moves
                    })

                total += 1

            except json.JSONDecodeError as e:
                print(f"⚠️ Skipping line {i}: invalid JSON ({e})")

    print(f"\n✅ Checked {total} records.")
    print(f"✔️  Valid: {valid}")
    print(f"❌ Invalid: {len(invalid_records)}")

    if invalid_records:
        print("\nInvalid records:")
        for rec in invalid_records[:5]:  # show first 5 for brevity
            print(f"  Line {rec['line']}: chosen={rec['chosen_move']}, legal={rec['legal_moves']}")

    return invalid_records


if __name__ == "__main__":
    filepath = "1purchase_dataset.jsonl"
    invalid = check_dataset_integrity(filepath)
    if invalid:
        print("\n⚠️ Some records have chosen moves not in their legal moves.")
    else:
        print("\n✅ All chosen moves are valid.")
