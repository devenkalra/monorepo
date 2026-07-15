import os
import re

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"
files = os.listdir(dumped_dir)

def read_file(name):
    with open(os.path.join(dumped_dir, name), "r", encoding="utf-8") as f:
        return f.read()

# Let's look at Die With Zero blocks
die_blocks = sorted([f for f in files if "die" in f.lower() and f.endswith(".txt") and os.path.getsize(os.path.join(dumped_dir, f)) > 100],
                    key=lambda x: int(x.split("_")[-1].replace(".txt", "") if "_" in x and x.split("_")[-1].replace(".txt", "").isdigit() else 0))

print(f"=== DIE WITH ZERO BLOCKS ({len(die_blocks)}) ===")
for db in die_blocks[:10]: # Print first 10 blocks info
    print(f"Block: {db}")
    content = read_file(db)
    print("  Preview:", repr(content[:150]))
    print("  Tail:", repr(content[-150:]))
