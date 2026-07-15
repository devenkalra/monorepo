import os
import re

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"

# Let's inspect files in dumped_dir
files = os.listdir(dumped_dir)

# Helper to find file content
def read_file(name):
    with open(os.path.join(dumped_dir, name), "r", encoding="utf-8") as f:
        return f.read()

# Let's print out information about Knee Exercises
knee_files = [f for f in files if "knee" in f.lower()]
print("KNEE EXERCISE FILES:")
for kf in sorted(knee_files, key=lambda x: os.path.getsize(os.path.join(dumped_dir, x)), reverse=True):
    content = read_file(kf)
    print(f"- {kf} (size: {len(content)}):")
    # print first 300 chars and last 300 chars
    print("  START:", repr(content[:200]))
    print("  END:", repr(content[-200:]))
    print()

# Let's print out information about Thinking Fast and Slow
thinking_files = [f for f in files if "thinking" in f.lower()]
print("THINKING FAST AND SLOW FILES:")
for tf in sorted(thinking_files, key=lambda x: os.path.getsize(os.path.join(dumped_dir, x)), reverse=True):
    content = read_file(tf)
    print(f"- {tf} (size: {len(content)}):")
    print("  START:", repr(content[:200]))
    print("  END:", repr(content[-200:]))
    print()

# Let's print out information about Die With Zero
die_files = [f for f in files if "die" in f.lower()]
print("DIE WITH ZERO FILES:")
# Print the top 3 largest
for df in sorted(die_files, key=lambda x: os.path.getsize(os.path.join(dumped_dir, x)), reverse=True)[:5]:
    content = read_file(df)
    print(f"- {df} (size: {len(content)}):")
    print("  START:", repr(content[:200]))
    print("  END:", repr(content[-200:]))
    print()
