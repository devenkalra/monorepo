# Changelog - Media Processor GUI

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-02-05

### Added - HEIF/HEIC and RAW Format Support

#### New Features
- **HEIF/HEIC Format Support**
  - Support for `.heic`, `.heif`, and `.avif` formats
  - Preview using pillow-heif or ImageMagick
  - Automatic format detection
  
- **RAW Camera Format Support**
  - Support for 30+ RAW formats from all major manufacturers
  - Canon (CR2, CR3), Nikon (NEF), Sony (ARW), and more
  - Preview using rawpy, ImageMagick, or dcraw
  - Intelligent fallback mechanism

- **Smart Image Loading**
  - New `load_image_with_fallback()` function
  - Tries multiple methods in priority order
  - Graceful degradation when libraries unavailable
  - Clear error messages with installation suggestions

#### Enhanced UI
- Loading indicators for slow formats (RAW/HEIF)
- Format-specific file counting in multi-select
- Better error messages for unsupported formats
- Separate counts for standard/HEIF/RAW in file info

#### Documentation
- New `HEIF_RAW_SUPPORT.md` - Comprehensive format support guide
- New `HEIF_RAW_IMPLEMENTATION.md` - Implementation details
- Updated `README.md` with supported formats
- Updated `INSTALL.md` with optional dependencies
- Updated `QUICKSTART.md` with HEIF/RAW setup
- Updated `PROJECT_SUMMARY.md` with new features

#### Dependencies
- Added optional: `pillow-heif>=0.13.0`
- Added optional: `rawpy>=0.18.0`
- Added optional: `numpy>=1.20.0`
- Alternative tools: ImageMagick, dcraw

#### Tools
- Enhanced `check_prerequisites.py` to verify HEIF/RAW support
- Checks for pillow-heif, rawpy, ImageMagick, dcraw
- Provides installation commands for missing tools

### Changed
- File type detection now includes HEIF and RAW as images
- Preview function completely rewritten to support multiple formats
- Filter function updated to categorize HEIF/RAW correctly
- Multi-file info function enhanced with format breakdown

### Technical Details
- 30+ new file extensions supported
- 3 loading methods for HEIF/HEIC
- 3 loading methods for RAW
- No breaking changes to existing functionality
- Backward compatible with version 1.0.0

---

## [1.0.0] - 2026-02-05

### Added - Initial Release

#### Core Features
- **File Browser**
  - Directory browsing with recursive scanning
  - File filtering by name
  - File type filtering (Images/Videos/Other)
  - Multi-file selection (Ctrl/Shift+Click)
  - Relative path display

- **Preview Panel**
  - Image thumbnail preview (500x400)
  - Proportional scaling
  - Support for JPEG, PNG, GIF, BMP, TIFF

- **Information Panel**
  - File metadata display
  - EXIF data viewing via exiftool
  - Multi-file statistics

- **Bulk Operations**
  - Index Media Files
  - Move Media Files
  - Manage Duplicates
  - Locate in Database
  - Apply EXIF Tags

- **Operation Dialogs**
  - Modal dialogs for each operation
  - Real-time output display
  - Dry-run mode for all operations
  - Async execution (non-blocking)

#### Documentation
- `README.md` - User guide
- `INSTALL.md` - Installation instructions
- `QUICKSTART.md` - Quick start guide
- `UI_LAYOUT.md` - UI layout documentation
- `PROJECT_SUMMARY.md` - Project overview

#### Tools
- `run_media_processor.sh` - Launch script
- `check_prerequisites.py` - Dependency checker
- `media-processor.desktop` - Linux desktop entry

#### Dependencies
- Python 3.7+
- tkinter (standard library)
- Pillow for image handling
- exiftool for EXIF operations

#### Integration
- Integrates with parent scripts:
  - index_media.py
  - move_media.py
  - manage_dupes.py
  - locate_in_db.py
  - apply_exif.py
  - media_utils.py

### Technical Details
- ~1,100 lines of Python code
- 7 classes (1 main + 1 base + 5 dialogs)
- 40+ methods
- MVC-like architecture
- Async operation execution
- Comprehensive error handling

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.1.0 | 2026-02-05 | Added HEIF/HEIC and RAW format support |
| 1.0.0 | 2026-02-05 | Initial release with core features |

---

## Upgrade Instructions

### From 1.0.0 to 1.1.0

No breaking changes. Simply update the files:

```bash
cd /home/ubuntu/monorepo/scripts/media_process/gui
git pull  # If using git
```

**Optional:** Install HEIF/HEIC and RAW support:

```bash
# For HEIF/HEIC
pip3 install pillow-heif

# For RAW
pip3 install rawpy numpy

# Or install all from requirements
pip3 install -r requirements.txt
```

**Verify installation:**
```bash
python3 check_prerequisites.py
```

If you don't install the optional libraries, the application will still work - you just won't see previews for HEIF/HEIC and RAW files.

---

## Known Issues

### Version 1.1.0
- RAW preview can be slow for large files (40+ MB)
- Some proprietary RAW formats may not be supported
- HEIC support may require ImageMagick policy changes on some systems
- Windows rawpy installation can be challenging

### Version 1.0.0
- No known issues

---

## Roadmap

### Version 1.2.0 (Planned)
- Thumbnail caching for faster repeat access
- Sort options (by name, date, size, type)
- Progress bars for long operations
- Batch HEIF/RAW to JPEG converter
- Configuration file support

### Version 1.3.0 (Planned)
- Tree view for directory browsing
- Map view for GPS data
- Timeline view by date
- Advanced search and filtering
- Export results to CSV

### Version 2.0.0 (Future)
- RAW processing controls (white balance, exposure)
- GPU acceleration for RAW
- Video frame preview
- Plugin system for extensions
- Dark theme support

---

## Contributing

To contribute to this project:
1. Follow existing code style
2. Add docstrings to new code
3. Update documentation
4. Test thoroughly
5. Update CHANGELOG.md

---

## License

Part of the media processing scripts suite.

---

**Current Version:** 1.1.0  
**Last Updated:** 2026-02-05
