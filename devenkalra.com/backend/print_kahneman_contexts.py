import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

for m in re.finditer(r"Kahneman", content, re.IGNORECASE):
    print(f"=== Kahneman at index {m.start()} ===")
    start = max(0, m.start() - 500)
    end = min(len(content), m.end() + 1500)
    print(content[start:end])
    print("=" * 60)
