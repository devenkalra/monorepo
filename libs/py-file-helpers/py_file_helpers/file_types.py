import magic
import os
RAW_EXTS=[
    'rw2', 'c42', 'nef'
]
def is_file_an_image(filepath):
    mime_type = magic.from_file(filepath, mime=True)
    if mime_type.startswith('image/'): return True
    extension = os.path.splitext(filepath)[1].lower().replace('.', '')
    if extension in RAW_EXTS: return True
    return False
import fnmatch
def file_matches_patterns(filepath, patterns):
    """
    Checks if the base filename or the full path matches any of the given patterns.

    Args:
        filepath (str): The full path to the file.
        patterns (list or str): A single pattern or list of patterns to check against.

    Returns:
        bool: True if the file matches any pattern, False otherwise.
    """
    if isinstance(patterns, str):
        patterns = [patterns]

    filename = os.path.basename(filepath)

    for pattern in patterns:
        # 1. Check if the full path matches (useful for excluding directories)
        if fnmatch.fnmatch(filepath, pattern):
            return True

        # 2. Check if the filename matches (most common use case like *.RW2)
        if fnmatch.fnmatch(filename, pattern):
            return True

    return False
