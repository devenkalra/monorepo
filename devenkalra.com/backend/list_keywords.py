import os
import re

recovered_file_path = r"C:\Users\deven\.gemini\antigravity-ide\brain\df25b910-3abd-4651-bd68-259c66f2e562\recovered_db_data.txt"

with open(recovered_file_path, "r", encoding="utf-8") as f:
    content = f.read()

pattern_keyword = re.compile(r"^===\s*KEYWORD:\s*(.*?)\s*===$", re.MULTILINE)
matches = pattern_keyword.findall(content)
print("All keywords in recovered_db_data.txt:")
for m in sorted(list(set(matches))):
    print("-", m)
