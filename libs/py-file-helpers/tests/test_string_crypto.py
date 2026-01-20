# -*- coding: utf-8 -*-
import pytest
from py_file_helpers.crypto import Crypto  # <-- IMPORTANT: Change 'your_module'


# Fixture not strictly necessary here, but often useful for setup/teardown in larger test files.

def test_known_value_hash():
    """
    Test 1: Verify the hash of a known string matches the expected SHA256 digest.
    (This expected value is calculated independently for verification).
    """
    test_string = "The quick brown fox jumps over the lazy dog"
    # Known SHA256 hash for the test_string (encoded as UTF-8)
    expected_hash = "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592"

    calculated_hash = Crypto.hash_string(test_string)
    print(calculated_hash)
    print(expected_hash)
    assert calculated_hash == expected_hash, "Hash of known string did not match expected value."


def test_empty_string_hash():
    """
    Test 2: Verify the hash of an empty string.
    """
    test_string = ""
    # Known SHA256 hash for an empty string
    expected_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    calculated_hash = Crypto.hash_string(test_string)

    assert calculated_hash == expected_hash, "Hash of empty string did not match expected value."


def test_case_sensitivity():
    """
    Test 3: Ensure hashing is case-sensitive ('a' != 'A').
    """
    string_lower = "testing"
    string_upper = "TESTING"

    hash_lower = Crypto.hash_string(string_lower)
    hash_upper = Crypto.hash_string(string_upper)

    # Hashes for different inputs should never be the same
    assert hash_lower != hash_upper, "Hashes for case-sensitive strings were identical."


def test_special_characters_hash():
    """
    Test 4: Check hashing with special characters and non-ASCII characters.
    """
    # The string literal containing non-ASCII characters: æ, ø, å
    test_string = "Français æ, ø, å"

    # CORRECT Known SHA256 hash for this specific string in UTF-8
    expected_hash = "3528621b32128add61e3cfb4c9aa3605dc10b9860a93eccf021669e5ff35b3d5"

    # Using the class name HashingUtils as defined in hasher_utils.py
    calculated_hash = Crypto.hash_string(test_string)

    assert calculated_hash == expected_hash, "Hash of string with special characters failed."

@pytest.mark.parametrize("invalid_input", [
    12345,
    None,
    b"bytes_input",
    [1, 2, 3]
])
def test_invalid_input_type(invalid_input):
    """
    Test 5: Ensure a TypeError is raised for non-string inputs using parametrization.
    """
    # We use pytest.raises to assert that a specific exception is raised
    with pytest.raises(TypeError) as excinfo:
        Crypto.hash_string(invalid_input)

    # Optionally, check the error message
    assert "Input must be a string." in str(excinfo.value)