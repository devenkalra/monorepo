import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's search for "ideas" or "Tracking Ideas" in the content
print("=== Matches for 'Tracking Ideas' or 'projects' ===")
for m in re.finditer(r"Tracking Ideas|projects", content, re.IGNORECASE):
    # Print the surrounding block (e.g. 200 chars before/after)
    start = max(0, m.start() - 100)
    end = min(len(content), m.end() + 200)
    # Check if there is HTML or JS code in it
    snippet = content[start:end]
    if "<" in snippet or "fetch" in snippet or "function" in snippet or "table" in snippet:
        print(f"Match at index {m.start()}:")
        print(repr(snippet))
        print("-" * 50)
