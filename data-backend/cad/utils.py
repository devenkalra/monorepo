"""CAD utilities - parameter extraction from scripts."""

import ast
import re

PARAM_PATTERN = re.compile(
    r"^PARAMETERS\s*=\s*(\{[\s\S]*?\})\s*$",
    re.MULTILINE,
)


def extract_parameters(script: str) -> dict:
    """Extract PARAMETERS dict from model script."""
    match = PARAM_PATTERN.search(script)
    if not match:
        return {}
    try:
        result = ast.literal_eval(match.group(1))
        return result if isinstance(result, dict) else {}
    except (ValueError, SyntaxError):
        return {}
