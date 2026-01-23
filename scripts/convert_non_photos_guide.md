# convert_non_photos.sh User Guide

`convert_non_photos.sh` is a Bash script designed to batch convert video files (specifically `.avi` and `.vob`) to H.264 MP4 format using `ffmpeg`. After successful conversion, it moves the original source files (and associated `.xmp` sidecars) to a specified archive directory, preserving the directory structure.

## Features

- **Batch Conversion**: Recursively finds and converts `.avi` and `.vob` files.
- **Archive Originals**: Safely moves original files to an archive location after verification.
- **Safety Checks**: Verifies output validity with `ffprobe` before deleting/moving source files.
- **Customizable Quality**: Supports CRF, encoding presets, and audio bitrate adjustments.
- **Smart Deinterlacing**: Automatically detects interlaced content (using `idet`) and applies `bwdif` filter if confidence > 50%.
- **Filtering**: Supports glob patterns to process specific files.
- **Dry Run & Test Modes**: Preview actions or run quick tests without affecting source files.

## Prerequisites

Ensure the following tools are installed and available in your system's PATH:

- `bash` (version 4.0+)
- `ffmpeg`
- `ffprobe` (included with ffmpeg)

## Usage

```bash
./convert_non_photos.sh --src <source_directory> --archive <archive_directory> [options]
```

### Required Arguments

| Argument | Description |
| :--- | :--- |
| `--src <dir>` | The root directory to search for source video files. |
| `--archive <dir>` | The root directory where original files will be moved after conversion. |

### Optional Arguments

| Argument | Default | Description |
| :--- | :--- | :--- |
| `--crf <int>` | `16` | x264 Constant Rate Factor (lower is better quality). |
| `--preset <str>` | `slow` | x264 encoding preset (e.g., fast, medium, slow, veryslow). |
| `--audio-bitrate <rate>` | `320k` | Audio bitrate for AAC encoding. |
| `--pattern <glob>` | `*` | Glob pattern to filter filenames (e.g., `*Vacation*`). |
| `--limit <int>` | `0` (unlimited) | Stop after processing N files. |
| `--log <file>` | `/tmp/convert.log` | Path to the log file. |
| `--verbose` | Off | Print detailed output to stdout as well as the log file. |
| `--deinterlace` | Off | Force deinterlacing (`bwdif`) for ALL files (skips detection). |
| `--overwrite-mp4` | Off | Overwrite existing output `.mp4` files if they exist. |
| `--dry-run` | Off | Print what commands would be executed without running them. |
| `--test` | Off | Convert only the first 30 seconds, keep temp files, and **do not** move originals. |
| `-h`, `--help` | N/A | Show the help message. |

### Deinterlacing Options

- **Auto-Detection (Default)**: The script analyzes the first 300 frames of each video. If the "interlaced" confidence score is greater than 50%, the `bwdif` filter is applied.
- `--deinterlace`: Skips detection and forces `bwdif` deinterlacing for **all** processed files.


## Examples

### 1. Basic Usage
Convert all files in `videos/` and archive originals to `archive/`:
```bash
./convert_non_photos.sh --src ./videos --archive ./archive
```

### 2. Dry Run
See what files would be processed without actually converting anything:
```bash
./convert_non_photos.sh --src ./videos --archive ./archive --dry-run
```

### 3. Test Mode
Run a quick test on the first file (converts only 30s, does not move source):
```bash
./convert_non_photos.sh --src ./videos --archive ./archive --test --limit 1
```

### 4. High Quality Archival
Use a lower CRF and slower preset for better quality/compression:
```bash
./convert_non_photos.sh --src ./old_dvds --archive ./archive --crf 14 --preset veryslow
```

### 5. Filter by Name
Process only files containing "Holiday":
```bash
./convert_non_photos.sh --src ./videos --archive ./archive --pattern "*Holiday*"
```

## Workflow Details

1. **Discovery**: The script scans the `--src` directory for `.avi` and `.vob` files matching the `--pattern`.
2. **Conversion**: 
   - Converts video to H.264 (yuv420p) and audio to AAC.
   - Writes to a temporary file (`.tmp.mp4`) first.
3. **Verification**: Checks if the resulting file has a valid video stream using `ffprobe`.
4. **Completion**:
   - If verification passes, renames the temp file to the final `.mp4` name.
   - Moves the **original** source file to the `--archive` directory (mirroring the subdirectory structure).
   - Moves related `.xmp` sidecar files if they exist.
5. **Logging**: All actions are logged to the specified log file.

> **Note**: In `--test` mode, the source files are **never** moved, and the temporary `.tmp.mp4` files are left in place for inspection.
