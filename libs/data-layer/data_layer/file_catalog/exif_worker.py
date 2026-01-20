import os
import datetime
import hashlib
from types import SimpleNamespace
import time
import meilisearch
from PIL.ExifTags import TAGS
from PIL.TiffImagePlugin import IFDRational
from pymediainfo import MediaInfo
import magic
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from exiftool import ExifToolHelper
import sys
from collections import defaultdict
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
target_package_dir = os.path.join(libs_root_path, 'py-file-helpers')
sys.path.insert(0, target_package_dir)

from py_file_helpers.file_types import file_matches_patterns
from py_file_helpers.exif import get_thumbnail

# --- Standard EXIF GPS Tag IDs ---
# These are universal across all files following the EXIF standard
GPS_TAGS = {
    # Reference Tags (N/S, E/W, Altitude ref)
    "LATITUDE_REF": 1,
    "LONGITUDE_REF": 3,
    "ALTITUDE_REF": 5,
    # Value Tags (DMS tuples, IFDRational objects)
    "LATITUDE": 2,
    "LONGITUDE": 4,
    "ALTITUDE": 6,
    # Time/Date/Direction
    "TIME_STAMP": 7,
    "DATE_STAMP": 29,
    "IMG_DIRECTION": 16,  # GPSImgDirection
}
# --- Configuration ---
# Your Synology IP and Meilisearch Port
from .config import MEILI_URL, MEILI_API_KEY, INDEX_NAME

# SCAN_DIR = "/mnt/video"  # e.g., /volume1/photos
# VOLUME_TAG = "SYN_VIDEO"

# SCAN_DIR = "/mnt/photo"  # e.g., /volume1/photos
# VOLUME_TAG = "SYN_PHOTO"

FOLDERS_INDEX = "catalog_folders"
FOLDER_BATCH_SIZE = 500
BATCH_SIZE = 1
TOTAL_TARGET = 100000
BIG_SIZE = 100000000
# ---------------------

# Initialize Client
client = meilisearch.Client(MEILI_URL, MEILI_API_KEY)

import hashlib


def folder_id(volume: str, dir_path: str) -> str:
    key = f"{volume}|{dir_path}".encode("utf-8")
    h = hashlib.sha1(key).hexdigest()  # 40 hex chars (alphanumeric)
    return f"f_{volume}_{h}"  # uses only [a-zA-Z0-9_]


def extract_exif_from_raw(filepath):
    """Extracts all metadata from any file, including proprietary RAW formats."""
    try:
        # ExifToolHelper handles running the command-line tool internally
        with ExifToolHelper() as et:
            # Execute the command to get the JSON output
            metadata_list = et.get_metadata(filepath)

            if metadata_list:
                # ExifTool returns a list containing one dictionary per file
                raw_metadata = metadata_list[0]

                # Clean and flatten the metadata for Meilisearch
                processed_data = {}
                for key, value in raw_metadata.items():
                    # ExifTool prepends the group (e.g., 'EXIF:Make', 'GPS:GPSLatitude')
                    # We can clean this up and convert GPS data later.
                    clean_key = key.split(':')[-1]
                    processed_data[clean_key] = value

                # You must still process the precise GPS coordinates
                # (converting IFDRational/string formats) separately.
                return processed_data

    except Exception as e:
        print(f"Error extracting metadata from RAW file {filepath}: {e}")
        return None


def _convert_dms_to_decimal(dms, ref):
    """Converts Degrees, Minutes, Seconds (DMS) tuple to Decimal degrees."""
    if not isinstance(dms, (list, tuple)) or len(dms) != 3:
        return None

    try:
        # NOTE: dms values are likely IFDRational objects here, which float() handles
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])

        decimal = degrees + (minutes / 60) + (seconds / 3600)

        # Apply reference (e.g., 'S' or 'W' mean negative decimal value)
        if isinstance(ref, str) and ref.upper() in ['S', 'W']:
            return -decimal
        return decimal
    except Exception:
        return None


def convert_raw_gps_info(raw_gps_info):
    """
    Converts a raw GPSInfo dictionary (using integer keys)
    into a flat dictionary of decimal values.
    """
    if not isinstance(raw_gps_info, dict):
        return {}

    gps = {}

    # 1. Latitude
    lat_ref = raw_gps_info.get(GPS_TAGS["LATITUDE_REF"], 'N')
    lat_dms = raw_gps_info.get(GPS_TAGS["LATITUDE"])
    gps['latitude'] = _convert_dms_to_decimal(lat_dms, lat_ref)

    # 2. Longitude
    lon_ref = raw_gps_info.get(GPS_TAGS["LONGITUDE_REF"], 'E')
    lon_dms = raw_gps_info.get(GPS_TAGS["LONGITUDE"])
    gps['longitude'] = _convert_dms_to_decimal(lon_dms, lon_ref)

    # 3. Altitude
    # Tag 5: Altitude Reference (0 = above sea level, 1 = below sea level)
    alt_ref = raw_gps_info.get(GPS_TAGS["ALTITUDE_REF"], 0)
    altitude_val = raw_gps_info.get(GPS_TAGS["ALTITUDE"])  # Tag 6

    if altitude_val is not None:
        try:
            # Convert IFDRational altitude (Tag 6) to float
            altitude = float(altitude_val)
            if alt_ref == 1:
                altitude = -altitude  # Apply below-sea-level reference
            gps['altitude'] = altitude
        except Exception:
            pass

    # 4. Image Direction
    # Tag 16 (GPSImgDirection) is likely an IFDRational object
    img_direction = raw_gps_info.get(GPS_TAGS["IMG_DIRECTION"])
    if img_direction is not None:
        try:
            gps['direction'] = float(img_direction)
        except Exception:
            pass

    return gps


def create_thumbnail(filepath, max_size=(128, 128), output_format='JPEG', quality=85, format="binary"):
    """
    Creates a small thumbnail, encodes it to Base64, and prepends the Data URI scheme.

    Args:
        filepath (str): The full path to the original image file.
        max_size (tuple): The maximum width and height (e.g., (128, 128)).
        output_format (str): The format for the encoded thumbnail (e.g., 'JPEG', 'PNG').
        quality (int): JPEG quality from 0 to 100.

    Returns:
        str: A Data URI string (e.g., 'data:image/jpeg;base64,...') or None on failure.
    """
    if not os.path.exists(filepath):
        raise Exception("Filepath not found")

    try:
        # 1. Open and Process the Image
        img = Image.open(filepath)

        # Create a copy and use .thumbnail() to preserve the aspect ratio in place
        img.thumbnail(max_size)

        # 2. Save the Thumbnail to In-Memory Buffer (BytesIO)
        # This avoids writing a temporary file to disk.
        buffer = BytesIO()
        # Save the image into the buffer, specifying the format
        img.save(buffer, format=output_format, quality=quality)
        buffer.seek(0)
        if format == "binary": return buffer

        # 3. Base64 Encode the Binary Data
        img_bytes = buffer.getvalue()
        base64_encoded = base64.b64encode(img_bytes)

        # 4. Convert bytes to a string and prepend the Data URI scheme
        # This makes it ready for direct use in HTML <img> tags
        mime_type = f"image/{output_format.lower()}"
        base64_string = base64_encoded.decode('utf-8')

        return f"data:{mime_type};base64,{base64_string}"

    except UnidentifiedImageError:
        # File is not a recognizable image format
        raise Exception(f"File at {filepath} is not a recognizable image.")
    except Exception as e:
        # Handle other errors (e.g., file corruption, permissions)
        raise Exception(f"Error in thumbnail creation: {filepath}: {e}")


def extract_and_prepare_video_metadata(file_path):
    """
    Extracts key video and audio metadata using MediaInfo and prepares
    a dictionary suitable for Meilisearch indexing.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return None

    try:
        # Load all metadata from the file
        media_info = MediaInfo.parse(file_path)

        # Initialize dictionary to hold flattened data
        video_metadata = {}

        # --- 1. Iterate through tracks to find Video and Audio streams ---

        for track in media_info.tracks:
            # --- VIDEO TRACK ---
            if track.track_type == 'Video':
                # Basic dimensions and rate
                video_metadata['video_width'] = track.width
                video_metadata['video_height'] = track.height

                # Framerate conversion (often a string or float)
                if track.frame_rate:
                    try:
                        video_metadata['video_framerate'] = float(track.frame_rate)
                    except ValueError:
                        pass  # Ignore if it's an unparsable string

                # Codec/Encoder info
                video_metadata['video_encoder'] = track.codec_long_name or track.codec

            # --- AUDIO TRACK ---
            elif track.track_type == 'Audio':
                # We prioritize the first audio track found
                if 'audio_channels' not in video_metadata:

                    # Bit Rate (often in bps, convert to Mbps for easier filtering)
                    if track.bit_rate:
                        video_metadata['audio_bit_rate_kbps'] = track.bit_rate / 1000  # Store in Kbps

                    video_metadata['audio_channels'] = track.channel_s

            # --- GENERAL TRACK (Container Info) ---
            elif track.track_type == 'General':
                # Duration (convert milliseconds to seconds)
                if track.duration:
                    video_metadata['duration_seconds'] = track.duration / 1000.0

        # Note: The video_metadata dictionary now contains the flattened,
        # cleaned data you requested.
        return video_metadata

    except Exception as e:
        print(f"Error extracting metadata from {file_pth}: {e}")
        return None


RAW_EXTS = [
    'rw2', 'c42', 'nef'
]


def is_file_an_image_magic(filepath):
    mime_type = magic.from_file(filepath, mime=True)
    if mime_type.startswith('image/'): return True
    extension = os.path.splitext(filepath)[1].lower().replace('.', '')
    if extension in RAW_EXTS: return True
    return False


# skip file
# exclude, include: glob patterns

def skip_file(doc, args=SimpleNamespace()):
    exclude = args.exclude if hasattr(args, "exclude") else None
    include = args.include if hasattr(args, "include") else None
    if include is not None and not file_matches_patterns(doc["path"].lower(), include): return True
    if exclude is not None and file_matches_patterns(doc["path"].lower(), exclude): return True
    if doc["size"] < 100000: return False  # re do the hash etc.
    search_results = find_document(doc)
    return len(search_results["hits"]) == 1


def calculate_file_hash(filepath, blocksize=65536):
    """Calculates the SHA256 hash of a file's content."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as afile:
        buf = afile.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(blocksize)
    return hasher.hexdigest()


def get_exif(filepath):
    """Extract EXIF data and flatten it for easier search"""
    exif_raw = extract_exif_from_raw(filepath)
    exif_clean = {}
    if exif_raw:
        for tag, value in exif_raw.items():
            decoded = TAGS.get(tag, tag)
            # Convert bytes to string if needed
            if isinstance(value, bytes):
                try:
                    value = value.decode()
                except:
                    value = str(value)
            exif_clean[str(decoded)] = value
    return exif_clean

    exif_clean = {}
    try:
        with Image.open(filepath) as img:
            exif_raw = img._getexif()
            if exif_raw:
                for tag, value in exif_raw.items():
                    decoded = TAGS.get(tag, tag)
                    # Convert bytes to string if needed
                    if isinstance(value, bytes):
                        try:
                            value = value.decode()
                        except:
                            value = str(value)
                    exif_clean[str(decoded)] = value
    except Exception:
        pass  # Not an image or no EXIF
    return exif_clean


def generate_id(full_file_path, mount_path, volume_tag):
    """Meilisearch needs a valid string ID. We hash the filepath."""
    relative_path_local = os.path.relpath(full_file_path, mount_path)

    # 2. Calculate Content Hash (as before)
    content_hash = calculate_file_hash(full_file_path)  # Assumes function exists
    return (hashlib.md5(f"{volume_tag}/{relative_path_local}::{content_hash}".encode('utf-8')).hexdigest(),
            content_hash)


# --- Helper Functions (Private) ---

def _convert_dms_to_decimal(dms, ref):
    """Converts Degrees/Minutes/Seconds tuple to Decimal degrees."""
    if not isinstance(dms, (list, tuple)) or len(dms) != 3:
        return None

    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + (minutes / 60) + (seconds / 3600)

        # Apply reference (N/S for Latitude, E/W for Longitude)
        if ref in ['S', 'W', '1']:
            return -decimal
        return decimal
    except Exception:
        return None


def _sanitize_value(value):
    """Recursively converts non-standard Python objects (IFDRational, bytes) to JSON-safe types."""

    # 1. Handle IFDRational (Convert to float)
    if isinstance(value, IFDRational):
        if value.denominator == 0:
            return "undefined"
        return float(value)

        # 2. Handle Bytes (Convert to string, ignoring binary data like thumbnails)
    elif isinstance(value, bytes):
        # Skip large binary fields (>1KB), otherwise decode to string
        if len(value) > 1024:
            return None
        return value.decode('utf-8', errors='replace')

        # 3. Handle Lists/Tuples and Dictionaries Recursively
    elif isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}

    # 4. Default
    else:
        return value


# --- Main EXIF Function ---

def flatten_and_sanitize_video_data(raw_data):
    """
    Cleans raw EXIF data and flattens specific fields for Meilisearch indexing.

    ASSUMPTION: raw_exif_data uses integer IDs or standard string names
    (e.g., 'GPSInfo') for keys. You must adjust keys if your library uses different names.
    """
    if not raw_data:
        return {}
    sanitized_data = _sanitize_value(raw_data)
    # 1. Clean all complex types recursively
    document = {}

    # Helper to safely extract and flatten a field
    def pop_and_flatten(key, new_key=None):
        value = sanitized_data.pop(key, None)
        if value is not None:
            document[new_key or key] = value

    # 2. Flatten Specific Fields (Keys below are examples; adjust to your library's output!)

    # Dimensions (often simple attributes on the Image object, but sometimes in EXIF)
    pop_and_flatten('video_width', 'width')
    pop_and_flatten('video_height', 'height')

    # Datetime and Exposure
    pop_and_flatten('video_framerate', 'frame_rate')
    pop_and_flatten('video_encoder', 'video_encoder')
    pop_and_flatten('audio_encoder', 'audio_encoder')
    pop_and_flatten('audio_channels', 'channels')

    # 4. Store remaining EXIF data cleanly
    document['video_data'] = sanitized_data.get('video_data')

    return document


def exposure_time_to_setting(exposure_time):
    """
    Converts the precise exposure time in seconds to a human-readable
    fractional camera setting (e.g., '1/2000').

    Args:
        exposure_time (float): The precise duration in seconds.

    Returns:
        str: The human-readable fractional shutter speed.
    """
    if exposure_time is None:
        return "N/A"

    try:
        if exposure_time >= 0.5:
            # Long exposure: display as seconds (e.g., 2.5s)
            return f"{round(exposure_time, 1)}s"
        else:
            # Short exposure: Invert and round to get the denominator
            denominator_float = 1 / exposure_time
            denominator = round(denominator_float)
            return f"1/{denominator}"

    except Exception as e:
        print(f"Error converting time: {e}")
        return "Error"


def flatten_and_sanitize_exif(raw_data):
    if not raw_data:
        return {}

    # 1. Clean all complex types recursively
    sanitized_data = _sanitize_value(raw_data)
    document = {}

    # Helper to safely extract and flatten a field
    def pop_and_flatten(keys, new_key=None):
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            value = sanitized_data.pop(key, None)
            if value is not None:
                document[new_key or key] = value
                return

    # 2. Flatten Specific Fields (Keys below are examples; adjust to your library's output!)

    # Dimensions (often simple attributes on the Image object, but sometimes in EXIF)
    pop_and_flatten('ExifImageWidth', 'width')
    pop_and_flatten('ExifImageHeight', 'height')

    # Datetime and Exposure
    pop_and_flatten('DateTimeOriginal', 'datetime_taken')
    exposure_time = exposure_time_to_setting(sanitized_data.pop('ExposureTime', None))
    document['exposure_time'] = exposure_time
    pop_and_flatten('ExposureTime', 'exposure_time')
    pop_and_flatten('FocalLength', 'focal_length')
    pop_and_flatten(['FocalLengthIn35mmFilm', 'FocalLengthIn35mmFormat'], 'focal_length35mm')
    pop_and_flatten('FNumber', 'f_number')
    pop_and_flatten('ExifImageWidth', 'width')
    pop_and_flatten('ExifImageHeight', 'height')
    pop_and_flatten('Make', 'camera_make')
    pop_and_flatten('Model', 'camera_model')
    pop_and_flatten('LensModel', 'lens_model')
    pop_and_flatten('ISOSpeedRatings', 'iso')
    # 3. GPS Conversion (Requires the GPSInfo dictionary, usually under 'GPSInfo' or its ID)
    gps_info = sanitized_data.pop('GPSInfo', None)  # Use the key your library outputs
    if gps_info and isinstance(gps_info, dict):
        gps_data = convert_raw_gps_info(gps_info)
        # a. Latitude/Longitude
        document['latitude'] = gps_data["latitude"]

        document['longitude'] = gps_data["longitude"]

        # b. Altitude

        document['altitude'] = gps_data["altitude"] if "altitude" in gps_data else None

        # c. Direction (often GPSImgDirection)
        pop_and_flatten('GPSImgDirection', 'direction')

    # 4. Store remaining EXIF data cleanly
    document['exif_data_raw'] = sanitized_data

    return document


def clear_all_docs():
    try:
        client.index(INDEX_NAME).delete_all_documents()
        client.wait_for_task()
    except Exception as e:
        print(f"Error during document deletion: {e}")


def create_document(filepath, file, scan_dir, volume_tag, skip_on, current_dir_files):
    logs = []
    stats = os.stat(filepath)
    if (stats.st_size > BIG_SIZE):
        print(f"Processing ({round(stats.st_size / 1024 / 1024, 2)}): {filepath} MB")
    doc = {
        "volume": volume_tag,
        "name": file,
        "mime": magic.from_file(filepath, mime=True),
        "path": filepath,
        "relative_path": os.path.relpath(filepath, scan_dir),
        "extension": os.path.splitext(file)[1].lower().replace('.', ''),
        "size": stats.st_size,
        "created": datetime.datetime.fromtimestamp(stats.st_ctime).isoformat(),
        "modified": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat()
    }
    # if skip_file(doc, args):
    if skip_file(doc):
        print("Excluding: " + doc["name"])
        return ("EXCLUDE", logs)

    def do_skip_on():
        if skip_on == None: return False
        server_file = current_dir_files.get(file, None)
        if server_file is None: return False
        for skip_field in skip_on:
            if "skip_field" not in server_file: return False
            if doc[skip_field] != server_file[skip_field]: return False
        return True

    if do_skip_on():
        print("Skipping: " + doc["name"])
        return ("SKIP", logs)

    print("Doing: " + doc["name"])
    (doc["id"], doc["hash"]) = generate_id(filepath, scan_dir, volume_tag)

    # If Image, add EXIF (Flattened into the main object or nested)
    if is_file_an_image_magic(filepath):
        exif_data = get_exif(filepath)
        exif_data = flatten_and_sanitize_exif(exif_data)
        doc['thumbnail'] = get_thumbnail(filepath)
        if doc['thumbnail'] is None:
            try:
                doc['thumbnail'] = create_thumbnail(filepath)
            except Exception as e:
                logs.append("Warning: " + e.__str__())
        # Add specific EXIF fields you want to search heavily

        if 'DateTimeOriginal' in exif_data: doc['date_taken'] = exif_data['DateTimeOriginal']

        # Store full EXIF data as a nested object for detail view
        doc['exif'] = exif_data

    elif doc['extension'] in ['mp4', 'mkv']:
        video_data = extract_and_prepare_video_metadata(filepath)
        video_data = flatten_and_sanitize_video_data(video_data)
        doc['video_data'] = video_data
    doc["path"] = doc["relative_path"]
    del doc["relative_path"]
    doc["path"] = "/" + doc["path"][:-len(doc["name"])]
    return (doc, logs)


def index_by_name(list_of_dicts):
    """
    Converts a list of dictionaries into a single dictionary indexed by the 'name' field.

    Args:
        list_of_dicts (list): A list of dictionaries, where each dictionary
                              is expected to have a 'name' key.

    Returns:
        dict: A dictionary where keys are the 'name' values and values are
              the original dictionaries.
    """
    indexed_dict = {}
    for item_dict in list_of_dicts:
        if 'name' in item_dict:
            indexed_dict[item_dict['name']] = item_dict
        else:
            print(f"Warning: Dictionary {item_dict} does not have a 'name' key and will be skipped.")
    return indexed_dict


def norm_dir(p: str) -> str:
    if not p:
        return "/"
    s = str(p).replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s)
    if not s.startswith("/"):
        s = "/" + s
    if len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s or "/"


def parent_dir(d: str) -> str:
    d = norm_dir(d)
    if d == "/":
        return "/"  # root’s parent as "/" (convenient for querying root children)
    i = d.rfind("/")
    return "/" if i <= 0 else (d[:i] or "/")


def leaf_name(d: str) -> str:
    d = norm_dir(d)
    return "/" if d == "/" else d.split("/")[-1]


def depth(d: str) -> int:
    d = norm_dir(d)
    return 0 if d == "/" else len([p for p in d.split("/") if p])


def iter_ancestors(d: str):
    d = norm_dir(d)
    while True:
        yield d
        if d == "/":
            break
        d = parent_dir(d)


def scan_and_upload(pmts, task_interface):
    scan_dir = pmts["scan_dir"]
    volume_tag = pmts["volume_tag"]
    skip_on = None
    start_dir = scan_dir

    kwargs = pmts.get("kwargs", None)
    if kwargs is not None:
        skip_on = kwargs.get("skip_on", None)
        if skip_on is not None:
            skip_on = skip_on.split(",")
        if "start_dir" in kwargs:
            start_dir = os.path.join(scan_dir, kwargs["start_dir"])

    task_id = pmts["task_id"]

    documents = []
    done_count = 0
    skip_count = 0

    print(f"Scanning {scan_dir}...")

    # ----------------------------
    # NEW: folder stats accumulators
    # ----------------------------
    folder_direct_counts = defaultdict(int)  # dir -> files directly in dir
    folder_children = defaultdict(set)  # parent_dir -> set(child_dir)
    seen_folders = set(["/"])

    def note_folder(dir_path: str):
        """Ensure folder + ancestors exist; update child links."""
        d = norm_dir(dir_path)
        prev = None
        for a in iter_ancestors(d):
            seen_folders.add(a)
            if prev is not None:
                # prev is child, a is parent
                folder_children[a].add(prev)
            prev = a

    current_dir_files = None
    files_by_name = None
    current_dir = None

    for root, dirs, files in os.walk(start_dir):
        if '@eaDir' in root:
            continue

        if current_dir != root:
            current_dir = root
            if skip_on is not None:
                current_dir_files = find_documents_in_folder(
                    volume_tag,
                    os.path.relpath(root, scan_dir)
                )
                files_by_name = index_by_name(current_dir_files)

        # Folder path stored in your doc.path is relative path, so compute it now
        rel_dir = os.path.relpath(root, scan_dir)
        rel_dir = "" if rel_dir == "." else rel_dir
        dir_for_index = norm_dir("/" + rel_dir)  # normalize to "/sub/dir" or "/"

        note_folder(dir_for_index)

        for file in files:
            if file.startswith('.'):
                continue

            filepath = os.path.join(root, file)

            (doc, logs) = create_document(filepath, file, scan_dir, volume_tag, skip_on, files_by_name)

            if doc == "SKIPPED":
                task_interface.add_file_status(task_id, filepath, "Skipped", logs)
                skip_count += 1
                continue

            if doc is not None:
                files = {
                    'thumbnail': ('thumb_001.jpg', doc['thumbnail'], 'image/jpeg'),
                }
                del doc['thumbnail']
                task_interface.update_file(doc, files)
                # documents.append(doc)
                task_interface.add_file_status(task_id, filepath, "Done", logs)
                done_count += 1

                # NEW: bump direct file count for this folder
                folder_direct_counts[dir_for_index] += 1

        if done_count >= TOTAL_TARGET:
            break

    # ----------------------------
    # NEW: Build + upload folder docs
    # ----------------------------
    folder_docs = []
    for d in seen_folders:
        pd = parent_dir(d)
        new_folder = {
            "id": folder_id(volume_tag, d),  # per-volume folder identity
            "volume": volume_tag,
            "dir": d,
            "parent_dir": f"{pd}" if pd != "/" else f"/",  # stable parent key
            "name": leaf_name(d),
            "depth": depth(d),
            "file_count": int(folder_direct_counts.get(d, 0)),
            "child_count": int(len(folder_children.get(d, set()))),
        }
        task_interface.update_folder(new_folder)


    print("Folders updated. Catalog ready.")


def scan_and_uploadx(pmts):
    scan_dir = pmts["scan_dir"]
    volume_tag = pmts["volume_tag"]
    skip_on = None
    start_dir = scan_dir

    kwargs = pmts.get("kwargs", None)
    if kwargs is not None:
        skip_on = kwargs.get("skip_on", None)
        if skip_on is not None: skip_on = skip_on.split(",")
        if "start_dir" in kwargs:
            start_dir = kwargs["start_dir"]
            start_dir = os.path.join(scan_dir, start_dir)

    taskInterface = pmts["taskInterface"]
    task_id = pmts["task_id"]

    documents = []

    done_count = 0
    skip_count = 0

    count = 0

    print(f"Scanning {scan_dir}...")

    current_dir_files = None
    files_by_name = None
    current_dir = None
    for root, dirs, files in os.walk(start_dir):
        # Skip Synology internal folders
        if '@eaDir' in root: continue
        print(f"root: {root}, dirs: {dirs}, files: {files}")
        if current_dir != root:
            current_dir = root
            if skip_on is not None:
                current_dir_files = find_documents_in_folder(volume_tag, os.path.relpath(root, scan_dir))
                files_by_name = index_by_name(current_dir_files)
        for file in files:
            if file.startswith('.'): continue

            filepath = os.path.join(root, file)

            # Base Record
            (doc, logs) = create_document(filepath, file, scan_dir, volume_tag, skip_on, files_by_name)
            if doc == "SKIPPED":
                taskInterface.add_file_status(task_id, filepath, "Skipped", logs)
                skip_count += 1
            elif doc is not None:
                documents.append(doc)
                taskInterface.add_file_status(task_id, filepath, "Done", logs)
                done_count += 1

            # Upload in batches of 100 to avoid memory issues or if the file is large

            if doc not in ["SKIPPED"] and (len(documents) >= BATCH_SIZE or doc["size"] > BIG_SIZE):
                task = client.index(INDEX_NAME).add_documents(documents)
                task_status = client.wait_for_task(task.task_uid, 30000, 500)
                if task_status.status == "failed":
                    print("Add Documents Failed.")
                    print("Errors: " + task_status.error["message"])

                # stats = client.index(INDEX_NAME).get_stats()
                print(f"Uploaded batch of {len(documents)} files...")
                documents = []

        if done_count >= TOTAL_TARGET:
            break

    # Upload remaining
    if documents:
        client.index(INDEX_NAME).add_documents(documents)
        print("Upload complete.")

    # Update Settings for better search
    # This makes these specific fields filterable in the UI

    print("Settings updated. Catalog ready.")


def find_documents_in_folder(volume, relative_path):
    try:
        search_results = client.index(INDEX_NAME).search(
            '',  # The search query
            {
                # Optional: Add filters for numerical data
                'filter': f"""volume = "{volume}" AND path = "{relative_path}" """,
                'attributesToRetrieve': ['name', 'size', 'created', 'modified']
            }
        )
        return search_results

    except Exception as e:
        print(f"Error during search: {e}")


def find_document(doc):
    try:
        search_results = client.index(INDEX_NAME).search(
            '',  # The search query
            {
                # Optional: Add filters for numerical data
                'filter': f"""size = {doc["size"]} AND volume = "{doc['volume']}" AND path = "{doc['path']}" """,
                # Optional: Limit the number of documents returned
                'limit': 25,
                # Optional: Define which fields to show
                'attributesToRetrieve': ['name', 'path', 'datetime_taken']
            }
        )
        return search_results

    except Exception as e:
        print(f"Error during search: {e}")
