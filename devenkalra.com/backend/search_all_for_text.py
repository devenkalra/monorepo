import os

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for occurrences of "try to stan" or "try to stand" or "stan" or "stand"
# to find if there is a continuation block.
import re
for m in re.finditer(r"try\s+to\s+stan[a-z]*", content, re.IGNORECASE):
    start = max(0, m.start() - 200)
    end = min(len(content), m.end() + 500)
    print(f"Match at index {m.start()}:")
    print(content[start:end])
    print("=" * 60)
