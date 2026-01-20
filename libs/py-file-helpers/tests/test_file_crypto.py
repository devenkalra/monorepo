import hashlib
import pytest
from py_file_helpers.crypto import Crypto  # <-- IMPORTANT: Change 'your_module'
from unittest import mock

# --- Fixture to create temporary files ---

@pytest.fixture
def temp_file_manager(tmp_path):
    """
    Creates temporary files with known content and returns the file paths
    and their expected SHA256 hash values.
    """
    files = {}

    # File 1: Short content, known hash
    content_short = b"hello world"
    # Expected hash for "hello world"
    hash_short = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    path_short = tmp_path / "short_file.txt"
    path_short.write_bytes(content_short)
    files['short'] = (path_short, hash_short)

    # File 2: Longer content, spanning multiple blocks (65536 * 1.5 bytes)
    blocksize = 65536
    content_long = b"A" * blocksize + b"B" * (blocksize // 2)  # 1.5 blocks
    # Expected hash for content_long
    hash_long = hashlib.sha256(content_long).hexdigest()
    path_long = tmp_path / "long_file.bin"
    path_long.write_bytes(content_long)
    files['long'] = (path_long, hash_long)

    # File 3: Empty file
    hash_empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # SHA256 of empty string
    path_empty = tmp_path / "empty_file.txt"
    path_empty.write_bytes(b"")
    files['empty'] = (path_empty, hash_empty)

    return files


# --- Tests ---

def test_hash_short_content(temp_file_manager):
    """Tests hash calculation for content shorter than the blocksize."""
    path, expected_hash = temp_file_manager['short']
    actual_hash = Crypto.hash_file(path, blocksize=1024)
    assert actual_hash == expected_hash


def test_hash_long_content(temp_file_manager):
    """Tests hash calculation for content spanning multiple blocks."""
    path, expected_hash = temp_file_manager['long']
    # Use a small blocksize to force multiple reads, ensuring the loop works
    actual_hash = Crypto.hash_file(path, blocksize=1024)
    assert actual_hash == expected_hash


@mock.patch('os.path.exists', return_value=True)
@mock.patch('builtins.open')
def test_hash_file_io_error(mock_open, mock_exists, capsys):
    """
    Test 6: Verify that hash_file returns None and prints an error message
    when an IOError occurs during file reading.
    """
    # ------------------ FIX APPLIED ------------------
    # Use MagicMock() instead of Mock() to correctly handle the 'with' statement (__enter__/__exit__).
    mock_file = mock.MagicMock()
    # The return value of __enter__ is what gets assigned to the variable 'afile'
    mock_file.__enter__.return_value = mock_file
    # Configure the mock to raise the IOError when the file's read() method is called
    mock_file.read.side_effect = IOError("Simulated Permission Denied")
    mock_open.return_value = mock_file
    # -------------------------------------------------

    test_filepath = "/tmp/restricted/file.dat"

    # 1. Call the function
    result = Crypto.hash_file(test_filepath)

    # 2. Assert the function returns None
    assert result is None, "hash_file should return None on IOError."

    # 3. Assert that the error message was printed to stdout
    captured = capsys.readouterr()
    assert f"Error reading file {test_filepath}: Simulated Permission Denied" in captured.out

def test_hash_empty_file(temp_file_manager):
    """Tests hash calculation for an empty file."""
    path, expected_hash = temp_file_manager['empty']
    actual_hash = Crypto.hash_file(path)
    assert actual_hash == expected_hash


def test_file_not_found():
    """Tests that the function raises FileNotFoundError for non-existent paths."""
    non_existent_path = "non_existent_file.xyz"
    with pytest.raises(FileNotFoundError):
        Crypto.hash_file(non_existent_path)


def test_different_block_size(temp_file_manager):
    """Tests the hash is consistent regardless of the blocksize used in the function."""
    path_short, expected_hash = temp_file_manager['short']

    # Run with a large blocksize (larger than file size)
    hash_large_block = Crypto.hash_file(path_short, blocksize=50000)

    # Run with a small blocksize (forcing multiple reads)
    hash_small_block = Crypto.hash_file(path_short, blocksize=1)

    assert hash_large_block == expected_hash
    assert hash_small_block == expected_hash
    assert hash_large_block == hash_small_block