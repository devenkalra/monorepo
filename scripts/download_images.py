import os
import requests
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# -------- CONFIG --------
URL_FILE = "urls.txt"
OUTPUT_DIR = "images"
TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ImageDownloader/1.0)"
}
# ------------------------

Path(OUTPUT_DIR).mkdir(exist_ok=True)

seen = set()

def is_valid_http_url(url):
    return url.startswith("http://") or url.startswith("https://")

with open(URL_FILE, "r", encoding="utf-8") as f:
    urls = [line.strip() for line in f if line.strip()]

for url in urls:
    # Skip data: URLs (SVGs, inline images)
    if not is_valid_http_url(url):
        print(f"Skipping non-http URL")
        continue

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)

    # Skip if no filename
    if not filename:
        continue

    # Add size suffix (im_w) to avoid overwriting
    qs = parse_qs(parsed.query)
    size = qs.get("im_w", ["orig"])[0]

    name, ext = os.path.splitext(filename)
    final_name = f"{name}_{size}{ext}"
    out_path = os.path.join(OUTPUT_DIR, final_name)

    # De-duplicate downloads
    if final_name in seen:
        continue
    seen.add(final_name)

    try:
        print(f"Downloading {final_name}")
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()

        with open(out_path, "wb") as f:
            f.write(r.content)

    except Exception as e:
        print(f"Failed: {url} ({e})")

print("Done.")
