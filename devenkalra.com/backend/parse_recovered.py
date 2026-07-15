import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

if not os.path.exists(recovered_file_path):
    print("File not found:", recovered_file_path)
    exit(1)

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

keywords_data = {}
current_keyword = None
current_offset = None
current_lines = []

pattern_keyword = re.compile(r"^===\s*KEYWORD:\s*(.*?)\s*===$")
pattern_offset = re.compile(r"^Offset\s*(\d+):$")

lines = content.split("\n")
for i, line in enumerate(lines):
    kw_match = pattern_keyword.match(line)
    if kw_match:
        current_keyword = kw_match.group(1).strip()
        keywords_data[current_keyword] = []
        continue
    
    if current_keyword:
        if line.startswith("------------------------------"):
            if current_lines:
                keywords_data[current_keyword].append((current_offset, "\n".join(current_lines)))
                current_lines = []
                current_offset = None
        else:
            off_match = pattern_offset.match(line)
            if off_match:
                current_offset = off_match.group(1)
            else:
                current_lines.append(line)

print("Found keywords:")
for kw, blocks in keywords_data.items():
    print(f"Keyword: {kw} - {len(blocks)} blocks")
    for offset, blk in blocks:
        # Print block preview
        lines_in_blk = blk.split("\n")
        print(f"  Offset: {offset} ({len(lines_in_blk)} lines) - Preview: {repr(blk[:100])}")
