import os
import re

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"
files = os.listdir(dumped_dir)

# Select all Die With Zero blocks from Group B (offsets >= 993000)
db_blocks = []
for f in files:
    if "die" in f.lower() and f.endswith(".txt"):
        parts = f.split("_")
        offset_str = parts[-1].replace(".txt", "")
        if offset_str.isdigit():
            offset = int(offset_str)
            if offset >= 993000:
                db_blocks.append((offset, f))

# Sort by offset
db_blocks.sort()

print(f"Sorting {len(db_blocks)} blocks:")
stitched_content = ""
for offset, fname in db_blocks:
    print(f"- {fname} (offset: {offset})")
    with open(os.path.join(dumped_dir, fname), "r", encoding="utf-8") as file:
        content = file.read()
    
    # We want to clean up SQLite page markers or system logs if any are in the block.
    # In SQLite page text, there might be null bytes, but they are already converted or removed.
    # Let's inspect the block transition.
    stitched_content += content + "\n"

output_path = r"c:\code\devenkalra.com\backend\stitched_dwz.html"
with open(output_path, "w", encoding="utf-8") as out:
    out.write(stitched_content)

print(f"Stitched file saved to {output_path} (size: {len(stitched_content)} bytes)")
