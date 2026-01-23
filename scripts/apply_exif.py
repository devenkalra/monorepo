#!/usr/bin/env python3
"""apply_exif.py – Enhanced script to apply EXIF/XMP tags to images.

Features:
- Load tags from a YAML file (`--tags-yaml`).
- Specify additional tags via the command line (`--set TAG=VALUE`).
- Dry‑run mode (`--dry-run`).
- Select files with a glob pattern (`--pattern`).
- Provide an explicit list of image files (`--files`).
- Backward‑compatible behavior using the original `PATTERN_TAG_MAP` when no new arguments are supplied.
"""

import argparse
import glob
import shlex
import subprocess
from pathlib import Path

import yaml
import json
import datetime
import sys
import requests
from geopy.geocoders import Nominatim

# ---------------- CONFIG ----------------
# Existing pattern‑to‑tag mapping retained for backward compatibility.
PATTERN_TAG_MAP = {
}

# Default tag name used by the original script.
DEFAULT_TAG_NAME = "XMP-dc:Subject"
# ----------------------------------------


def load_yaml_tags(path: str) -> dict:
    """Load a YAML file containing a mapping of tag names to values.

    The file should contain a simple mapping, e.g.:
        XMP-dc:Subject: "vacation"
        XMP-iptc:Keywords: "beach, sunset"
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError("YAML file must contain a mapping of tag names to values.")
            return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        raise FileNotFoundError(f"YAML tags file not found: {path}")


def parse_cli_tags(tag_list: list) -> dict:
    """Parse ``--set TAG=VALUE`` arguments into a dictionary.

    ``tag_list`` is a list of strings supplied by ``argparse``.
    """
    tags = {}
    for item in tag_list:
        if "=" not in item:
            raise ValueError(f"Invalid tag specification '{item}'. Expected format TAG=VALUE.")
        key, value = item.split("=", 1)
        tags[key] = value
    return tags


def build_exiftool_cmd(files: list, tags: dict, dry_run: bool) -> list:
    """Construct the ``exiftool`` command.

    ``tags`` is a mapping of tag names to values. Each entry becomes ``-TAG=VALUE``.
    For list values (e.g., keywords), we clear the tag first, then use -= to delete 
    the empty value, then use += to add each value individually.
    """
    cmd = ["exiftool"]
    
    # Separate list-type tags from regular tags
    list_tags = {}
    regular_tags = {}
    
    for tag_name, tag_value in tags.items():
        if isinstance(tag_value, list):
            list_tags[tag_name] = tag_value
        else:
            regular_tags[tag_name] = tag_value
    
    # Process list-type tags (keywords, subjects, etc.)
    # Strategy: Use -sep to specify separator, then pass all values as one string
    for tag_name, tag_values in list_tags.items():
        if tag_values:
            # Use newline as separator (exiftool's default for lists)
            cmd.append("-sep")
            cmd.append("\n")
            # Join all values with newline and set in one go
            joined_values = "\n".join(tag_values)
            cmd.append(f"-{tag_name}={joined_values}")
        else:
            # Empty list - clear the tag
            cmd.append(f"-{tag_name}=")
    
    # Process regular tags
    for tag_name, tag_value in regular_tags.items():
        cmd.append(f"-{tag_name}={tag_value}")
    
    if not dry_run:
        cmd.append("-overwrite_original")
    cmd.extend(files)
    return cmd


def run_exiftool(files: list, tags: dict, dry_run: bool):
    """Execute the exiftool command with the given files and tags."""
    cmd = build_exiftool_cmd(files, tags, dry_run)
    cmd_str = shlex.join(cmd)
    print(f"Exiftool command: {cmd_str}")

    if dry_run:
        print("Dry run: Command not executed.")
        return

    try:
        # Use subprocess.run for better error handling and capturing output.
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            print("Exiftool output:\n", result.stdout)
        if result.stderr:
            print("Exiftool errors (if any):\n", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error executing exiftool: {e}", file=sys.stderr)
        print(f"Stdout: {e.stdout}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        raise RuntimeError(f"exiftool failed: {e.stderr}") from e
    except FileNotFoundError as e:
        print("Error: exiftool not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        raise RuntimeError("exiftool not found") from e


def get_existing_keywords(file_path: str) -> dict:
    """Read existing XMP-dc:Subject and IPTC:Keywords from a file using exiftool.

    Returns a dictionary like {"XMP-dc:Subject": ["kw1", "kw2"], "IPTC:Keywords": ["kw1", "kw2"]}.
    """
    # Use -G flag to get group names in JSON output (e.g., "XMP:Subject" instead of just "Subject")
    cmd = ["exiftool", "-G", "-json", "-XMP-dc:Subject", "-IPTC:Keywords", file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            data = json.loads(result.stdout)
            if data and isinstance(data, list) and data[0]:
                file_tags = data[0]
                # Try multiple possible key names for compatibility
                # exiftool with -G returns "XMP:Subject" not "XMP-dc:Subject"
                subjects = (file_tags.get("XMP-dc:Subject") or 
                           file_tags.get("XMP:Subject") or 
                           file_tags.get("Subject", []))
                iptc_keywords = (file_tags.get("IPTC:Keywords") or 
                                file_tags.get("Keywords", []))
                normalized = {
                    "XMP-dc:Subject": _normalize_keywords(subjects),
                    "IPTC:Keywords": _normalize_keywords(iptc_keywords),
                }
                return normalized
        return {"XMP-dc:Subject": [], "IPTC:Keywords": []}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Warning: Could not read existing keywords from {file_path}: {e}", file=sys.stderr)
        return {"XMP-dc:Subject": [], "IPTC:Keywords": []}
    except FileNotFoundError:
        print("Error: exiftool not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)


def resolve_files(args) -> list:
    """Determine the list of image files to process based on arguments.

    Priority:
    1. Explicit ``--files`` list.
    2. ``--pattern`` glob.
    3. Fallback to legacy ``PATTERN_TAG_MAP`` handling.
    """
    if args.files:
        # Ensure paths are absolute for consistency.
        return [str(Path(p).resolve()) for p in args.files]
    if args.pattern:
        return sorted(glob.glob(args.pattern, recursive=True))
    # Legacy mode – return an empty list; the caller will handle PATTERN_TAG_MAP.
    return []


def create_exif_metadata(place_name: str, date_str: str = "", offset_str: str = "") -> dict:
    """Generate EXIF/XMP metadata for a location and optional timestamp.

    Parameters:
    - ``place_name``: Human‑readable location (required for location tags).
    - ``date_str``:   Date/time in ``YYYY:MM:DD HH:MM:SS`` format (optional).
    - ``offset_str``: UTC offset string like ``+05:30`` (optional).
    """
    # Geocode location if a place is provided.
    import requests
    geolocator = Nominatim(user_agent="exif_metadata_generator")
    # Request English names and extra tags (including elevation).
    location = geolocator.geocode(place_name, addressdetails=True, language='en', extratags=True)
    if not location:
        raise ValueError(f"Could not geocode place: {place_name}")

    # Extract address components (prefer English names).
    # Nominatim may return localized names; use 'namedetails' which respects the language parameter.
    address = location.raw.get('address', {}) if isinstance(location.raw, dict) else {}
    namedetails = location.raw.get('namedetails', {}) if isinstance(location.raw, dict) else {}
    city = address.get('city') or address.get('town') or namedetails.get('city') or ""
    state = address.get('state') or namedetails.get('state') or ""
    country = address.get('country') or namedetails.get('country') or ""
    country_code = address.get('country_code', "").upper()


    # Extract altitude if available (elevation in meters).
    altitude = None
    extratags = location.raw.get('extratags', {}) if isinstance(location.raw, dict) else {}
    # Nominatim may provide 'ele' or 'elevation' in extratags.
    if extratags is not None:
        if 'ele' in extratags:
            altitude = extratags['ele']
        elif 'elevation' in extratags:
            altitude = extratags['elevation']
    # Ensure altitude is a number; default to 0 if not provided.
    try:
        altitude = float(altitude)
    except (TypeError, ValueError):
        altitude = 0
    # If altitude is still 0, fallback to open-elevation.com API.
    if altitude == 0:
        try:
            resp = requests.get(
                "https://api.open-elevation.com/api/v1/lookup",
                params={"locations": f"{location.latitude},{location.longitude}"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results')
                if results and isinstance(results, list):
                    elevation = results[0].get('elevation')
                    if elevation is not None:
                        altitude = float(elevation)
        except Exception:
            # Silently ignore failures; keep altitude as 0.
            pass
    
    metadata = {}
    # Add optional date/time tags if supplied.
    if date_str:
        metadata["DateTimeOriginal"] = date_str
        metadata["CreateDate"] = date_str
    if offset_str:
        metadata["OffsetTimeOriginal"] = offset_str
        metadata["OffsetTimeDigitized"] = offset_str
    # Add GPS and all required location tags.
    metadata.update({
        "GPSLatitude": abs(location.latitude),
        "GPSLatitudeRef": "N" if location.latitude >= 0 else "S",
        "GPSLongitude": abs(location.longitude),
        "GPSLongitudeRef": "E" if location.longitude >= 0 else "W",
        "GPSAltitude": altitude,
        # Photoshop XMP tags
        "XMP-photoshop:City": city,
        "XMP-photoshop:State": state,
        "XMP-photoshop:Country": country,
        # IPTC Extension tags
        "XMP-iptcExt:LocationShownCity": city,
        "XMP-iptcExt:LocationShownProvinceState": state,
        "XMP-iptcExt:LocationShownCountryName": country,
        "XMP-iptcExt:LocationShownCountryCode": country_code,
        # Coverage tag
        "XMP-dc:Coverage": place_name,
    })
    return metadata


def _normalize_keywords(keywords) -> list:
    """Ensure keywords are a list of unique strings, handling various input types."""
    if isinstance(keywords, str):
        # Split by comma, strip whitespace, filter empty strings
        return sorted(list(set([k.strip() for k in keywords.split(',') if k.strip()])))
    elif isinstance(keywords, (list, tuple, set)):
        return sorted(list(set([str(k).strip() for k in keywords if str(k).strip()])))
    return []


def main():
    parser = argparse.ArgumentParser(description="Apply EXIF/XMP tags to images.")
    parser.add_argument("--dry-run", action="store_true", help="Print exiftool commands without writing.")
    parser.add_argument("--tags-yaml", type=str, help="Path to a YAML file containing tag name/value pairs.")
    parser.add_argument("--set", action="append", default=[], metavar="TAG=VALUE", help="Tag to set (can be repeated).")
    parser.add_argument("--pattern", type=str, help="Glob pattern to select image files.")
    parser.add_argument("--files", nargs="+", help="Explicit list of image files to process.")
    # New arguments for location metadata
    parser.add_argument("--place", type=str, help="Place name for location metadata (e.g., 'Fort Worth, Texas, USA').")
    parser.add_argument("--date", type=str, help="Date/time string in 'YYYY:MM:DD HH:MM:SS' format.")
    parser.add_argument("--offset", type=str, help="UTC offset string like '+05:30' or '-06:00'.")
    # Ensure sys is available for error handling
    import sys
    # New arguments for keywords and caption
    parser.add_argument("--add-keyword", action="append", default=[], help="Keyword to add (can be repeated).")
    parser.add_argument("--remove-keyword", action="append", default=[], help="Keyword to remove if present.")
    parser.add_argument("--caption", type=str, help="Caption text to set as Caption-Abstract.")
    args = parser.parse_args()

    # Load tags from YAML if provided.
    yaml_tags = {}
    if args.tags_yaml:
        yaml_tags = load_yaml_tags(args.tags_yaml)

    # Parse command‑line tags.
    cli_tags = parse_cli_tags(args.set)

    # Initialize a dictionary for all tags to be applied.
    # These are base tags that will be applied to all files,
    # potentially modified by per-file keyword logic.
    base_tags = {}

    # 1. Start with tags from YAML and CLI (CLI overrides YAML).
    base_tags.update({**yaml_tags, **cli_tags})

    # 2. Add location metadata if --place is provided.
    if args.place:
        try:
            location_metadata = create_exif_metadata(args.place, args.date, args.offset)
            base_tags.update(location_metadata)
        except (ValueError, requests.exceptions.RequestException) as e:
            print(f"Error generating location metadata: {e}", file=sys.stderr)
            sys.exit(1)
    
    # 2b. Add date/time metadata if --date or --offset provided (without --place)
    if not args.place:
        if args.date:
            base_tags["DateTimeOriginal"] = args.date
            base_tags["CreateDate"] = args.date
        if args.offset:
            base_tags["OffsetTimeOriginal"] = args.offset
            base_tags["OffsetTimeDigitized"] = args.offset

    # 3. Add caption if provided.
    if args.caption:
        base_tags["Caption-Abstract"] = args.caption

    # Resolve target files.
    target_files = resolve_files(args)

    # Determine if keyword modification is requested.
    # If so, we need to read existing keywords per file.
    modify_keywords_per_file = bool(args.add_keyword or args.remove_keyword)
    keywords_to_add_set = set(args.add_keyword)
    keywords_to_remove_set = set(args.remove_keyword)

    if target_files:
        print(f"\nApplying tags to {len(target_files)} file(s).")
        for file_path in target_files:
            print(f"\nProcessing file: {file_path}")
            current_file_tags = base_tags.copy() # Start with base tags for this file

            # Handle keywords if modification is requested.
            if modify_keywords_per_file:
                existing_keywords = get_existing_keywords(file_path)
                
                # Process XMP-dc:Subject
                current_subjects = set(existing_keywords.get("XMP-dc:Subject", []))
                updated_subjects = (current_subjects.union(keywords_to_add_set)).difference(keywords_to_remove_set)
                # Only add to tags if there are actual subjects or if we're explicitly clearing them.
                if updated_subjects:
                    current_file_tags["XMP-dc:Subject"] = sorted(list(updated_subjects))
                elif keywords_to_add_set or keywords_to_remove_set: # If modification was attempted and resulted in empty, set to empty
                    current_file_tags["XMP-dc:Subject"] = ""
                
                # Process IPTC:Keywords
                current_iptc_keywords = set(existing_keywords.get("IPTC:Keywords", []))
                updated_iptc_keywords = (current_iptc_keywords.union(keywords_to_add_set)).difference(keywords_to_remove_set)
                # Only add to tags if there are actual keywords or if we're explicitly clearing them.
                if updated_iptc_keywords:
                    current_file_tags["IPTC:Keywords"] = sorted(list(updated_iptc_keywords))
                elif keywords_to_add_set or keywords_to_remove_set: # If modification was attempted and resulted in empty, set to empty
                    current_file_tags["IPTC:Keywords"] = ""

            for tag_name, tag_value in current_file_tags.items():
                print(f"Tag: {tag_name} = '{tag_value}'")
            run_exiftool([file_path], current_file_tags, args.dry_run)
        print("\nDone.")
        return

    # Legacy behavior – iterate over PATTERN_TAG_MAP.
    # Note: Keyword modification (--add-keyword, --remove-keyword) is not supported
    # in legacy mode as it requires per-file processing which is not how PATTERN_TAG_MAP works.
    if modify_keywords_per_file:
        print("Warning: --add-keyword and --remove-keyword are ignored in legacy PATTERN_TAG_MAP mode.", file=sys.stderr)

    seen = set()
    for pattern, tag_value in PATTERN_TAG_MAP.items():
        files = sorted(set(glob.glob(pattern)) - seen)
        seen.update(files)
        if not files:
            print(f"[WARN] No matches for {pattern}")
            continue
        # Use the default tag name for legacy entries.
        legacy_tags = {DEFAULT_TAG_NAME: tag_value}
        # Merge any additional tags supplied via YAML/CLI (base_tags).
        if base_tags:
            legacy_tags.update(base_tags)
        print(f"\nPattern: {pattern}")
        for tn, tv in legacy_tags.items():
            print(f"Tag: {tn} = '{tv}'")
        print(f"Files: {len(files)}")
        run_exiftool(files, legacy_tags, args.dry_run)
    print("\nDone.")


if __name__ == "__main__":
    main()
