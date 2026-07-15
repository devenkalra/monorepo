import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for "knee" and find surrounding text (approx 500 chars before/after)
for m in re.finditer(r"knee-exercises", content, re.IGNORECASE):
    start = max(0, m.start() - 300)
    end = min(len(content), m.end() + 300)
    print(f"Match at index {m.start()}:")
    print(repr(content[start:end]))
    print("=" * 60)
