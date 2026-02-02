#!/usr/bin/env python3
"""
Find similar/duplicate images in a folder using perceptual hashing (pHash).

Examples:
  python find_similar_images.py /path/to/photos --threshold 6
  python find_similar_images.py . --threshold 4 --extensions jpg jpeg png heic
  python find_similar_images.py . --json results.json

Notes:
- Lower threshold => stricter (more exact duplicates). Typical: 4-10.
- For large folders, this is O(n^2) comparisons; for very large sets, consider the "bucket" optimization.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageFile
import imagehash
from tqdm import tqdm
import datetime

ImageFile.LOAD_TRUNCATED_IMAGES = True


@dataclass(frozen=True)
class ImgHash:
    path: str
    phash: str
    width: int
    height: int
    size_bytes: int
    mtime: float



def iter_images(root: Path, extensions: List[str], recursive: bool) -> List[Path]:
    exts = {("." + e.lower().lstrip(".")) for e in extensions}
    if recursive:
        paths = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    else:
        paths = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return sorted(paths)


def compute_phash(path: Path, hash_size: int = 16):
    stat = path.stat()
    with Image.open(path) as im:
        im = im.convert("RGB")
        width, height = im.size
        h = imagehash.phash(im, hash_size=hash_size)

    return {
        "phash": str(h),
        "width": width,
        "height": height,
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
    }



def hamming_distance(hash_a: str, hash_b: str) -> int:
    # imagehash can parse from hex via hex_to_hash
    a = imagehash.hex_to_hash(hash_a)
    b = imagehash.hex_to_hash(hash_b)
    return (a - b)  # overloaded: returns Hamming distance


def union_find(n: int):
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            parent[ra] = rb
        elif rank[ra] > rank[rb]:
            parent[rb] = ra
        else:
            parent[rb] = ra
            rank[ra] += 1

    return find, union

def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}PB"


def human_time(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

def main():
    ap = argparse.ArgumentParser(description="Find similar images in a folder using perceptual hashing.")
    ap.add_argument("folder", type=str, help="Folder containing images")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument("--threshold", type=int, default=6, help="Max Hamming distance to consider images similar (default: 6)")
    ap.add_argument("--extensions", nargs="+", default=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "heic"],
                    help="Image extensions to include (default includes jpg/jpeg/png/webp/bmp/tif/tiff/heic)")
    ap.add_argument("--hash-size", type=int, default=16, help="pHash size (default 16 -> 256-bit). Smaller is faster, less accurate.")
    ap.add_argument("--json", type=str, default="", help="Write groups to a JSON file")
    ap.add_argument("--min-group", type=int, default=2, help="Only output groups with at least this many images (default 2)")
    args = ap.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")

    paths = iter_images(root, args.extensions, args.recursive)
    if not paths:
        raise SystemExit("No images found with given extensions.")

    print(f"Found {len(paths)} images. Computing perceptual hashes...")
    hashes: List[ImgHash] = []
    failures: List[str] = []

    for p in tqdm(paths, unit="img"):
        try:
            meta = compute_phash(p, hash_size=args.hash_size)
            hashes.append(
                ImgHash(
                    path=str(p),
                    phash=meta["phash"],
                    width=meta["width"],
                    height=meta["height"],
                    size_bytes=meta["size_bytes"],
                    mtime=meta["mtime"],
                )
            )

        except Exception as e:
            failures.append(f"{p} :: {e}")

    if failures:
        print(f"\nWarning: {len(failures)} images failed to process (showing up to 10):")
        for line in failures[:10]:
            print("  -", line)

    n = len(hashes)
    if n < 2:
        raise SystemExit("Need at least two readable images to compare.")

    print(f"\nComparing hashes (O(n^2) = {n*(n-1)//2:,} comparisons)...")
    find, union = union_find(n)
    similar_pairs: List[Tuple[int, int, int]] = []

    # Brute-force comparisons; good up to a few thousand images depending on machine.
    for i in tqdm(range(n), unit="img"):
        hi = hashes[i].phash
        for j in range(i + 1, n):
            d = hamming_distance(hi, hashes[j].phash)
            if d <= args.threshold:
                union(i, j)
                similar_pairs.append((i, j, d))

    # Build groups
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    # Filter + sort groups by size desc
    grouped = [idxs for idxs in groups.values() if len(idxs) >= args.min_group]
    grouped.sort(key=len, reverse=True)

    if not grouped:
        print("\nNo similar groups found at this threshold.")
        return

    print(f"\nFound {len(grouped)} group(s) with >= {args.min_group} images (threshold={args.threshold}).\n")

    # Print groups with distances (optional: show closest pair per group)
    for gi, idxs in enumerate(grouped, start=1):
        # sort indexes by file size (descending)
        sorted_idxs = sorted(
            idxs,
            key=lambda i: (hashes[i].size_bytes, -hashes[i].mtime, hashes[i].path),
            reverse=True
        )

        print(f"Group {gi} ({len(sorted_idxs)} images):")
        rm_command = "rm \\\n"
        first = True
        for k in sorted_idxs:
            img = hashes[k]
            print(
                f"  - {img.path}\n"
                f"      {img.width}x{img.height} | "
                f"{human_size(img.size_bytes)} | "
                f"modified {human_time(img.mtime)}"
            )
            if not first:
                rm_command += f'''"{img.path}" \\\n'''
            else:
                first = False
        print(rm_command)
        print()

    if args.json:
        out = []
        for idxs in grouped:
            out.append({
                "count": len(idxs),
                "images": [{"path": hashes[k].path, "phash": hashes[k].phash} for k in idxs],
            })
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Wrote JSON: {args.json}")


if __name__ == "__main__":
    main()

