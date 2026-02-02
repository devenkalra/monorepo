# Photo Management Tools

A comprehensive suite of Python scripts for managing, indexing, and organizing photo and media collections.

## Features

- **Media Indexing**: Scan and index photos/videos with metadata extraction
- **EXIF Management**: Read, write, and update EXIF/XMP metadata
- **Location Tagging**: Geocode locations and add GPS coordinates
- **Duplicate Detection**: Find and manage duplicate files
- **File Organization**: Move and organize media files with database tracking
- **GUI Interface**: User-friendly graphical interface for all tools
- **Database Integration**: SQLite database for fast searching and tracking

## Requirements

### System Requirements
- Python 3.8 or higher
- 100MB disk space for installation
- Additional space for media database

### External Dependencies
- **exiftool** (required for EXIF operations)
  - Ubuntu/Debian: `sudo apt-get install libimage-exiftool-perl`
  - macOS: `brew install exiftool`
  - Windows: Download from https://exiftool.org/

### Python Dependencies
All Python dependencies are automatically installed:
- Pillow (image processing)
- geopy (geocoding)
- requests (HTTP requests)
- PyYAML (configuration files)

## Installation

### Quick Install

```bash
# Extract the package
tar -xzf photo-management-tools-1.0.0.tar.gz
cd photo-management-tools-1.0.0

# Run the installation script
./install.sh
```

### Manual Install

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install package
pip install -e .
```

## Usage

### Activate Environment

Before using any commands, activate the virtual environment:

```bash
source venv/bin/activate
```

### Command-Line Tools

#### 1. Index Media Files

```bash
photo-index --source /path/to/photos --db media.db --volume "MyPhotos"
```

Options:
- `--source`: Directory to scan
- `--db`: Database path
- `--volume`: Volume name for organization
- `--verbose`: Verbosity level (0-3)
- `--dry-run`: Preview without changes

#### 2. Apply EXIF Metadata

```bash
photo-apply-exif --files photo1.jpg photo2.jpg \
  --place "New York, NY" \
  --keywords "vacation,2024" \
  --db media.db
```

Options:
- `--files`: Files to process (can be repeated)
- `--place`: Location name (geocoded automatically)
- `--latitude`, `--longitude`: Manual coordinates
- `--keywords`: Comma-separated keywords
- `--city`, `--state`, `--country`: Location details
- `--dry-run`: Preview without changes

#### 3. Move Media Files

```bash
photo-move --files *.jpg \
  --destination /archive/2024 \
  --volume "Archive" \
  --db media.db
```

Options:
- `--files`: Files to move
- `--destination`: Target directory
- `--volume`: Volume name
- `--db`: Database path
- `--dry-run`: Preview without changes

#### 4. Locate Files in Database

```bash
photo-locate --files photo.jpg --db media.db --metadata
```

Options:
- `--files`: Files to locate
- `--db`: Database path
- `--metadata`: Show detailed metadata
- `--json`: Output as JSON

#### 5. Show EXIF Data

```bash
photo-show-exif --files photo.jpg --mode common
```

Options:
- `--files`: Files to display
- `--mode`: Display mode (common, all, gps, grouped)
- `--thumbnail`: Extract and show thumbnail

#### 6. Find Location Coordinates

```bash
photo-find-location --place "Paris, France"
```

Options:
- `--place`: Location to geocode
- `--json`: Output as JSON

#### 7. Manage Duplicates

```bash
photo-manage-dupes --source /path/to/photos \
  --db media.db \
  --dry-run
```

#### 8. Remove Duplicates

```bash
photo-remove-dupes --db media.db \
  --base-dir /photos \
  --dry-run
```

### GUI Application

Launch the graphical interface:

```bash
photo-gui
```

The GUI provides:
- Dropdown to select command
- Dynamic form fields
- Command preview
- Dry-run testing
- Load/save configurations

## Configuration Files

### YAML Configuration

Each tool can use a YAML configuration file for the GUI:

```yaml
title: "Index Media Files"
description: "Scan and index photos/videos"
command: "python3 index_media.py"
working_dir: "."
window_size: "800x600"

parameters:
  - name: "--source"
    label: "Source Directory"
    type: "directory"
    required: true
    
  - name: "--db"
    label: "Database Path"
    type: "file"
    default: "media.db"
    
  - name: "--dry-run"
    label: "Dry Run"
    type: "checkbox"
```

### JSON Configuration

Save/load application state:

```json
{
  "command": "index_media",
  "parameters": {
    "source": "/path/to/photos",
    "db": "media.db",
    "volume": "MyPhotos",
    "dry_run": false
  }
}
```

## Database Schema

The SQLite database includes:

- **files**: Main file records with hash, size, dates
- **image_metadata**: EXIF data, GPS, camera info
- **video_metadata**: Video codec, duration, frame rate
- **thumbnails**: Embedded thumbnails
- **skipped_files**: Files that couldn't be processed

## Examples

### Complete Workflow

```bash
# 1. Index your photo collection
photo-index --source ~/Pictures --db photos.db --volume "Main"

# 2. Add location tags to vacation photos
photo-apply-exif --files vacation/*.jpg \
  --place "Santorini, Greece" \
  --keywords "vacation,2024,greece" \
  --db photos.db

# 3. Find duplicates
photo-manage-dupes --source ~/Pictures --db photos.db

# 4. Organize by moving to archive
photo-move --files old_photos/*.jpg \
  --destination ~/Archive/2020 \
  --volume "Archive" \
  --db photos.db

# 5. Locate a specific file
photo-locate --files IMG_1234.jpg --db photos.db --metadata
```

### Batch Processing

```bash
# Process all JPEGs in a directory
for file in /path/to/photos/*.jpg; do
  photo-apply-exif --files "$file" \
    --place "New York" \
    --db photos.db
done

# Or use find
find /path/to/photos -name "*.jpg" -exec \
  photo-apply-exif --files {} --place "New York" --db photos.db \;
```

## Troubleshooting

### exiftool not found

```bash
# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# macOS
brew install exiftool

# Verify installation
exiftool -ver
```

### Permission denied

```bash
# Make scripts executable
chmod +x *.py

# Or run with python3
python3 index_media.py --help
```

### Module not found

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Database locked

```bash
# Close other applications using the database
# Or copy database to a new location
cp media.db media_backup.db
```

## Development

### Running Tests

```bash
# Run all tests
cd tests
bash run_all_tests.sh

# Run specific test
python3 -m unittest tests.test_index_media

# Run with coverage
bash run_all_tests.sh --coverage
```

### Adding New Scripts

1. Create your script (e.g., `my_tool.py`)
2. Add entry point to `setup.py`
3. Create YAML config for GUI
4. Update documentation

## Uninstallation

```bash
./uninstall.sh
```

Or manually:

```bash
source venv/bin/activate
pip uninstall photo-management-tools
deactivate
rm -rf venv
```

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions:
- GitHub: https://github.com/yourusername/photo-management-tools
- Email: your.email@example.com

## Version History

### 1.0.0 (2026-01-30)
- Initial release
- Core indexing and EXIF management
- GUI interface
- Duplicate detection
- Location tagging
- Database integration
