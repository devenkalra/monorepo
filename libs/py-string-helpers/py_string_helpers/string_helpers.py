import pprint
import re
from typing import Any, Optional, Union


def format_number_with_precision(
        number: Union[int, float],
        precision: int = 2
) -> str:
    """
    Converts a number (int or float) to a string, rounded to a specified
    number of decimal places.

    Args:
        number (Union[int, float]): The numeric value to format.
        precision (int): The number of digits after the decimal point to round to.
                         Must be a non-negative integer. Defaults to 2.

    Returns:
        str: The number formatted as a string with the specified rounding.

    Examples:
        >>> format_number_with_precision(3.14159, 2)
        '3.14'
        >>> format_number_with_precision(42.678, 0)
        '43'
        >>> format_number_with_precision(100, 3)
        '100.000'
    """
    if not isinstance(precision, int) or precision < 0:
        raise ValueError("Precision must be a non-negative integer.")

    # Use an f-string with the format specification:
    # {number:.{precision}f}
    #   - :. is for floating point precision
    #   - {precision} dynamically inserts the desired number of digits
    #   - f specifies fixed-point notation
    format_string = f"{{:.{precision}f}}"

    return format_string.format(number)

def pretty_print_object(obj: Any) -> str:
    """
    Generates a pretty-printed, nicely formatted string representation of a
    Python object (e.g., dict, list, class instance).

    This function uses pprint.pformat to create a multi-line, readable string.

    Args:
        obj (Any): The Python object to pretty-print.

    Returns:
        str: The multi-line, formatted string representation of the object.
    """
    header = "--- Pretty Printed Object ---\n"
    # Use pformat to return the formatted string instead of printing
    formatted_string = pprint.pformat(obj, indent=4)
    footer = "\n-----------------------------"
    return header + formatted_string + footer


def to_snake_case(text: str) -> str:
    """
    Converts a string from CamelCase or PascalCase to snake_case,
    correctly handling acronyms (e.g., 'HTTPServerResponse' -> 'http_server_response').

    Args:
        text (str): The input string (e.g., 'APIResponseHandler').

    Returns:
        str: The snake_case version of the string (e.g., 'api_response_handler').
    """
    # 1. Insert '_' between a sequence of 2+ capital letters and a capital letter
    #    that is followed by a lowercase letter (e.g., HTTPServerResponse -> HTTP_ServerResponse)
    text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1_\2', text)

    # 2. Insert '_' between a lowercase letter/digit and an uppercase letter
    #    (This handles standard camelCase/PascalCase, e.g., get_User_ID)
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', text)

    # 3. Convert all to lowercase
    return text.lower()


def truncate_string(text: str, max_length: int, suffix: str = '...') -> str:
    """
    Truncates a string to a specified maximum length, adding a suffix
    if truncation occurs.

    Args:
        text (str): The input string.
        max_length (int): The maximum length of the output string (including suffix).
        suffix (str): The suffix to append if truncated (default: '...').

    Returns:
        str: The original or truncated string.
    """
    if len(text) <= max_length:
        return text

    # Calculate the actual truncation point
    effective_length = max_length - len(suffix)
    if effective_length <= 0:
        # If the max_length is too short for even the suffix, return a truncated suffix
        return text[:max_length]

    return text[:effective_length] + suffix


def is_palindrome(text: str) -> bool:
    """
    Checks if a string is a palindrome (reads the same forwards and backwards),
    ignoring case, spaces, and punctuation.

    Args:
        text (str): The input string.

    Returns:
        bool: True if the string is a palindrome, False otherwise.
    """
    # Remove all non-alphanumeric characters and convert to lowercase
    cleaned_text = re.sub(r'[^a-zA-Z0-9]', '', text).lower()
    return cleaned_text == cleaned_text[::-1]


# Example Usage
if __name__ == "__main__":
    # 1. Pretty Print Example
    user_data = {
        "user_id": 1001,
        "username": "jdoe",
        "email": "jdoe@example.com",
        "preferences": {
            "notifications": True,
            "theme": "dark",
            "history": [
                {"item": "laptop", "date": "2023-10-25"},
                {"item": "monitor", "date": "2023-10-26"}
            ]
        },
        "description": "This is a very long text string that would normally wrap awkwardly if not pretty-printed by the dedicated function."
    }

    # The function now RETURNS a string, which we then print
    print("--- Testing pretty_print_object ---")
    formatted_output = pretty_print_object(user_data)
    print(formatted_output)
    print("\n")

    # 2. Snake Case Example
    print("--- Testing to_snake_case ---")
    camel_input = "HTTPServerResponse"
    snake_output = to_snake_case(camel_input)
    print(f"'{camel_input}' -> '{snake_output}'")

    camel_input_2 = "MyCoolClassName"
    snake_output_2 = to_snake_case(camel_input_2)
    print(f"'{camel_input_2}' -> '{snake_output_2}'")
    print("\n")

    # 3. Truncate String Example
    print("--- Testing truncate_string ---")
    long_string = "The quick brown fox jumps over the lazy dog."
    truncated1 = truncate_string(long_string, 25)
    truncated2 = truncate_string(long_string, 50)
    print(f"Original: '{long_string}'")
    print(f"Truncated to 25: '{truncated1}'")
    print(f"Truncated to 50: '{truncated2}'")
    print("\n")

    # 4. Palindrome Example
    print("--- Testing is_palindrome ---")
    palindrome1 = "A man, a plan, a canal: Panama"
    palindrome2 = "Hello World"
    print(f"'{palindrome1}' is palindrome: {is_palindrome(palindrome1)}")
    print(f"'{palindrome2}' is palindrome: {is_palindrome(palindrome2)}")