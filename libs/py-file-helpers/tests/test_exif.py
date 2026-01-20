import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import sys
# Assuming the file is now named 'exif.py' inside the package
from py_file_helpers.exif import get_tags, get_thumbnail

from PIL import UnidentifiedImageError
from exiftool import ExifToolHelper  # Needed for mocking FileNotFoundError
import sys
import os

# --- Path Injection for Cross-Package Imports ---

# 1. Get the current test directory: .../libs/py-file-helpers/tests/
current_dir = os.path.dirname(os.path.abspath(__file__))
libs_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
target_package_dir = os.path.join(libs_root_path, 'py-data-helpers')
sys.path.insert(0, target_package_dir)

# --- End Path Injection ---
target_package_dir = os.path.join(libs_root_path, 'py-string-helpers')
sys.path.insert(0, target_package_dir)
# Now the desired import should work:
from py_data_helpers.data_utils import DataUtils
import py_string_helpers.string_helpers as string_helpers

# ... rest of your test code ...
# Initialize the utility class once for all tests in this file
util = DataUtils()
# --- Mocking Constants ---
MOCK_EXIF_DATA = [
    {
        "SourceFile": "mock_test_image.jpg",
        "Make": "FakeCam",
        "Model": "FakeModel-X",
        "DateTimeOriginal": "2025:12:04 10:00:00",
        'ExifImageWidth': 100,
    }
]
dir_path = os.path.dirname(os.path.realpath(__file__))
a_test_file = f"{dir_path}/exif_data/jpg/Canon_PowerShot_S40.jpg"

test_files = [
    (
        f"{dir_path}/exif_data/jpg/Canon_PowerShot_S40.jpg",
        {"Make": "Canon", "Model": 'Canon PowerShot S40',
         'Width': 2272, 'Height': 1704, 'DateTimeOriginal': '2003:12:14 12:01:44',
         'ExposureTime': 0.00191127,
         'FocalLength': 21, 'FocalLengthIn35mmFormat': 104, 'Aperture': 4.9, 'ISO': 100}
    ),
    (
        f"{dir_path}/exif_data/jpg/Canon_40D.jpg",
        {"Make": "Canon", "Model": "Canon EOS 40D",
         'Width': 100, 'Height': 68, 'DateTimeOriginal': '2008:05:30 15:56:01', 'ExposureTime': 0.00625,
         'FocalLength': 135, 'FocalLengthIn35mmFormat': 219, 'Aperture': 7.10, 'ISO': 100}
    ),
    (
        f"{dir_path}/exif_data/raw/nikon_z_9_high_efficiency_compressed_dx_cropped_max_overexposed.dng",
        {
            'Aperture': 1.2, 'DateTimeOriginal': '2025:08:10 19:02:53',
            'ExposureTime': 30.0,
            'FocalLength': 85, 'FocalLengthIn35mmFormat': 127, 'Height': 3592, 'ISO': 102400, "Make": "NIKON CORPORATION",
            "Model": "NIKON Z 9",
            'Width': 5392, }
    ),
(
        f"{dir_path}/exif_data/heic/spring_1440x960.heic",
        {
            'DateTimeOriginal': '2020:12:03 15:04:31',
             'Height': 960,
            'Width': 1440, }
    ),
(
        f"{dir_path}/exif_data/heic/mobile/iphone_13_pro_max.heic",
        {
            'Aperture': 1.5, 'DateTimeOriginal':  '2022:02:16 12:55:41',
            'ExposureTime': 0.01666667,
            'FocalLength': 6, 'FocalLengthIn35mmFormat': 26, 'Height': 3024,
            'ISO': 250, "Make": "Apple",
            "Model": 'iPhone 13 Pro Max',
            'Width': 4032, }
    ),

]


# ----------------------------------------------------------------------
# Tests for get_tags (Achieves 100% coverage for this function)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("file, expected", test_files)
def test_test_files(file, expected):
    result = get_tags(file)
    try:
        assert DataUtils().is_subset(expected, result)
    except AssertionError:
        print("\n+++++ Result")
        print(string_helpers.pretty_print_object(result))

        print("\n+++++ Expected")
        print(string_helpers.pretty_print_object(expected))
        assert DataUtils().is_subset(expected, result)


def test_get_tags_file_not_found_os_check():
    """Covers: if not os.path.exists(filepath): return None"""
    result = get_tags("/path/to/nonexistent/file.jpg")
    assert result is None

thumb_test_files = [
    (
        f"{dir_path}/exif_data/jpg/Sony_DSLR-A200.jpg",
        "data:image/jpeg;base64,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"
    ),
]


@pytest.mark.parametrize("file, thumb", thumb_test_files)
def test_extract_thumbnail(file, thumb):
    extracted_thumb = get_thumbnail(file)
    assert extracted_thumb == thumb

@patch('py_file_helpers.exif.ExifToolHelper')
@patch('py_file_helpers.exif.Image.open')
def xtest_get_tags_successful_extraction(mock_image_open, mock_et_helper, mock_image_path: Path):
    """Covers: Success path (Image.open, verify, ExifToolHelper usage, return metadata_list[0])"""
    # 1. Mock Image.open context manager
    mock_img_verify = mock_image_open.return_value.__enter__.return_value
    mock_img_verify.verify.return_value = None

    # 2. Mock ExifToolHelper to return fake data
    mock_et_instance = mock_et_helper.return_value.__enter__.return_value
    mock_et_instance.get_tags.return_value = MOCK_EXIF_DATA

    result = get_tags(str(mock_image_path))

    assert result == MOCK_EXIF_DATA[0]
    mock_et_instance.get_tags.assert_called_once()
    mock_img_verify.verify.assert_called_once()


@patch('py_file_helpers.exif.ExifToolHelper')
@patch('py_file_helpers.exif.Image.open')
def test_get_tags_no_metadata_found(mock_image_open, mock_et_helper, mock_image_path: Path, capsys):
    """Covers: if metadata_list: ... else: print(...); return None"""
    mock_image_open.return_value.__enter__.return_value.verify.return_value = None

    # Mock ExifToolHelper to return an empty list
    mock_et_instance = mock_et_helper.return_value.__enter__.return_value
    mock_et_instance.get_tags.return_value = []

    result = get_tags(str(mock_image_path))

    assert result is None
    captured = capsys.readouterr()
    assert "Warning: No metadata found" in captured.out


@patch('py_file_helpers.exif.Image.open')
def test_get_tags_unidentified_image_error(mock_image_open, corrupted_file_path: Path, capsys):
    """Covers: except UnidentifiedImageError: print(...); return None"""
    # Force Image.open to fail with the specific PIL error
    mock_image_open.side_effect = UnidentifiedImageError

    result = get_tags(str(corrupted_file_path))

    assert result is None
    captured = capsys.readouterr()
    assert "Error: File is not a recognized image format" in captured.out


@patch('py_file_helpers.exif.Image.open')
def test_get_tags_exiftool_executable_not_found(mock_image_open, mock_image_path: Path, capsys):
    """Covers: except FileNotFoundError as e: print(...); return None (when ExifTool fails)"""
    mock_image_open.return_value.__enter__.return_value.verify.return_value = None

    # Patch the ExifToolHelper to raise the expected FileNotFoundError
    with patch('py_file_helpers.exif.ExifToolHelper', side_effect=FileNotFoundError("ExifTool binary missing")):
        result = get_tags(str(mock_image_path))

    assert result is None
    captured = capsys.readouterr()
    assert "Error: The exiftool executable was not found" in captured.out


@patch('py_file_helpers.exif.Image.open')
@patch('py_file_helpers.exif.ExifToolHelper')
def xtest_get_tags_unexpected_error(mock_et_helper, mock_image_open, mock_image_path: Path, capsys):
    """Covers: except Exception as e: print(...); return None"""
    # Mock an unexpected error during the process
    mock_image_open.side_effect = ValueError("Some unexpected internal error")

    result = get_tags(str(mock_image_path))

    assert result == {}
    captured = capsys.readouterr()
    assert "An unexpected error occurred during EXIF extraction" in captured.out


# ----------------------------------------------------------------------
# Tests for get_specific_tags (Achieves 100% coverage for this function)
# ----------------------------------------------------------------------

def test_get_specific_tags_file_not_found_os_check():
    """Covers: if not os.path.exists(filepath): return None"""
    result = get_tags("/path/to/nonexistent/file.jpg", "cleaned", ["Make"])
    assert result is None



@patch('py_file_helpers.exif.ExifToolHelper')
def test_get_specific_tags_successful_extraction(mock_et_helper, mock_image_path: Path):
    """Covers: Success path (ExifToolHelper usage, return metadata_list[0])"""
    requested_tags = ["Make", "Model"]

    # Mock ExifToolHelper to return data containing only the requested tags
    mock_return = [{"Make": "FakeCam", "Model": "FakeModel-X"}]
    mock_et_instance = mock_et_helper.return_value.__enter__.return_value
    mock_et_instance.get_tags.return_value = mock_return

    result = get_tags(str(mock_image_path), mode="cleaned", tags=requested_tags)

    assert result == mock_return[0]

    # Assert ExifTool was called with the correct tags list
    mock_et_instance.get_tags.assert_called_once_with(
        str(mock_image_path),
        tags=requested_tags
    )


@patch('py_file_helpers.exif.ExifToolHelper')
def test_get_specific_tags_no_tags_found(mock_et_helper, mock_image_path: Path):
    """Covers: if metadata_list: ... else: return None"""
    # Mock ExifToolHelper to return an empty list
    mock_et_instance = mock_et_helper.return_value.__enter__.return_value
    mock_et_instance.get_tags.return_value = []

    result = get_tags(str(mock_image_path), "cleaned", ["NonExistentTag"])

    assert result is None


@patch('py_file_helpers.exif.ExifToolHelper')
def test_get_specific_tags_unexpected_error(mock_et_helper, mock_image_path: Path, capsys):
    """Covers: except Exception as e: print(...); return None"""
    # Mock an unexpected error during the process
    mock_et_instance = mock_et_helper.return_value.__enter__.return_value
    mock_et_instance.get_tags.side_effect = ValueError("Network connection dropped")

    result = get_tags(str(mock_image_path), "cleaned", ["Make"])

    assert result is None
    captured = capsys.readouterr()
    print("++++\n" + captured.out)

    assert "Network connection dropped" in captured.out
