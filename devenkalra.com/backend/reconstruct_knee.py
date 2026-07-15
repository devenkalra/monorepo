import os

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"
files = os.listdir(dumped_dir)

# Read file
def read_file(name):
    with open(os.path.join(dumped_dir, name), "r", encoding="utf-8") as f:
        return f.read()

# Filter files related to knee exercises
knee_files = [f for f in files if "knee" in f.lower()]
print("Found knee files:", knee_files)

# Print non-empty knee files contents
for kf in knee_files:
    content = read_file(kf)
    if len(content) > 100:
        print(f"==================================================")
        print(f"FILE: {kf} (length: {len(content)})")
        print(f"==================================================")
        print(content)
        print("\n\n")
