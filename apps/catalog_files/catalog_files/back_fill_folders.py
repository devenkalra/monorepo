import os
import re
from collections import defaultdict
from typing import Dict, Any, Iterable, Tuple, Optional

import meilisearch
MEILI_URL = "https://meili.bldrdojo.com"
MEILI_API_KEY = "DKKeyDKKeyDkKeyDKKey"  # The master key you set when creating the container
INDEX_NAME = "files_catalog"

FILES_INDEX = INDEX_NAME
FOLDERS_INDEX = "catalog_folders"

READ_LIMIT = int(os.environ.get("READ_LIMIT", "5000"))
WRITE_BATCH = int(os.environ.get("WRITE_BATCH", "2000"))

# If your file docs have 'volume', set this true to track per-volume counts
TRACK_VOLUME_COUNTS = os.environ.get("TRACK_VOLUME_COUNTS", "1") == "1"


def normalize_dir(p: str) -> str:
    if not p:
        return "/"
    s = str(p).replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s)
    if not s.startswith("/"):
        s = "/" + s
    if len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s or "/"


def parent_dir(dir_path: str) -> Optional[str]:
    if dir_path == "/":
        return None
    i = dir_path.rfind("/")
    if i <= 0:
        return "/"
    return dir_path[:i] or "/"


def leaf_name(dir_path: str) -> str:
    if dir_path == "/":
        return "/"
    return dir_path.split("/")[-1]


def depth(dir_path: str) -> int:
    if dir_path == "/":
        return 0
    return len([p for p in dir_path.split("/") if p])


def iter_ancestors(dir_path: str) -> Iterable[str]:
    """Yield dir and its parents up to '/'."""
    d = dir_path
    while True:
        yield d
        pd = parent_dir(d)
        if pd is None:
            break
        d = pd


def main():
    client = meilisearch.Client(MEILI_URL, MEILI_API_KEY)
    files = client.index(FILES_INDEX)
    folders = client.index(FOLDERS_INDEX)

    # One-time index settings (run once; safe if repeated)
    # folders.update_filterable_attributes(["parent_dir", "depth"])
    # folders.update_sortable_attributes(["name", "file_count", "child_count"])

    # Accumulators
    # direct file counts by folder
    direct_counts: Dict[str, int] = defaultdict(int)

    # volume counts by folder (optional)
    vol_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Ensure every ancestor folder exists even if direct_counts is 0
    seen_folders = set(["/"])

    offset = 0
    processed = 0

    while True:
        resp = files.get_documents({"limit": READ_LIMIT, "offset": offset})
        docs = resp.get("results") if isinstance(resp, dict) else resp.results
        if not docs:
            break

        for doc in docs:
            processed += 1
            d = normalize_dir(doc.path)
            seen_folders.update(iter_ancestors(d))

            direct_counts[d] += 1

            if TRACK_VOLUME_COUNTS:
                v = doc.volume
                if v:
                    vol_counts[d][str(v)] += 1

        offset += len(docs)
        print(f"Scanned files: {offset}")

    # Build initial folder docs (child_count computed in second pass)
    folder_docs: Dict[str, Dict[str, Any]] = {}

    for d in seen_folders:
        pd = parent_dir(d)
        folder_docs[d] = {
            "id": d,
            "dir": d,
            "parent_dir": pd if pd is not None else "/",  # convenient: root children query uses parent_dir="/"
            "name": leaf_name(d),
            "depth": depth(d),
            "file_count": direct_counts.get(d, 0),
            "child_count": 0,
        }
        if TRACK_VOLUME_COUNTS:
            # store as array of [volume, count] to keep JSON small and deterministic
            vc = vol_counts.get(d)
            if vc:
                folder_docs[d]["volume_counts"] = sorted([[k, v] for k, v in vc.items()])

    # Compute child_count (immediate subfolders)
    for d in seen_folders:
        if d == "/":
            continue
        pd = parent_dir(d) or "/"
        if pd in folder_docs:
            folder_docs[pd]["child_count"] = int(folder_docs[pd].get("child_count", 0)) + 1

    # Write to Meili in batches
    all_docs = list(folder_docs.values())
    print(f"Writing {len(all_docs)} folder docs to index '{FOLDERS_INDEX}'")

    for i in range(0, len(all_docs), WRITE_BATCH):
        batch = all_docs[i : i + WRITE_BATCH]
        folders.add_documents(batch)  # add_documents upserts
        print(f"Wrote {i + len(batch)} / {len(all_docs)}")

    print("Done.")


if __name__ == "__main__":
    main()
