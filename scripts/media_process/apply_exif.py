#!/usr/bin/env python3
"""apply_exif.py – Enhanced script to apply EXIF/XMP tags to images.

Features:
- Load tags from a YAML file (`--tags-yaml`).
- Specify additional tags via the command line (`--set TAG=VALUE`).
- Dry‑run mode (`--dry-run`).
- Select files with a glob pattern (`--pattern`).
- Provide an explicit list of image files (`--files`, can be repeated).
- Backward‑compatible behavior using the original `PATTERN_TAG_MAP` when no new arguments are supplied.
"""

import argparse
import glob
import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml
import json
import datetime

# Optional imports for location functionality
try:
    import requests
    from geopy.geocoders import Nominatim
    LOCATION_AVAILABLE = True
except ImportError:
    LOCATION_AVAILABLE = False

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


def run_exiftool(files: list, tags: dict, dry_run: bool, verbose: int = 0):
    """Execute the exiftool with the given files and tags."""
    if verbose >= 2:
        print(f"[DEBUG] Building exiftool command for {len(files)} file(s) with {len(tags)} tag(s)")
    
    cmd = build_exiftool_cmd(files, tags, dry_run)
    cmd_str = shlex.join(cmd)
    
    if verbose >= 1:
        print(f"[VERBOSE] Exiftool command: {cmd_str}")
    else:
        print(f"Exiftool command: {cmd_str}")

    if dry_run:
        print("Dry run: Command not executed.")
        return True

    if verbose >= 2:
        print(f"[DEBUG] Executing exiftool subprocess...")
    
    try:
        # Use subprocess.run for better error handling and capturing output.
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if verbose >= 2:
            print(f"[DEBUG] Exiftool completed with return code: {result.returncode}")
        
        # Check for warnings in output
        if result.stdout:
            if verbose >= 3:
                print(f"[DEBUG] Exiftool stdout ({len(result.stdout)} chars):")
                print(result.stdout)
            
            stdout_lower = result.stdout.lower()
            if 'warning' in stdout_lower or 'error' in stdout_lower:
                print("Exiftool warnings/errors:", file=sys.stderr)
                print(result.stdout, file=sys.stderr)
            elif result.stdout.strip() and verbose >= 1:
                print("[VERBOSE] Exiftool output:", result.stdout)
        
        if result.stderr:
            if verbose >= 3:
                print(f"[DEBUG] Exiftool stderr ({len(result.stderr)} chars):")
                print(result.stderr)
            
            stderr_lower = result.stderr.lower()
            if 'warning' in stderr_lower or 'error' in stderr_lower:
                print("Exiftool stderr:", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
        
        if verbose >= 2:
            print(f"[DEBUG] Exiftool execution successful")
        
        return True
        
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
    1. Explicit ``--files`` list (can be specified multiple times).
    2. ``--pattern`` glob.
    3. Fallback to legacy ``PATTERN_TAG_MAP`` handling.
    """
    if args.files:
        # args.files is a list from action="append", may contain multiple entries
        # Ensure paths are absolute for consistency and remove duplicates
        resolved = [str(Path(p).resolve()) for p in args.files]
        return sorted(list(set(resolved)))  # Remove duplicates and sort
    if args.pattern:
        return sorted(glob.glob(args.pattern, recursive=True))
    # Legacy mode – return an empty list; the caller will handle PATTERN_TAG_MAP.
    return []


def create_exif_metadata_from_manual_params(
    latitude=None, longitude=None, altitude=None,
    city=None, state=None, country=None, country_code=None,
    coverage=None, date_str="", offset_str=""
) -> dict:
    """Create EXIF metadata from manual location parameters (no geocoding needed).
    
    This function doesn't require geopy and creates metadata directly from provided values.
    """
    metadata = {}
    
    # Add optional date/time tags
    if date_str:
        metadata["DateTimeOriginal"] = date_str
        metadata["CreateDate"] = date_str
    if offset_str:
        metadata["OffsetTimeOriginal"] = offset_str
        metadata["OffsetTimeDigitized"] = offset_str
    
    # Add GPS coordinates if provided
    if latitude is not None:
        metadata["GPSLatitude"] = abs(latitude)
        metadata["GPSLatitudeRef"] = "N" if latitude >= 0 else "S"
    
    if longitude is not None:
        metadata["GPSLongitude"] = abs(longitude)
        metadata["GPSLongitudeRef"] = "E" if longitude >= 0 else "W"
    
    if altitude is not None:
        metadata["GPSAltitude"] = altitude
    
    # Add location text fields if provided
    if city:
        metadata["XMP-photoshop:City"] = city
        metadata["XMP-iptcExt:LocationShownCity"] = city
    
    if state:
        metadata["XMP-photoshop:State"] = state
        metadata["XMP-iptcExt:LocationShownProvinceState"] = state
    
    if country:
        metadata["XMP-photoshop:Country"] = country
        metadata["XMP-iptcExt:LocationShownCountryName"] = country
    
    if country_code:
        metadata["XMP-iptcExt:LocationShownCountryCode"] = country_code.upper()
    
    if coverage:
        metadata["XMP-dc:Coverage"] = coverage
    
    return metadata


def create_exif_metadata(place_name: str, date_str: str = "", offset_str: str = "") -> dict:
    """Generate EXIF/XMP metadata for a location and optional timestamp.

    Parameters:
    - ``place_name``: Human‑readable location (required for location tags).
    - ``date_str``:   Date/time in ``YYYY:MM:DD HH:MM:SS`` format (optional).
    - ``offset_str``: UTC offset string like ``+05:30`` (optional).
    """
    # Use shared location utilities
    try:
        from location_utils import get_location_metadata
        return get_location_metadata(place_name, date_str, offset_str)
    except ImportError:
        # Fallback to inline implementation if location_utils not available
        import requests
        geolocator = Nominatim(user_agent="exif_metadata_generator")
        location = geolocator.geocode(place_name, addressdetails=True, language='en', extratags=True)
        if not location:
            raise ValueError(f"Could not geocode place: {place_name}")

        address = location.raw.get('address', {}) if isinstance(location.raw, dict) else {}
        namedetails = location.raw.get('namedetails', {}) if isinstance(location.raw, dict) else {}
        city = address.get('city') or address.get('town') or namedetails.get('city') or ""
        state = address.get('state') or namedetails.get('state') or ""
        country = address.get('country') or namedetails.get('country') or ""
        country_code = address.get('country_code', "").upper()

        altitude = None
        extratags = location.raw.get('extratags', {}) if isinstance(location.raw, dict) else {}
        if extratags is not None:
            if 'ele' in extratags:
                altitude = extratags['ele']
            elif 'elevation' in extratags:
                altitude = extratags['elevation']
        try:
            altitude = float(altitude)
        except (TypeError, ValueError):
            altitude = 0
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
                pass
        
        metadata = {}
        if date_str:
            metadata["DateTimeOriginal"] = date_str
            metadata["CreateDate"] = date_str
        if offset_str:
            metadata["OffsetTimeOriginal"] = offset_str
            metadata["OffsetTimeDigitized"] = offset_str
        metadata.update({
            "GPSLatitude": abs(location.latitude),
            "GPSLatitudeRef": "N" if location.latitude >= 0 else "S",
            "GPSLongitude": abs(location.longitude),
            "GPSLongitudeRef": "E" if location.longitude >= 0 else "W",
            "GPSAltitude": altitude,
            "XMP-photoshop:City": city,
            "XMP-photoshop:State": state,
            "XMP-photoshop:Country": country,
            "XMP-iptcExt:LocationShownCity": city,
            "XMP-iptcExt:LocationShownProvinceState": state,
            "XMP-iptcExt:LocationShownCountryName": country,
            "XMP-iptcExt:LocationShownCountryCode": country_code,
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


def verify_exif_written(file_path: str, expected_tags: dict, verbose: int = 0) -> bool:
    """Verify that EXIF tags were actually written to the file.
    
    Args:
        file_path: Path to the file to check
        expected_tags: Dictionary of tags that should have been written
        verbose: Verbosity level
    
    Returns:
        True if at least one tag is verified, False otherwise
    """
    try:
        if verbose >= 2:
            print(f"[DEBUG] Verifying EXIF write for: {file_path}")
        
        # Check a few key tags to verify write succeeded
        verify_tags = []
        if 'GPSLatitude' in expected_tags:
            verify_tags.append('GPSLatitude')
        elif 'XMP-photoshop:City' in expected_tags:
            verify_tags.append('XMP-photoshop:City')
        elif 'XMP-dc:Subject' in expected_tags:
            verify_tags.append('XMP-dc:Subject')
        
        if not verify_tags:
            # No specific tags to verify, assume success
            if verbose >= 2:
                print(f"[DEBUG] No specific tags to verify, assuming success")
            return True
        
        if verbose >= 2:
            print(f"[DEBUG] Will verify tag: {verify_tags[0]}")
        
        # Use exiftool to read back one tag
        cmd = ['exiftool', '-' + verify_tags[0], '-s3', file_path]
        if verbose >= 3:
            print(f"[DEBUG] Verification command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if verbose >= 3:
            print(f"[DEBUG] Verification result stdout: '{result.stdout.strip()}'")
            print(f"[DEBUG] Verification result stderr: '{result.stderr.strip()}'")
        
        # If we got any output, the tag was written
        success = bool(result.stdout.strip())
        
        if verbose >= 2:
            print(f"[DEBUG] Verification {'succeeded' if success else 'FAILED'}")
        
        return success
        
    except Exception as e:
        # Verification failed, but don't block the process
        if verbose >= 1:
            print(f"  [VERBOSE] Could not verify EXIF write: {e}", file=sys.stderr)
        else:
            print(f"  Note: Could not verify EXIF write: {e}", file=sys.stderr)
        return True  # Assume success


def check_file_in_database(db_path: str, file_path: str) -> bool:
    """Check if a file exists in the database.
    
    Args:
        db_path: Path to the database file
        file_path: Path to the file to check
    
    Returns:
        True if file is in database, False otherwise
    """
    if not os.path.exists(db_path):
        return False
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check by absolute path
        abs_path = os.path.abspath(file_path)
        cursor.execute("SELECT id FROM files WHERE fullpath = ?", (abs_path,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    except Exception as e:
        print(f"Warning: Could not check database for {file_path}: {e}", file=sys.stderr)
        return False


def reprocess_file_in_database(db_path: str, file_path: str, verbose: int = 0) -> bool:
    """Reprocess a file in the database by calling index_media for just this file.
    
    Args:
        db_path: Path to the database file
        file_path: Path to the file to reprocess
        verbose: Verbosity level (0=quiet, 1=normal, 2=debug, 3=trace)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess
        import os
        import sqlite3
        
        if verbose >= 2:
            print(f"[DEBUG] Starting database reprocess for: {file_path}")
        
        # Get the volume for this file from the database
        abs_path = os.path.abspath(file_path)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT volume FROM files WHERE fullpath = ? LIMIT 1", (abs_path,))
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                print(f"Warning: File not found in database: {file_path}", file=sys.stderr)
                return False
            
            volume = result[0]
            if verbose >= 2:
                print(f"[DEBUG] File volume in database: {volume}")
        except Exception as e:
            print(f"Warning: Could not query database for volume: {e}", file=sys.stderr)
            return False
        
        # Find index_media.py in the same directory as this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        index_media_script = os.path.join(script_dir, 'index_media.py')
        
        if verbose >= 2:
            print(f"[DEBUG] Looking for index_media.py at: {index_media_script}")
        
        if not os.path.exists(index_media_script):
            print(f"Warning: index_media.py not found at {index_media_script}", file=sys.stderr)
            return False
        
        # Get the directory and file for index_media
        file_dir = os.path.dirname(os.path.abspath(file_path))
        file_name = os.path.basename(file_path)
        
        if verbose >= 2:
            print(f"[DEBUG] File directory: {file_dir}")
            print(f"[DEBUG] File name: {file_name}")
        
        # Build command to reindex just this file
        # Use regex to match exact filename (escape special regex chars)
        # 
        # Note: index_media.py matches patterns against the FULL PATH, not just the filename.
        # To match a specific file, we need a pattern that matches the filename at the END
        # of the path (after a path separator).
        # 
        # Pattern format: [/\]<escaped_filename>$
        #   [/\\] - Matches either / (Unix) or \ (Windows) path separator
        #   <escaped_filename> - The filename with regex special chars escaped
        #   $ - Anchors to end of string (ensures exact filename match)
        #
        # This pattern is more specific than typical index_media.py patterns (like ".jpg" 
        # or "2024") and won't interfere with normal usage.
        import re
        escaped_filename = re.escape(file_name)
        pattern = f'[/\\\\]{escaped_filename}$'
        
        if verbose >= 2:
            print(f"[DEBUG] Filename pattern: {pattern}")
        
        cmd = [
            'python3',
            index_media_script,
            '--path', file_dir,
            '--volume', volume,  # Use the same volume as originally indexed
            '--db-path', db_path,
            '--include-pattern', pattern,  # Match filename at end of path
            # Pass --check-existing with 'hash' to force re-computation
            # Since we just updated EXIF, the file metadata changed, so we want to update the DB
            # Using 'hash' as check criteria means it will compute hash, not find a match
            # (because hash hasn't changed), and proceed to update logic
            '--check-existing', 'hash'  # Check by hash - won't match, will update
        ]
        
        if verbose >= 1:
            print(f"  Reprocessing in database: {file_path}")
        
        if verbose >= 1:
            cmd.append('--verbose')
            cmd.append(str(min(verbose, 3)))  # Pass verbosity to index_media
        
        if verbose >= 2:
            print(f"[DEBUG] Reprocess command: {' '.join(cmd)}")
        
        # Run index_media to update the file's metadata
        if verbose >= 2:
            print(f"[DEBUG] Executing index_media subprocess...")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if verbose >= 2:
            print(f"[DEBUG] index_media completed with return code: {result.returncode}")
        
        if verbose >= 3:
            print(f"[DEBUG] index_media stdout:")
            print(result.stdout)
            print(f"[DEBUG] index_media stderr:")
            print(result.stderr)
        
        if result.returncode != 0:
            print(f"  ⚠ Database reprocess returned code {result.returncode}", file=sys.stderr)
            if verbose >= 1:
                print(f"  [VERBOSE] Stdout: {result.stdout}")
                print(f"  [VERBOSE] Stderr: {result.stderr}")
            return False
        
        if verbose >= 1:
            print(f"  ✓ Database updated")
        
        return True
        
    except subprocess.TimeoutExpired:
        print(f"Warning: Reprocessing timed out for {file_path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Warning: Could not reprocess {file_path}: {e}", file=sys.stderr)
        if verbose >= 2:
            import traceback
            print(f"[DEBUG] Exception traceback:")
            traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Apply EXIF/XMP tags to images.")
    parser.add_argument("--dry-run", action="store_true", help="Print exiftool commands without writing.")
    parser.add_argument("--tags-yaml", type=str, help="Path to a YAML file containing tag name/value pairs.")
    parser.add_argument("--set", action="append", default=[], metavar="TAG=VALUE", help="Tag to set (can be repeated).")
    parser.add_argument("--pattern", type=str, help="Glob pattern to select image files.")
    parser.add_argument("--files", action="append", default=[], help="Image file to process (can be repeated).")
    
    # Location metadata - either lookup by place OR specify manually
    parser.add_argument("--place", type=str, help="Place name for location metadata (e.g., 'Fort Worth, Texas, USA'). If specified, will geocode this location.")
    
    # Manual location controls (used if --place is NOT specified)
    parser.add_argument("--latitude", type=float, help="GPS latitude (-90 to 90, North is positive).")
    parser.add_argument("--longitude", type=float, help="GPS longitude (-180 to 180, East is positive).")
    parser.add_argument("--altitude", type=float, help="GPS altitude in meters.")
    parser.add_argument("--city", type=str, help="City name for location metadata.")
    parser.add_argument("--state", type=str, help="State/province name for location metadata.")
    parser.add_argument("--country", type=str, help="Country name for location metadata.")
    parser.add_argument("--country-code", type=str, help="Country code (e.g., 'US').")
    parser.add_argument("--coverage", type=str, help="Human-readable location description (stored in XMP-dc:Coverage tag, e.g., full address).")
    
    # Date/time metadata
    parser.add_argument("--date", type=str, help="Date/time string in 'YYYY:MM:DD HH:MM:SS' format.")
    parser.add_argument("--offset", type=str, help="UTC offset string like '+05:30' or '-06:00'.")
    # Ensure sys is available for error handling
    import sys
    # New arguments for keywords and caption
    parser.add_argument("--add-keyword", action="append", default=[], help="Keyword to add (can be repeated).")
    parser.add_argument("--remove-keyword", action="append", default=[], help="Keyword to remove if present.")
    parser.add_argument("--caption", type=str, help="Caption text to set as Caption-Abstract.")
    parser.add_argument("--limit", type=int, help="Limit number of files to process (useful with --dry-run for testing).")
    
    # Database integration
    parser.add_argument("--db-path", type=str, help="Path to media database. If provided, will check if files are indexed and reprocess them after EXIF update.")
    parser.add_argument("--reprocess-db", action="store_true", help="Reprocess files in database after EXIF update (requires --db-path).")
    
    # Verbosity
    parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2, 3],
                       help="Verbosity level: 0=quiet, 1=verbose, 2=debug, 3=trace (default: 0)")
    
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

    # 2. Add location metadata
    # Priority: --place (geocode lookup) OR manual location parameters
    if args.place:
        # Use place lookup with geocoding
        try:
            location_metadata = create_exif_metadata(args.place, args.date, args.offset)
            base_tags.update(location_metadata)
            print(f"Using geocoded location: {args.place}")
        except (ValueError, requests.exceptions.RequestException) as e:
            print(f"Error generating location metadata: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Check if any manual location parameters are provided
        has_manual_location = any([
            args.latitude is not None,
            args.longitude is not None,
            args.altitude is not None,
            args.city,
            args.state,
            args.country,
            getattr(args, 'country_code', None),
            args.coverage
        ])
        
        if has_manual_location:
            # Use manual location parameters (no geocoding needed)
            location_metadata = create_exif_metadata_from_manual_params(
                latitude=args.latitude,
                longitude=args.longitude,
                altitude=args.altitude,
                city=args.city,
                state=args.state,
                country=args.country,
                country_code=getattr(args, 'country_code', None),
                coverage=args.coverage,
                date_str=args.date or "",
                offset_str=args.offset or ""
            )
            base_tags.update(location_metadata)
            print(f"Using manual location parameters")
            if args.latitude is not None and args.longitude is not None:
                print(f"  GPS: {args.latitude}, {args.longitude}")
            if args.city or args.state or args.country:
                location_str = ", ".join(filter(None, [args.city, args.state, args.country]))
                print(f"  Location: {location_str}")
        else:
            # No location parameters, just add date/time if provided
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
        # Apply limit if specified
        if args.limit and args.limit > 0:
            original_count = len(target_files)
            target_files = target_files[:args.limit]
            print(f"\nLimit applied: Processing {len(target_files)} of {original_count} file(s).")
        else:
            print(f"\nApplying tags to {len(target_files)} file(s).")
        
        if args.verbose >= 2:
            print(f"[DEBUG] Verbosity level: {args.verbose}")
            print(f"[DEBUG] Dry run: {args.dry_run}")
            print(f"[DEBUG] Database path: {args.db_path}")
            print(f"[DEBUG] Reprocess database: {args.reprocess_db}")
            print(f"[DEBUG] Base tags to apply: {base_tags}")
            print(f"[DEBUG] Files to process: {target_files}")
        
        for file_path in target_files:
            print(f"\nProcessing file: {file_path}")
            
            if args.verbose >= 2:
                print(f"[DEBUG] ========== Processing: {file_path} ==========")
                print(f"[DEBUG] File exists: {os.path.exists(file_path)}")
                if os.path.exists(file_path):
                    import stat
                    st = os.stat(file_path)
                    print(f"[DEBUG] File size: {st.st_size} bytes")
                    print(f"[DEBUG] File permissions: {oct(st.st_mode)}")
            
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

            if args.verbose >= 2:
                print(f"[DEBUG] Tags to apply for {file_path}:")
            
            for tag_name, tag_value in current_file_tags.items():
                print(f"Tag: {tag_name} = '{tag_value}'")
            
            # Apply EXIF tags
            if args.verbose >= 2:
                print(f"[DEBUG] Step 1: Writing EXIF tags to file...")
            
            try:
                run_exiftool([file_path], current_file_tags, args.dry_run, verbose=args.verbose)
                
                if not args.dry_run:
                    if args.verbose >= 2:
                        print(f"[DEBUG] Step 2: Verifying EXIF write...")
                    
                    # Verify EXIF was actually written
                    if verify_exif_written(file_path, current_file_tags, verbose=args.verbose):
                        print(f"  ✓ EXIF tags written successfully")
                    else:
                        print(f"  ⚠ EXIF tags may not have been written", file=sys.stderr)
                
            except Exception as e:
                print(f"  ✗ Failed to write EXIF tags: {e}", file=sys.stderr)
                if args.verbose >= 2:
                    import traceback
                    print(f"[DEBUG] Exception details:")
                    traceback.print_exc()
                continue  # Skip reprocessing if EXIF write failed
            
            # Check if file is in database and reprocess if requested
            if args.db_path and args.reprocess_db and not args.dry_run:
                if args.verbose >= 2:
                    print(f"[DEBUG] Step 3: Checking if file is in database...")
                
                # Small delay to ensure filesystem sync (especially on network drives)
                import time
                if args.verbose >= 2:
                    print(f"[DEBUG] Waiting 200ms for filesystem sync...")
                time.sleep(0.2)  # Increased to 200ms for better reliability
                
                if check_file_in_database(args.db_path, file_path):
                    if args.verbose >= 1:
                        print(f"  File found in database, reprocessing...")
                    if args.verbose >= 2:
                        print(f"[DEBUG] Step 4: Reprocessing file in database...")
                    
                    success = reprocess_file_in_database(args.db_path, file_path, verbose=args.verbose)
                    if not success:
                        print(f"  Warning: Reprocessing failed, database may be out of sync", file=sys.stderr)
                else:
                    if args.verbose >= 1:
                        print(f"  (File not in database, skipping reprocess)")
                    if args.verbose >= 2:
                        print(f"[DEBUG] File {file_path} not found in database")
        
        # Summary
        if args.db_path and args.reprocess_db and not args.dry_run:
            print(f"\n✓ EXIF tags applied and database updated for {len(target_files)} file(s).")
        else:
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
