# libs/py-file-helpers/py_file_helpers/exif_helpers.py
import sys
from PIL import Image, UnidentifiedImageError
from exiftool import ExifToolHelper
import os
from typing import Dict, Any, Optional
current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
import base64
import subprocess
import py_string_helpers.string_helpers as string_helpers
from .file_types import is_file_an_image
from io import BytesIO
def create_base64_thumbnail(filepath, max_size=(128, 128), output_format='JPEG', quality=85):
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
        return None

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
        print(f"Warning: File at {filepath} is not a recognizable image.")
        return None
    except Exception as e:
        # Handle other errors (e.g., file corruption, permissions)
        print(f"Error processing file {filepath}: {e}")
        return None



def _encode_to_data_uri(image_bytes, output_format='JPEG'):
    """Encodes binary data to a Base64 Data URI string."""
    base64_encoded = base64.b64encode(image_bytes)
    mime_type = f"image/{output_format.lower()}"
    base64_string = base64_encoded.decode('utf-8')
    return f"data:{mime_type};base64,{base64_string}"
def get_thumbnail(filepath, generate=True):
    """
    Extracts the embedded thumbnail binary using the ExifTool command line.
    If not found and generate=True, thumbnail is created from the image
    """
    if not os.path.exists(filepath):
        return None

    try:
        # Command: exiftool -b -ThumbnailImage - (filename)
        # -b (binary output), -ThumbnailImage (specifies the tag to extract)
        command = ['exiftool', '-b', '-ThumbnailImage', filepath]

        # Execute the command and capture the output (stdout)
        result = subprocess.run(
            command,
            capture_output=True,
            check=True  # Raise an exception if the command returns a non-zero exit code
        )

        # The result.stdout is the raw binary data of the JPEG thumbnail
        if result.stdout:
            print("  [SUCCESS] Extracted embedded thumbnail via subprocess.")
            return _encode_to_data_uri(result.stdout, 'JPEG')

    except subprocess.CalledProcessError as e:
        # ExifTool often returns an error code if the tag is missing/empty
        if b'no thumbnail image' in e.stderr.lower():
            print("  [INFO] File contains no embedded ThumbnailImage tag.")
            return None
        else:
            print(f"  [ERROR] ExifTool failed (CalledProcessError): {e.stderr.decode()}")
    except FileNotFoundError:
        print("  [CRITICAL] 'exiftool' command not found. Ensure it is installed and in PATH.")
    except Exception as e:
        print(f"  [ERROR] Unexpected error during subprocess call: {e}")

    return None

def clean_exif_data(raw_metadata):
    # ExifTool returns a list containing one dictionary per file

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

# mode = "cleaned"|"raw"|
def get_tags(filepath: str, mode="cleaned", tags: list[str]=None) -> Optional[Dict[str, Any]]:
    """
    Extracts all EXIF metadata from a file using ExifToolHelper.

    Args:
        filepath: The path to the image file.

    Returns:
        A dictionary containing EXIF metadata, or None if extraction fails.
    """
    def round_number_as_str(num, precision):
        if isinstance(num, str):
            num = float(num)
        return string_helpers.format_number_with_precision(num, precision)

    def round_number(num, precision):
        if isinstance(num, str):
            num = float(num)
        s= string_helpers.format_number_with_precision(num, precision)
        if precision == 0:
            return int(s)
        else:
            return float(s)

    key_map = [
        (["Aperture", "FNumber"], "Aperture", lambda x: round_number(x, 2)),
        (["ISO"], "ISO", lambda x: round_number(x, 0)),
        (["ExifImageHeight", "ImageHeight"], "Height", lambda x: round_number(x, 0)),
        (["ExifImageWidth", "ImageWidth"], "Width", lambda x: round_number(x, 0)),
        (["ExposureTime"], "ExposureTime", lambda x: round_number(x, 8)),
        (["FocalLength"], "FocalLength", lambda x: round_number(x, 0)),
        (["FocalLengthIn35mmFormat", "FocalLength35efl"], "FocalLengthIn35mmFormat", lambda x: round_number(x, 0)),
    ]
    def map_multi_key_values(exif):
        for (keys, mapped_key, converter) in key_map:
            for key in keys:
                if key in exif:
                    exif[mapped_key] = converter(exif[key])
                    break
        return exif

    if not os.path.exists(filepath):
        print(f"Error: File not found at path: {filepath}")
        return None

    def filter_tags(raw_tags):
        if tags is None:
            return raw_tags
        filtered_dict = {
            key: value
            for key, value in raw_tags.items()
            if key in tags
        }
        return filtered_dict

    try:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found at path: {filepath}")
        if not is_file_an_image(filepath):
            raise UnidentifiedImageError(f"File at path: {filepath}")
        with ExifToolHelper(executable="/usr/bin/exiftool") as et:
            metadata_list = et.get_tags(filepath, tags=tags)
            if metadata_list:
                # Return the first (and usually only) dictionary of metadata
                if mode == "cleaned":
                    cleaned_tags = map_multi_key_values(clean_exif_data(metadata_list[0]))
                else:
                    cleaned_tags = map_multi_key_values(metadata_list[0])
                return filter_tags(cleaned_tags)
            else:
                print(f"Warning: No metadata found for {filepath}")
                return None

    except UnidentifiedImageError:
        print(f"Error: File is not a recognized image format: {filepath}")
        return None

    except FileNotFoundError as e:
        # This catches if ExifTool (the executable) is not installed or found
        print(f"Error: The exiftool executable was not found. Please install it on your system.")
        print(f"Details: {e}")
        return None

    except Exception as e:
        print(f"An unexpected error occurred during EXIF extraction for {filepath}: {e}")
        return None


