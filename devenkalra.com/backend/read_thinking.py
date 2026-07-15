import os

dumped_dir = r"c:\code\devenkalra.com\backend\dumped_data"
files = os.listdir(dumped_dir)

def read_file(name):
    with open(os.path.join(dumped_dir, name), "r", encoding="utf-8") as f:
        return f.read()

thinking_files = [f for f in files if "thinking" in f.lower() and f.endswith(".txt") and os.path.getsize(os.path.join(dumped_dir, f)) > 100]

for tf in thinking_files:
    print(f"==================================================")
    print(f"FILE: {tf} (length: {len(read_file(tf))})")
    print(f"==================================================")
    print(read_file(tf))
    print("\n\n")
