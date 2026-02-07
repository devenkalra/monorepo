# Installation Guide - Media Processor GUI

This guide will help you install and set up the Media Processor GUI application.

## Prerequisites

### 1. Python 3
The application requires Python 3.7 or later.

**Check if Python 3 is installed:**
```bash
python3 --version
```

**Install Python 3 if needed:**
- **Ubuntu/Debian:**
  ```bash
  sudo apt-get update
  sudo apt-get install python3 python3-pip python3-tk
  ```

- **macOS:**
  ```bash
  brew install python3 python-tk
  ```

- **Windows:**
  Download from [python.org](https://www.python.org/downloads/)

### 2. Tkinter
Tkinter is Python's standard GUI library.

**Check if tkinter is installed:**
```bash
python3 -c "import tkinter"
```

**Install if needed:**
- **Ubuntu/Debian:**
  ```bash
  sudo apt-get install python3-tk
  ```

- **macOS:**
  Already included with Python from Homebrew

- **Windows:**
  Included with standard Python installation

### 3. ExifTool
ExifTool is required for EXIF metadata operations.

**Check if exiftool is installed:**
```bash
exiftool -ver
```

**Install exiftool:**
- **Ubuntu/Debian:**
  ```bash
  sudo apt-get install libimage-exiftool-perl
  ```

- **macOS:**
  ```bash
  brew install exiftool
  ```

- **Windows:**
  Download from [exiftool.org](https://exiftool.org/)

## Installation Steps

### 1. Install Python Dependencies

Navigate to the GUI directory:
```bash
cd /home/ubuntu/monorepo/scripts/media_process/gui
```

Install required packages:
```bash
pip3 install -r requirements.txt
```

Or install manually:

**Core (required):**
```bash
pip3 install Pillow
```

**Optional - HEIC/HEIF support:**
```bash
pip3 install pillow-heif
```

**Optional - RAW camera format support:**
```bash
pip3 install rawpy numpy
```

**Note:** If `rawpy` installation fails, you can use ImageMagick or dcraw as alternatives (see below).

### 2. Verify Parent Scripts

The GUI depends on these scripts in the parent directory:
- `index_media.py`
- `move_media.py`
- `manage_dupes.py`
- `locate_in_db.py`
- `apply_exif.py`
- `media_utils.py`

Check they exist:
```bash
ls -la ../*.py
```

### 3. Install Optional Tools for HEIC/HEIF and RAW Support

For **HEIC/HEIF** preview support (choose one or both):

**Option 1: Python library (recommended):**
```bash
pip3 install pillow-heif
```

**Option 2: ImageMagick:**
```bash
# Ubuntu/Debian
sudo apt-get install imagemagick

# macOS
brew install imagemagick
```

For **RAW camera format** preview support (choose one or more):

**Option 1: Python library (recommended):**
```bash
pip3 install rawpy numpy
```

**Option 2: ImageMagick with RAW support:**
```bash
# Ubuntu/Debian
sudo apt-get install imagemagick libraw-dev

# macOS
brew install imagemagick
```

**Option 3: dcraw (lightweight alternative):**
```bash
# Ubuntu/Debian
sudo apt-get install dcraw

# macOS
brew install dcraw
```

**Note:** The application will try multiple methods to load HEIC/HEIF and RAW files:
1. Python libraries first (fastest)
2. ImageMagick convert
3. dcraw (RAW only)

If none are installed, you can still view file information and perform operations, but preview will not be available.

### 4. Make the Launcher Script Executable

```bash
chmod +x run_media_processor.sh
```

### 5. Test the Installation

Run the application:
```bash
./run_media_processor.sh
```

Or run directly:
```bash
python3 media_processor_app.py
```

## Optional: Create Desktop Shortcut

### Linux (GNOME, KDE, etc.)

1. Edit the desktop file to use absolute paths:
   ```bash
   nano media-processor.desktop
   ```
   
   Update the `Exec` line with the correct path:
   ```
   Exec=/home/ubuntu/monorepo/scripts/media_process/gui/run_media_processor.sh
   ```

2. Copy to applications directory:
   ```bash
   cp media-processor.desktop ~/.local/share/applications/
   ```

3. Make it executable:
   ```bash
   chmod +x ~/.local/share/applications/media-processor.desktop
   ```

4. Update desktop database:
   ```bash
   update-desktop-database ~/.local/share/applications/
   ```

### macOS

1. Create an Automator application:
   - Open Automator
   - Choose "Application"
   - Add "Run Shell Script" action
   - Enter: `/home/ubuntu/monorepo/scripts/media_process/gui/run_media_processor.sh`
   - Save as "Media Processor.app" in Applications

### Windows

1. Create a shortcut:
   - Right-click in the gui folder
   - New > Shortcut
   - Target: `python media_processor_app.py`
   - Working directory: `<path-to-gui-folder>`
   - Name: "Media Processor"

## Verification

After installation, verify all features work:

### 1. Check GUI Launches
```bash
./run_media_processor.sh
```

You should see the main window with:
- Directory browser at top
- File list on left
- Preview and info panels on right
- Operation buttons at bottom

### 2. Test File Browser
- Click "Browse..." and select a directory with images
- Files should appear in the list
- Click a file to see preview and info

### 3. Test EXIF Display
- Select an image file with EXIF data
- Info panel should show EXIF metadata

### 4. Test Operations (Dry Run)
- Create or select a test database
- Select some files
- Try each operation with "Dry run" enabled
- Check output in operation dialog

## Troubleshooting

### "No module named 'PIL'"
Install Pillow:
```bash
pip3 install Pillow
```

### "No module named 'tkinter'"
Install tkinter:
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# macOS
brew reinstall python-tk
```

### "exiftool: command not found"
Install exiftool:
```bash
# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# macOS
brew install exiftool
```

### "Script not found" errors
Verify parent scripts exist:
```bash
ls -la ../*.py
```

### GUI doesn't appear (headless server)
If running on a headless server, you need X11 forwarding:
```bash
# Enable X11 forwarding when connecting via SSH
ssh -X user@server

# Or use VNC/Remote Desktop
```

### Permission denied when running launcher
Make script executable:
```bash
chmod +x run_media_processor.sh
```

### Database errors
- Ensure database file exists or can be created
- Check write permissions on database directory
- Verify database schema is up to date

## Uninstallation

To remove the application:

1. Remove installed Python packages:
   ```bash
   pip3 uninstall Pillow
   ```

2. Remove desktop shortcut (if created):
   ```bash
   rm ~/.local/share/applications/media-processor.desktop
   ```

3. Remove the gui directory:
   ```bash
   rm -rf /home/ubuntu/monorepo/scripts/media_process/gui
   ```

## Next Steps

After installation:
1. Read the [README.md](README.md) for usage instructions
2. Prepare a test directory with some media files
3. Create or select a database file
4. Try operations with dry-run mode first
5. Back up important data before bulk operations

## Support

For issues and questions:
- Check the [README.md](README.md) documentation
- Review operation output in dialog windows
- Check parent script documentation
- Verify all prerequisites are installed

## Updates

To update the application:
1. Pull latest changes from repository
2. Update Python packages: `pip3 install -U -r requirements.txt`
3. Restart the application

## Configuration

The application uses configuration from parent scripts:
- Database schema from `media_utils.py`
- Operation parameters from individual scripts
- YAML configuration files for specific operations

Refer to parent script documentation for advanced configuration options.
