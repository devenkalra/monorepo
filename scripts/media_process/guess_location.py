#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dateutil import parser as dateparser
from PIL import Image, ExifTags, ImageFile
from tqdm import tqdm
import imagehash

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Optional HEIC support
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass

TAGS = ExifTags.TAGS
GPSTAGS = ExifTags.GPSTAGS


@dataclass
class PhotoRow:
    path: str
    datetime: Optional[dt.datetime]
    lat: Optional[float]
    lon: Optional[float]
    place: Optional[str]
    source: str
    confidence: float
    evidence: str


def human_dt(x: Optional[dt.datetime]) -> str:
    return x.isoformat() if x else ""


def _ratio_to_float(x: Any) -> float:
    if isinstance(x, tuple) and len(x) == 2:
        num, den = x
        return float(num) / float(den) if den else 0.0
    if hasattr(x, "numerator") and hasattr(x, "denominator"):
        den = float(x.denominator)
        return float(x.numerator) / den if den else 0.0
    return float(x)


def _dms_to_deg(dms: Any, ref: str) -> Optional[float]:
    try:
        d = _ratio_to_float(dms[0])
        m = _ratio_to_float(dms[1])
        s = _ratio_to_float(dms[2])
        deg = d + (m / 60.0) + (s / 3600.0)
        if ref in ("S", "W"):
            deg = -deg
        return deg
    except Exception:
        return None


def parse_exif_datetime(exif: Dict[str, Any]) -> Optional[dt.datetime]:
    # Typical EXIF string: "2024:11:02 14:31:09"
    for k in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        v = exif.get(k)
        if not v:
            continue
        try:
            if isinstance(v, bytes):
                v = v.decode(errors="ignore")
            v = str(v).strip()
            # Try EXIF format first
            try:
                return dt.datetime.strptime(v, "%Y:%m:%d %H:%M:%S")
            except Exception:
                return dateparser.parse(v)
        except Exception:
            pass
    return None


def extract_exif(path: Path) -> Dict[str, Any]:
    try:
        with Image.open(path) as im:
            exif_raw = im._getexif() or {}
    except Exception:
        return {}

    out: Dict[str, Any] = {}
    for k, v in exif_raw.items():
        out[TAGS.get(k, k)] = v
    return out


def extract_gps_from_exif(exif: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    gps_info = exif.get("GPSInfo")
    if not gps_info:
        return None, None

    gps: Dict[str, Any] = {}
    try:
        for k, v in gps_info.items():
            gps[GPSTAGS.get(k, k)] = v
    except Exception:
        return None, None

    lat = lon = None
    if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
        lat = _dms_to_deg(gps["GPSLatitude"], gps["GPSLatitudeRef"])
    if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
        lon = _dms_to_deg(gps["GPSLongitude"], gps["GPSLongitudeRef"])
    return lat, lon


# ---------- Sidecars ----------

def find_sidecars(img: Path) -> List[Path]:
    """Common sidecars: Google Takeout .json, XMP sidecar."""
    out = []
    # Google Takeout often uses "IMG_1234.jpg.json" (same full filename + .json)
    gjson = Path(str(img) + ".json")
    if gjson.exists():
        out.append(gjson)

    # Sometimes sidecar is same stem: "IMG_1234.json"
    stem_json = img.with_suffix(".json")
    if stem_json.exists() and stem_json not in out:
        out.append(stem_json)

    # XMP: "IMG_1234.xmp"
    xmp = img.with_suffix(".xmp")
    if xmp.exists():
        out.append(xmp)

    return out


def parse_google_takeout_json(p: Path) -> Tuple[Optional[float], Optional[float], Optional[dt.datetime], str]:
    """
    Google Photos Takeout JSON commonly contains:
      - geoDataExif: { latitude, longitude, ... } OR geoData: { ... }
      - photoTakenTime: { timestamp: "..." }
    """
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None, None, None, ""

    lat = lon = None
    evidence = []

    for key in ("geoDataExif", "geoData"):
        geo = data.get(key) or {}
        if isinstance(geo, dict):
            la = geo.get("latitude")
            lo = geo.get("longitude")
            if isinstance(la, (int, float)) and isinstance(lo, (int, float)):
                lat, lon = float(la), float(lo)
                evidence.append(key)

    taken_dt = None
    ptt = data.get("photoTakenTime") or {}
    ts = ptt.get("timestamp")
    if ts:
        try:
            taken_dt = dt.datetime.fromtimestamp(int(ts))
            evidence.append("photoTakenTime")
        except Exception:
            pass

    return lat, lon, taken_dt, ",".join(evidence)


_DMS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)\s*([NSEW])\s*$", re.I)


def parse_dms_text(s: str) -> Optional[float]:
    """
    Accepts strings like: '37, 46, 30.12 N' or '37 46 30.12 N'
    """
    m = _DMS_RE.match(s.strip())
    if not m:
        return None
    d, mm, ss, ref = m.groups()
    deg = float(d) + float(mm) / 60.0 + float(ss) / 3600.0
    if ref.upper() in ("S", "W"):
        deg = -deg
    return deg


def parse_xmp(p: Path) -> Tuple[Optional[float], Optional[float], Optional[dt.datetime], str]:
    """
    Best-effort XMP parsing. XMP may store GPS in various namespaces/keys.
    We'll look for common patterns:
      exif:GPSLatitude / exif:GPSLongitude
      tiff:DateTime or exif:DateTimeOriginal
    """
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        root = ET.fromstring(txt)
    except Exception:
        return None, None, None, ""

    lat = lon = None
    taken = None
    found = []

    # Search all attributes in the tree for GPS-ish fields.
    for elem in root.iter():
        for k, v in (elem.attrib or {}).items():
            key = k.lower()
            if "gpslatitude" in key and isinstance(v, str):
                val = parse_dms_text(v) or (float(v) if v.strip().replace(".", "", 1).replace("-", "", 1).isdigit() else None)
                if val is not None:
                    lat = val
                    found.append("xmp:gpslat")
            if "gpslongitude" in key and isinstance(v, str):
                val = parse_dms_text(v) or (float(v) if v.strip().replace(".", "", 1).replace("-", "", 1).isdigit() else None)
                if val is not None:
                    lon = val
                    found.append("xmp:gpslon")
            if ("datetimeoriginal" in key or key.endswith("datetime")) and isinstance(v, str) and not taken:
                try:
                    taken = dateparser.parse(v)
                    found.append("xmp:datetime")
                except Exception:
                    pass

    return lat, lon, taken, ",".join(found)


# ---------- Name / folder hints ----------

PLACE_SPLIT_RE = re.compile(r"[/\\]+")

def extract_place_hint_from_path(path: Path) -> Optional[str]:
    """
    Very simple heuristic: look at folder names and file name tokens,
    ignore obviously-date-like segments and numeric-only segments.
    Example: Trips/2024/11/08 New Zealand/IMG_1234.jpg -> "New Zealand"
    """
    parts = PLACE_SPLIT_RE.split(str(path.parent))
    candidates = []
    for part in reversed(parts[-6:]):  # last few folders usually most informative
        p = part.strip()
        if not p:
            continue
        # skip year/month/day-like folders
        if re.fullmatch(r"\d{4}", p) or re.fullmatch(r"\d{1,2}", p) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
            continue
        if re.search(r"\d{4}[:\-]\d{2}[:\-]\d{2}", p):
            continue
        # allow multi-word place-ish segments
        if any(c.isalpha() for c in p) and len(p) >= 3:
            candidates.append(p)

    # Return the best guess (nearest folder that looks place-like)
    return candidates[0] if candidates else None


# ---------- Reverse geocoding (optional) ----------

class Nominatim:
    def __init__(self, user_agent: str, cache_path: Path, min_delay: float = 1.1):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent})
        self.cache_path = cache_path
        self.min_delay = min_delay
        self.last = 0.0
        self.cache: Dict[str, Any] = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}

    def _k(self, lat: float, lon: float) -> str:
        return f"{lat:.6f},{lon:.6f}"

    def reverse(self, lat: float, lon: float) -> Optional[str]:
        k = self._k(lat, lon)
        if k in self.cache:
            return self.cache[k].get("display_name")

        wait = self.min_delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)

        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"format": "jsonv2", "lat": str(lat), "lon": str(lon), "zoom": "14", "addressdetails": "1"}
        r = self.s.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        self.last = time.time()
        self.cache[k] = data
        try:
            self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
        except Exception:
            pass
        return data.get("display_name")

    def search_place(self, q: str) -> Optional[Tuple[float, float, str]]:
        """Geocode a place string to lat/lon (best effort)."""
        key = f"q:{q.strip().lower()}"
        if key in self.cache:
            cached = self.cache[key]
            if cached:
                return float(cached["lat"]), float(cached["lon"]), cached.get("display_name", q)
            return None

        wait = self.min_delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)

        url = "https://nominatim.openstreetmap.org/search"
        params = {"format": "jsonv2", "q": q, "limit": "1"}
        r = self.s.get(url, params=params, timeout=20)
        r.raise_for_status()
        arr = r.json()
        self.last = time.time()

        if arr:
            hit = arr[0]
            self.cache[key] = hit
            try:
                self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
            except Exception:
                pass
            return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", q)

        self.cache[key] = None
        try:
            self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
        except Exception:
            pass
        return None


# ---------- Content + time inference helpers ----------

def compute_phash(path: Path, hash_size: int = 16) -> Optional[str]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            return str(imagehash.phash(im, hash_size=hash_size))
    except Exception:
        return None


def hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------- Main ----------

def iter_images(root: Path, recursive: bool, exts: List[str]) -> List[Path]:
    exts = {("." + e.lower().lstrip(".")) for e in exts}
    if recursive:
        paths = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    else:
        paths = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return sorted(paths)


def main():
    ap = argparse.ArgumentParser(description="Infer photo locations using EXIF, sidecars, names, time, and content.")
    ap.add_argument("folder")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--extensions", nargs="+", default=["jpg", "jpeg", "png", "tif", "tiff", "webp", "heic"])
    ap.add_argument("--out", default="inferred_locations.csv")

    # Sidecars / names
    ap.add_argument("--use-sidecars", action="store_true", default=True)
    ap.add_argument("--use-names", action="store_true", default=True)

    # Geocoding (optional web calls)
    ap.add_argument("--geocode", action="store_true", help="Reverse geocode lat/lon and optionally geocode name hints (uses Nominatim).")
    ap.add_argument("--user-agent", default="infer-photo-locations/1.0 (set a real contact)")
    ap.add_argument("--cache", default=".nominatim_cache.json")

    # Time inference
    ap.add_argument("--infer-time", action="store_true", default=True)
    ap.add_argument("--max-time-mins", type=int, default=120, help="Max minutes difference for time-based location copy (default 120).")

    # Content inference (pHash)
    ap.add_argument("--infer-content-phash", action="store_true", default=True)
    ap.add_argument("--phash-size", type=int, default=16)
    ap.add_argument("--phash-threshold", type=int, default=6, help="Hamming distance threshold for pHash match (default 6 for hash_size=16).")

    # Content inference (CLIP) optional
    ap.add_argument("--infer-content-clip", action="store_true", help="Use CLIP embeddings nearest neighbor (requires sentence-transformers/torch).")

    args = ap.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")

    imgs = iter_images(root, args.recursive, args.extensions)
    if not imgs:
        raise SystemExit("No images found.")

    nomi = None
    if args.geocode:
        nomi = Nominatim(args.user_agent, Path(args.cache).expanduser().resolve(), min_delay=1.1)

    # First pass: extract best-known location (EXIF -> sidecar -> name geocode)
    rows: List[PhotoRow] = []
    phashes: Dict[str, str] = {}  # path -> phash
    located_idx: List[int] = []   # indexes into rows with lat/lon
    time_index: List[Tuple[dt.datetime, int]] = []  # (datetime, row_index)

    # Optional CLIP
    clip_model = None
    clip_paths: List[str] = []
    clip_vecs = None

    if args.infer_content_clip:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            clip_model = SentenceTransformer("clip-ViT-B-32")
        except Exception:
            print("CLIP requested but sentence-transformers/torch not available. Skipping CLIP.")
            clip_model = None

    for p in tqdm(imgs, unit="img", desc="Reading EXIF/sidecars"):
        exif = extract_exif(p)
        dt0 = parse_exif_datetime(exif)

        lat, lon = extract_gps_from_exif(exif)
        source = "unknown"
        conf = 0.0
        evidence = ""

        if lat is not None and lon is not None:
            source = "exif_gps"
            conf = 1.0
            evidence = "EXIF GPSInfo"
        else:
            # Sidecars
            if args.use_sidecars:
                for sc in find_sidecars(p):
                    if sc.suffix.lower() == ".json":
                        la, lo, taken, ev = parse_google_takeout_json(sc)
                        if dt0 is None and taken is not None:
                            dt0 = taken
                        if la is not None and lo is not None:
                            lat, lon = la, lo
                            source = "sidecar_json"
                            conf = 0.95
                            evidence = f"{sc.name}:{ev}"
                            break
                    if sc.suffix.lower() == ".xmp":
                        la, lo, taken, ev = parse_xmp(sc)
                        if dt0 is None and taken is not None:
                            dt0 = taken
                        if la is not None and lo is not None:
                            lat, lon = la, lo
                            source = "sidecar_xmp"
                            conf = 0.9
                            evidence = f"{sc.name}:{ev}"
                            break

            # Name hints -> optional geocode
            if (lat is None or lon is None) and args.use_names and nomi is not None:
                hint = extract_place_hint_from_path(p)
                if hint:
                    hit = nomi.search_place(hint)
                    if hit:
                        la, lo, disp = hit
                        lat, lon = la, lo
                        source = "name_geocode"
                        conf = 0.6
                        evidence = f'path_hint="{hint}"'

        place = None
        if lat is not None and lon is not None and nomi is not None:
            try:
                place = nomi.reverse(lat, lon)
            except Exception:
                place = None

        r = PhotoRow(
            path=str(p),
            datetime=dt0,
            lat=lat,
            lon=lon,
            place=place,
            source=source,
            confidence=conf,
            evidence=evidence,
        )
        rows.append(r)

    # Build indexes of located photos
    for i, r in enumerate(rows):
        if r.lat is not None and r.lon is not None:
            located_idx.append(i)
        if r.datetime is not None:
            time_index.append((r.datetime, i))
    time_index.sort(key=lambda x: x[0])

    # Precompute pHash for content inference if needed
    if args.infer_content_phash:
        for r in tqdm(rows, unit="img", desc="Computing pHash"):
            h = compute_phash(Path(r.path), hash_size=args.phash_size)
            if h:
                phashes[r.path] = h

    # CLIP vectors for located images (optional)
    if clip_model is not None and located_idx:
        # Keep it simple: embed only the located images; then query for unknowns.
        # NOTE: SentenceTransformer CLIP accepts images via PIL list.
        located_paths = [rows[i].path for i in located_idx]
        try:
            loc_imgs = []
            for p in tqdm(located_paths, desc="Loading images for CLIP"):
                with Image.open(p) as im:
                    loc_imgs.append(im.convert("RGB"))
            clip_vecs = clip_model.encode(loc_imgs, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=True)
            clip_paths = located_paths
        except Exception:
            clip_model = None
            clip_vecs = None
            clip_paths = []

    # Second pass: infer for unknowns using time, then content
    max_dt = dt.timedelta(minutes=args.max_time_mins)

    def nearest_in_time(t: dt.datetime) -> Optional[int]:
        # binary search in time_index
        import bisect
        times = [x[0] for x in time_index]
        pos = bisect.bisect_left(times, t)
        candidates = []
        for j in (pos - 1, pos, pos + 1):
            if 0 <= j < len(time_index):
                candidates.append(time_index[j])
        best = None
        best_delta = None
        for tt, idx in candidates:
            rr = rows[idx]
            if rr.lat is None or rr.lon is None:
                continue
            d = abs(tt - t)
            if d <= max_dt and (best_delta is None or d < best_delta):
                best = idx
                best_delta = d
        return best

    # Content: best pHash match among located images
    located_phash = [(i, phashes.get(rows[i].path)) for i in located_idx if phashes.get(rows[i].path)]
    def best_phash_match(path: str) -> Optional[Tuple[int, int]]:
        h0 = phashes.get(path)
        if not h0:
            return None
        best = None
        best_d = None
        for i, hi in located_phash:
            if not hi:
                continue
            d = hamming(h0, hi)
            if best_d is None or d < best_d:
                best_d = d
                best = i
        if best is not None and best_d is not None and best_d <= args.phash_threshold:
            return best, best_d
        return None

    # Content: CLIP nearest neighbor
    def best_clip_match(path: str) -> Optional[Tuple[int, float]]:
        if clip_model is None or clip_vecs is None or not clip_paths:
            return None
        try:
            with Image.open(path) as im:
                qv = clip_model.encode([im.convert("RGB")], convert_to_numpy=True, normalize_embeddings=True)[0]
            # cosine similarity since normalized
            sims = clip_vecs @ qv
            best_i = int(sims.argmax())
            sim = float(sims[best_i])
            # heuristic cutoff; tune as needed
            if sim >= 0.28:
                matched_path = clip_paths[best_i]
                # map back to rows index
                matched_idx = next((i for i in located_idx if rows[i].path == matched_path), None)
                if matched_idx is not None:
                    return matched_idx, sim
        except Exception:
            return None
        return None

    for i, r in tqdm(list(enumerate(rows)), unit="img", desc="Inferring missing locations"):
        if r.lat is not None and r.lon is not None:
            continue

        # 1) time-based inference
        if args.infer_time and r.datetime is not None:
            j = nearest_in_time(r.datetime)
            if j is not None:
                src = rows[j]
                r.lat, r.lon = src.lat, src.lon
                r.source = "inferred_time"
                # confidence decays with time delta
                delta = abs(src.datetime - r.datetime) if src.datetime and r.datetime else max_dt
                frac = min(1.0, delta.total_seconds() / max_dt.total_seconds())
                r.confidence = 0.75 * (1.0 - 0.7 * frac)
                r.evidence = f"nearest_time={human_dt(src.datetime)} src={src.path}"
                if nomi is not None and r.lat is not None and r.lon is not None:
                    try:
                        r.place = nomi.reverse(r.lat, r.lon)
                    except Exception:
                        pass
                continue

        # 2) content-based pHash inference
        if args.infer_content_phash:
            m = best_phash_match(r.path)
            if m is not None:
                j, d = m
                src = rows[j]
                r.lat, r.lon = src.lat, src.lon
                r.source = "inferred_content_phash"
                # map distance -> confidence (heuristic)
                r.confidence = max(0.35, 0.85 - (d / max(1, args.phash_threshold)) * 0.5)
                r.evidence = f"phash_d={d} src={src.path}"
                if nomi is not None and r.lat is not None and r.lon is not None:
                    try:
                        r.place = nomi.reverse(r.lat, r.lon)
                    except Exception:
                        pass
                continue

        # 3) content-based CLIP inference (optional)
        if args.infer_content_clip:
            m2 = best_clip_match(r.path)
            if m2 is not None:
                j, sim = m2
                src = rows[j]
                r.lat, r.lon = src.lat, src.lon
                r.source = "inferred_content_clip"
                r.confidence = min(0.8, max(0.4, (sim - 0.25) * 2.0))
                r.evidence = f"clip_sim={sim:.3f} src={src.path}"
                if nomi is not None and r.lat is not None and r.lon is not None:
                    try:
                        r.place = nomi.reverse(r.lat, r.lon)
                    except Exception:
                        pass
                continue

    # Write CSV
    out = Path(args.out).expanduser().resolve()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "datetime", "lat", "lon", "place", "location_source", "confidence", "evidence"])
        for r in rows:
            w.writerow([r.path, human_dt(r.datetime), r.lat, r.lon, r.place, r.source, f"{r.confidence:.2f}", r.evidence])

    known = sum(1 for r in rows if r.lat is not None and r.lon is not None)
    inferred = sum(1 for r in rows if r.source.startswith("inferred_"))
    print(f"Wrote: {out}")
    print(f"Located: {known}/{len(rows)} (inferred: {inferred})")


if __name__ == "__main__":
    main()
