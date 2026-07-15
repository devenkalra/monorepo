import os

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"
files = os.listdir(dumped_dir)

# Read file
def read_file(name):
    with open(os.path.join(dumped_dir, name), "r", encoding="utf-8") as f:
        return f.read()

# Filter files related to knee exercises
knee_files = [f for f in files if "knee" in f.lower()]

# We want to see the ending of the files that seem to start with Knee Exercises content but might go further.
# Let's search for "joint safety" or "sharp, localized pain" in all knee files.
for kf in knee_files:
    content = read_file(kf)
    if "safety" in content.lower() or "sharp" in content.lower() or "experience" in content.lower():
        print(f"==================================================")
        print(f"FILE: {kf} (length: {len(content)})")
        print(f"==================================================")
        # Find where "sharp" occurs
        idx = content.lower().find("sharp")
        if idx != -1:
            print(content[idx-100:idx+400])
        else:
            print(content[:500])
        print("\n\n")
