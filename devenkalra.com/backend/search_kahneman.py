import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

terms = ["Kahneman", "System 1", "System 2", "Cognitive", "heuristics", "anchoring", "loss aversion", "prospect theory"]

print("=== SEARCH RESULTS FOR THINKING, FAST AND SLOW TERMS ===")
for term in terms:
    matches = list(re.finditer(re.escape(term), content, re.IGNORECASE))
    print(f"Term '{term}': {len(matches)} matches")
    for m in matches[:5]:
        start = max(0, m.start() - 100)
        end = min(len(content), m.end() + 200)
        print(f"  Match at index {m.start()}:")
        print(repr(content[start:end]))
        print("-" * 30)
