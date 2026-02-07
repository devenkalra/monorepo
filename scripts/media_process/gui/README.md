# Media Processor GUI

A graphical user interface for processing media files including images and videos.

## Supported Formats

### Standard Image Formats
- JPEG/JPG
- PNG
- GIF
- BMP
- TIFF

### HEIF/HEIC Formats
- HEIC (High Efficiency Image Container - Apple)
- HEIF (High Efficiency Image Format)
- AVIF (AV1 Image File Format)

**Requirements:** Install `pillow-heif` or `ImageMagick` for preview support

### RAW Camera Formats
- **Canon:** CR2, CR3
- **Nikon:** NEF, NRW
- **Sony:** ARW, SRF, SR2
- **Adobe/Generic:** DNG
- **Olympus:** ORF
- **Panasonic:** RW2
- **Pentax:** PEF
- **Fujifilm:** RAF
- **Hasselblad:** 3FR
- **Kodak:** DCR, K25, KDC
- **Mamiya:** MEF
- **Leaf:** MOS
- **Minolta:** MRW
- **RED:** R3D
- **Leica:** RWL
- **Samsung:** SRW
- **Sigma:** X3F

**Requirements:** Install `rawpy` or `ImageMagick` or `dcraw` for preview support

### Video Formats
All formats supported by the system (MP4, MOV, AVI, MKV, etc.)
**Note:** Video preview is not available, only file information.

## Features

### File Browser
- Browse directories and view media files
- Filter by filename
- Filter by file type (Images, Videos, Other)
- Multi-select support
- Recursive directory scanning

### Preview & Information
- Image preview for selected files
- File information display
- EXIF data viewing (using exiftool)
- Summary statistics for multiple selected files

### Bulk Operations

#### 1. Index Media Files
- Index selected media files into a database
- Extract metadata (EXIF, video info)
- Generate thumbnails
- Configurable volume tags

#### 2. Move Media Files
- Move files to a new location
- Update database with new paths
- Preserve or update metadata
- Dry-run mode for testing

#### 3. Manage Duplicates
- Scan directories for duplicate files
- Identify duplicates by content hash
- Move or copy duplicates to separate directory
- Preserve directory structure
- Media-only filtering option

#### 4. Locate in Database
- Find files in the database
- Search by path or hash
- View database records for selected files

#### 5. Apply EXIF Tags
- Add location metadata (geocoding support)
- Add keywords and captions
- Update database records after EXIF changes
- Batch processing support

## Requirements

### Python Packages

**Required:**
```bash
pip install Pillow
```

**Optional (for HEIC/HEIF and RAW support):**
```bash
pip install pillow-heif  # For HEIC/HEIF formats
pip install rawpy numpy  # For RAW camera formats
```

### External Tools

**Required:**
- **exiftool**: Required for EXIF operations
  ```bash
  # Ubuntu/Debian
  sudo apt-get install libimage-exiftool-perl
  
  # macOS
  brew install exiftool
  ```

**Optional (for HEIC/HEIF and RAW support):**
- **ImageMagick**: Alternative for HEIC/HEIF and RAW preview
  ```bash
  # Ubuntu/Debian
  sudo apt-get install imagemagick libraw-dev
  
  # macOS
  brew install imagemagick
  ```

- **dcraw**: Alternative for RAW preview
  ```bash
  # Ubuntu/Debian
  sudo apt-get install dcraw
  
  # macOS
  brew install dcraw
  ```

### Parent Scripts
The GUI depends on these scripts in the parent directory:
- `index_media.py` - Media indexing functionality
- `move_media.py` - File moving operations
- `manage_dupes.py` - Duplicate management
- `locate_in_db.py` - Database lookup
- `apply_exif.py` - EXIF tag application
- `media_utils.py` - Shared utilities

## Usage

### Quick Start

1. Launch the application:
   ```bash
   python3 media_processor_app.py
   ```

2. Browse to a directory containing media files

3. Select a database file (or create a new one)

4. Select files in the file browser

5. Choose an operation from the bottom panel

### Directory Browser
- Click "Browse..." to select a directory
- Use the filter box to search for specific files
- Check/uncheck file type filters to show/hide different file types
- Click "Refresh" to reload the file list

### File Selection
- Click on files to select them
- Hold Ctrl (Cmd on Mac) to select multiple files
- Hold Shift to select a range of files
- Selected files show in the "Selected: N files" label

### Preview Panel
- Single file selection: Shows image preview and detailed info
- Multiple file selection: Shows summary statistics
- EXIF data is displayed when available

### Database Configuration
- Click "Browse..." next to Database field
- Select an existing SQLite database or create a new one
- Database is required for most operations

### Running Operations

All operations open a dialog with:
- Operation-specific options
- Real-time output display
- Dry-run mode for testing
- Progress feedback

**Index Media Files:**
1. Select files to index
2. Specify database
3. Set volume name
4. Choose dry-run if testing
5. Click "Start"

**Move Media Files:**
1. Select files to move
2. Specify database and destination
3. Set volume name
4. Choose dry-run if testing
5. Click "Start"

**Manage Duplicates:**
1. Specify database
2. Set destination for duplicates
3. Choose action (move/copy)
4. Enable "Media files only" to skip non-media
5. Choose dry-run if testing
6. Click "Start"

**Locate in Database:**
1. Select files to locate
2. Specify database
3. Click "Start"

**Apply EXIF Tags:**
1. Select files to tag
2. Enter location (for geocoding)
3. Add keywords (comma-separated)
4. Add caption if desired
5. Enable database update if needed
6. Choose dry-run if testing
7. Click "Start"

## Tips

- **Always use dry-run first**: Test operations with `--dry-run` before making actual changes
- **Database backups**: Back up your database before bulk operations
- **Filter smartly**: Use filename filters to quickly find specific files
- **Batch operations**: Select multiple files for efficient bulk processing
- **Preview before acting**: Check file info and preview before running operations

## Troubleshooting

### "exiftool not found"
Install exiftool using your package manager (see Requirements section)

### "Script not found" errors
Ensure all parent scripts are present in the parent directory

### Preview not showing
- Check that Pillow is installed: `pip install Pillow`
- Verify the file is a supported image format

### Operation fails silently
- Check the output panel in the operation dialog
- Verify database path is correct
- Ensure you have write permissions

## Architecture

The GUI is organized into:
- **MediaProcessorApp**: Main application window
- **OperationDialogBase**: Base class for operation dialogs
- **Operation Dialogs**: Specialized dialogs for each operation
  - IndexMediaDialog
  - MoveMediaDialog
  - ManageDuplicatesDialog
  - LocateInDbDialog
  - ApplyExifDialog

Each operation dialog:
- Validates inputs
- Builds command-line arguments
- Runs the underlying Python script
- Displays real-time output

## Development

### Adding New Operations

1. Create a new dialog class inheriting from `OperationDialogBase`
2. Implement `setup_ui()` to create the dialog interface
3. Implement `start()` to build and run the command
4. Add a button and method to `MediaProcessorApp`

Example:
```python
class NewOperationDialog(OperationDialogBase):
    def __init__(self, parent, files, db_path):
        super().__init__(parent, "New Operation", 700, 500)
        self.files = files
        self.db_path = db_path
        self.setup_ui()
    
    def setup_ui(self):
        # Create UI elements
        pass
    
    def start(self):
        # Build and run command
        pass
```

### Extending the File Browser

The file browser can be extended with:
- Additional file type filters
- Sort options (by name, date, size)
- Tree view for nested directories
- Thumbnail grid view

## License

This GUI is part of the media processing scripts suite.
