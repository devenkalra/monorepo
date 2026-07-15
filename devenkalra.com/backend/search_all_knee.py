import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for "knee" and print sections that look like model objects or logs
print("=== Matches for 'knee' ===")
for m in re.finditer(r"knee", content, re.IGNORECASE):
    start = max(0, m.start() - 150)
    end = min(len(content), m.end() + 150)
    print(repr(content[start:end]))
    print("-" * 50)
