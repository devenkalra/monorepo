import pytest
# Assuming string_helpers.py is in the same directory
import py_string_helpers.string_helpers as string_helpers


# --- Fixture for Complex Data ---
# A fixture allows reuse of complex test data across multiple tests
@pytest.fixture
def complex_data():
    """Provides a complex nested dictionary for testing pretty_print_object."""
    return {
        "user_id": 1001,
        "username": "jdoe",
        "preferences": {
            "notifications": True,
            "history": [
                {"item": "laptop", "date": "2023-10-25"},
                {"item": "monitor", "date": "2023-10-26"}
            ]
        },
        "tags": ("python", "helper", "test")
    }


# --- Test Group 1: pretty_print_object ---

def test_pretty_print_object_structure(complex_data):
    """Tests that the output string contains the headers, footers, and is multi-line."""
    formatted_str = string_helpers.pretty_print_object(complex_data)

    assert formatted_str.startswith("--- Pretty Printed Object ---")
    assert formatted_str.endswith("\n-----------------------------")

    # Check for multi-line formatting (a key feature of pretty-print)
    assert formatted_str.count('\n') > 5


def test_pretty_print_object_content(complex_data):
    """Tests that key content from the complex data is present in the output."""
    formatted_str = string_helpers.pretty_print_object(complex_data)

    # Check for keys and nested values
    assert "'user_id': 1001" in formatted_str
    assert "'notifications': True" in formatted_str
    assert "'item': 'laptop'" in formatted_str


def test_pretty_print_object_simple():
    """Tests that a simple object (string) is handled correctly."""
    formatted_str = string_helpers.pretty_print_object("simple string")
    assert "'simple string'" in formatted_str


# --- Test Group 2: to_snake_case ---

@pytest.mark.parametrize("input_str, expected", [
    ("MyClassName", "my_class_name"),
    ("getUserId", "get_user_id"),
    ("already_snake_case", "already_snake_case"),
    # Acronym handling
    ("HTTPServerResponse", "http_server_response"),
    ("APIResponseHandler", "api_response_handler"),
    ("A", "a"),
    ("", ""),  # Empty string test
    ("MyCoolID", "my_cool_id"),  # Handles acronym at the end
    ("HTTPCode404", "http_code404"),  # Handles digits
])
def test_to_snake_case(input_str, expected):
    """Tests various standard and edge cases for snake casing."""
    assert string_helpers.to_snake_case(input_str) == expected


# --- Test Group 3: truncate_string ---

@pytest.mark.parametrize("text, max_length, suffix, expected", [
    # No truncation needed
    ("Hello", 10, "...", "Hello"),
    # Exact length
    ("12345", 5, "...", "12345"),
    # FIX 1: Text length (20) < Max length (22), so no truncation should occur.
    ("The quick brown fox.", 22, "...", "The quick brown fox."),
    # FIX 2: Max length (15) - Suffix length (6) = 9 prefix chars.
    ("Long sentence to cut.", 15, "...END", "Long sent...END"),
    # Truncation when max_length is too small
    ("ABCDEFGHIJ", 3, "...", "ABC"),
    # Truncation when max_length just fits the suffix
    ("ABCDEFGHIJ", 4, "T", "ABCT"),
])
def test_truncate_string(text, max_length, suffix, expected):
    """Tests string truncation under various length and suffix conditions."""
    assert string_helpers.truncate_string(text, max_length, suffix) == expected


# --- Test Group 4: is_palindrome ---

@pytest.mark.parametrize("text, expected", [
    ("racecar", True),
    ("A man, a plan, a canal: Panama", True),  # Complex with spaces and punctuation
    ("Hello World", False),
    ("12321", True),  # Numbers
    ("", True),  # Empty string
    ("X", True),  # Single character
    ("Madam", True),  # Case insensitive
    ("No lemon, no melon", True),
    ("Was it a car or a cat I saw", True),
])
def test_is_palindrome(text, expected):
    """Tests various strings for palindrome status, ignoring case and punctuation."""
    assert string_helpers.is_palindrome(text) == expected


@pytest.mark.parametrize("input, precision, output", [
    (123.45678, 2, "123.46"),
    (42.99, 0, "43"),
    (500, 4, "500.0000"),
    (-12.345, 1, "-12.3"),
    (2.675, 2, "2.67")
])
def test_format_number_with_precision(input, precision,output):
    assert string_helpers.format_number_with_precision(input, precision) == output
