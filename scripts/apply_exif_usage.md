# apply_exif.py – Usage Manual

## Overview
`apply_exif.py` is a small utility that applies EXIF/XMP tags to image files using **exiftool**.  The script has been extended to support:

1. Loading a set of tag name/value pairs from a YAML file (`--tags-yaml`).
2. Adding or overriding tags directly on the command line (`--set TAG=VALUE`).
3. Dry‑run mode (`--dry-run`) that prints the exact `exiftool` command without modifying files.
4. Selecting files via a glob pattern (`--pattern`).
5. Supplying an explicit list of image files (`--files`).
6. Backward‑compatible behaviour that still works with the original `PATTERN_TAG_MAP` configuration.

The script requires **Python 3**, the **PyYAML** package, and **exiftool** to be installed on the system.

---

## Installation
```bash
# Install exiftool (Debian/Ubuntu example)
sudo apt-get update && sudo apt-get install -y exiftool

# Install Python dependencies (run from the repository root)
python3 -m pip install --user pyyaml
```

Make the script executable (optional):
```bash
chmod +x scripts/apply_exif.py
```

---

## Command‑Line Interface
```bash
python3 scripts/apply_exif.py [OPTIONS]
```

### Options
| Option | Argument | Description |
|--------|----------|-------------|
| `--dry-run` | – | Print the `exiftool` command that would be executed, but do **not** modify any files. |
| `--tags-yaml` | `PATH` | Path to a YAML file containing a mapping of tag names to values. Example content:
|
| `--set` | `TAG=VALUE` (repeatable) | Directly set a tag from the command line. Can be used multiple times; later occurrences override earlier ones. |
| `--pattern` | `GLOB` | Glob pattern (supports `**` for recursive) that selects image files. |
| `--files` | `FILE [FILE ...]` | Explicit list of image files to process. Takes precedence over `--pattern`. |


```
Example Tag:
XMP-dc:Subject: "vacation"
XMP-iptc:Keywords: "beach, sunset"
```
### Behaviour Summary
- If `--files` is provided, those files are processed.
- Else if `--pattern` is supplied, files matching the glob are processed.
- If neither is given, the script falls back to the legacy `PATTERN_TAG_MAP` mapping defined inside the script.
- Tags are merged in the following order (later overrides earlier):
  1. Tags from the YAML file (if any).
  2. Tags from `--set` arguments.
  3. For legacy mode, the default tag (`XMP-dc:Subject`) from `PATTERN_TAG_MAP` is added **after** the merged tags, so CLI/YAML tags can override it.

---


## Examples
### 1. Apply tags from a YAML file (dry‑run)
```bash
python3 scripts/apply_exif.py \
    --tags-yaml tags.yml \
    --dry-run
```
`tags.yml` might contain:
```yaml
XMP-dc:Subject: "holiday"
XMP-iptc:Keywords: "beach, sunset"
```
The script will print the full `exiftool` command that would be run.

### 2. Override/add tags on the command line
```bash
python3 scripts/apply_exif.py \
    --tags-yaml tags.yml \
    --set XMP-dc:Subject=travel \
    --set XMP-iptc:Keywords="mountains, hiking"
```
The `--set` values take precedence over anything defined in `tags.yml`.

### 3. Process a specific glob pattern
```bash
python3 scripts/apply_exif.py \
    --pattern "photos/**/*.jpg" \
    --set XMP-dc:Subject=family
```
All `*.jpg` files under `photos/` (recursively) will receive the `family` tag.

### 4. Provide an explicit list of files
```bash
python3 scripts/apply_exif.py \
    --files img1.jpg img2.png img3.tif \
    --set XMP-dc:Subject=portfolio
```
Only the three listed files are modified.

### 5. Use the legacy behaviour (no new arguments)
If you run the script without any of the new options, it behaves exactly as the original version:
```bash
python3 scripts/apply_exif.py
```
It will iterate over the hard‑coded `PATTERN_TAG_MAP` entries and apply the default tag `XMP-dc:Subject` to each matching set of images.

---

## Notes & Tips
- **Multiple `--set` flags**: You can repeat `--set` to add several tags. Example: `--set Tag1=Value1 --set Tag2=Value2`.
- **Tag name quoting**: If a tag name contains spaces or special characters, wrap the entire `TAG=VALUE` argument in quotes, e.g. `--set "XMP-photoshop:City=New York"`.
- **Dry‑run safety**: Always start with `--dry-run` when testing a new tag set to verify the command before making changes.
- **Performance**: Supplying an explicit file list (`--files`) is the fastest path because the script skips the globbing and duplicate‑file‑deduplication steps.
- **Backwards compatibility**: Existing workflows that relied on the original `PATTERN_TAG_MAP` continue to work unchanged.

---

## License
This script is provided under the same license as the rest of the repository (see the repository root `LICENSE` file).
