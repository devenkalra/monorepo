import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"
output_dir = r"c:\code\devenkalra.com\backend\dumped_data"
os.makedirs(output_dir, exist_ok=True)

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

pattern_keyword = re.compile(r"^===\s*KEYWORD:\s*(.*?)\s*===$")
pattern_offset = re.compile(r"^Offset\s*(\d+):$")

lines = content.split("\n")
current_keyword = None
current_offset = None
current_lines = []

for line in lines:
    kw_match = pattern_keyword.match(line)
    if kw_match:
        # Save previous block if any
        if current_keyword and current_lines:
            safe_kw = re.sub(r'[^a-zA-Z0-9_-]', '_', current_keyword)
            out_file = os.path.join(output_dir, f"{safe_kw}_{current_offset}.txt")
            with open(out_file, "w", encoding="utf-8") as out_f:
                out_f.write("\n".join(current_lines))
            current_lines = []
        
        current_keyword = kw_match.group(1).strip()
        current_offset = None
        continue
    
    if current_keyword:
        if line.startswith("------------------------------"):
            if current_lines:
                safe_kw = re.sub(r'[^a-zA-Z0-9_-]', '_', current_keyword)
                out_file = os.path.join(output_dir, f"{safe_kw}_{current_offset}.txt")
                with open(out_file, "w", encoding="utf-8") as out_f:
                    out_f.write("\n".join(current_lines))
                current_lines = []
                current_offset = None
        else:
            off_match = pattern_offset.match(line)
            if off_match:
                current_offset = off_match.group(1)
            else:
                current_lines.append(line)

# Handle the last block
if current_keyword and current_lines:
    safe_kw = re.sub(r'[^a-zA-Z0-9_-]', '_', current_keyword)
    out_file = os.path.join(output_dir, f"{safe_kw}_{current_offset}.txt")
    with open(out_file, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(current_lines))

print("Dumped all blocks into", output_dir)
print("Files created:")
for f in os.listdir(output_dir):
    print("-", f, os.path.getsize(os.path.join(output_dir, f)), "bytes")
