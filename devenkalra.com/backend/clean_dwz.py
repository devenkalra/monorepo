import re

input_path = r"c:\code\devenkalra.com\backend\stitched_dwz.html"
with open(input_path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's inspect non-ascii or binary characters if any
print("Length of text:", len(text))

# Let's see all unique HTML headers or titles in it
headers = re.findall(r"<h\d.*?>.*?</h\d>", text, re.IGNORECASE)
print(f"Found {len(headers)} headings:")
for h in headers[:20]:
    print("  ", h)

# Let's write a regex that matches only the HTML structure inside the <div id="my-body"> ... </div>
# Wait, let's see where <div id="my-body"> starts and where it ends, or if there are multiple.
body_starts = [m.start() for m in re.finditer(r'<div\s+id="my-body">', text, re.IGNORECASE)]
print("my-body starts at:", body_starts)

# Let's print the first 1000 chars of the first <div id="my-body">
if body_starts:
    print("=== FIRST BODY PREVIEW ===")
    print(text[body_starts[0]:body_starts[0]+1000])
