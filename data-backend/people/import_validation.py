from functools import lru_cache
from pathlib import Path
import json

from jsonschema import Draft202012Validator, FormatChecker


@lru_cache(maxsize=1)
def _load_import_validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parent / "import.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_import_payload(payload):
    """Validate an import payload against people/import.schema.json.

    Returns a tuple: (is_valid, error_message).
    """
    validator = _load_import_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if not errors:
        return True, None

    first = errors[0]
    path = ".".join(str(part) for part in first.absolute_path) or "$"
    return False, f"{path}: {first.message}"
