import argparse
import os

# --- Custom Type Converter ---
def comma_separated_list(arg):
    """Splits a comma-separated string into a list of strings."""
    if not arg:
        return []
    # Use list comprehension to split and strip whitespace from each item
    return [item.strip() for item in arg.split(',') if item.strip()]


# --- Main Parsing Function ---
def parse_cli_arguments():
    """Configures and parses the command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scan directories for files and apply tagging criteria."
    )

    # 1. scan_dirs (required, comma-separated directories)
    parser.add_argument(
        '--scan-dirs',
        type=comma_separated_list,
        required=True,
        help="Comma-separated list of directories to scan (e.g., '/home/user/docs,/mnt/photos')."
    )

    # 2. volume_tags (required, comma-separated tags, must match length of scan_dirs)
    parser.add_argument(
        '--volume-tags',
        type=comma_separated_list,
        required=True,
        help="Comma-separated list of tags corresponding to each scan-dir (e.g., 'DOCS,PHOTOS')."
    )

    # 3. exclude (optional, single string for exclude criteria)
    parser.add_argument(
        '--exclude',
        type=comma_separated_list,
        default=None,
        help="File/directory exclusion criteria (e.g., glob pattern or regex string)."
    )

    # 4. include (optional, single string for include criteria)
    parser.add_argument(
        '--include',
        type=comma_separated_list,
        default=None,
        help="File/directory inclusion criteria (e.g., glob pattern or regex string)."
    )

    args = parser.parse_args()

    # --- Custom Validation for Scan Dirs and Tags ---
    if len(args.scan_dirs) != len(args.volume_tags):
        parser.error(
            f"The number of --scan-dirs ({len(args.scan_dirs)}) must match "
            f"the number of --volume-tags ({len(args.volume_tags)})."
        )

    return args