# Drag and Drop Feature

## Overview
The Media Processor GUI now supports drag and drop functionality for the Directory and Database path fields. You can drag files or folders from your file explorer directly into these fields to populate them.

## Supported Fields

### 1. Directory Field
- **Location**: Top of the main window
- **Label**: "Directory:"
- **What you can drop**:
  - Folders/directories
  - Files (will use the file's parent directory)
- **Behavior**: 
  - Dropped path is set as the current directory
  - File list automatically refreshes to show files in the dropped directory

### 2. Database Field
- **Location**: Below the file browser, in the operations section
- **Label**: "Database:"
- **What you can drop**:
  - `.db` database files only
- **Behavior**:
  - Dropped file path is set as the database path
  - If you drop a non-`.db` file, you'll see a warning message

## How to Use

### Dragging a Directory
1. Open your file explorer (Nautilus, Dolphin, Finder, Windows Explorer, etc.)
2. Navigate to the folder you want to process
3. Drag the folder from the file explorer
4. Drop it onto the "Directory:" field in the Media Processor
5. The file list will automatically refresh to show files in that directory

### Dragging a Database File
1. Open your file explorer
2. Navigate to your media database file (e.g., `media.db`)
3. Drag the `.db` file from the file explorer
4. Drop it onto the "Database:" field in the Media Processor
5. The database path is now set

### Dragging a File (for Directory)
If you drag a regular file (not a database) onto the Directory field:
- The application will use the file's parent directory
- Useful when you want to quickly navigate to a file's location

## Requirements

### tkinterdnd2 Library
The drag and drop feature requires the `tkinterdnd2` library:

```bash
pip install tkinterdnd2
```

This is included in `requirements.txt` and will be installed automatically when you run:

```bash
pip install -r requirements.txt
```

### Fallback Behavior
If `tkinterdnd2` is not installed:
- The application will still work normally
- Drag and drop will not be available
- You can still use the "Browse..." buttons
- Right-clicking on the fields will show a message about installing tkinterdnd2

## Platform Support

### Linux
- Works with most file managers (Nautilus, Dolphin, Thunar, etc.)
- Supports both Wayland and X11 (though X11 is more reliable)

### macOS
- Works with Finder
- Fully supported

### Windows
- Works with Windows Explorer
- Fully supported

## Technical Details

### Implementation
- Uses `tkinterdnd2` library for cross-platform drag and drop
- Gracefully degrades if library is not available
- Handles multiple file formats and edge cases:
  - Paths with spaces
  - Paths with special characters
  - Windows-style paths with curly braces
  - Multiple files (takes the first one)

### Event Handling
- `<<Drop>>` event is bound to entry widgets
- Drop callbacks parse the dropped data
- Validation ensures correct file types
- Automatic UI updates after successful drop

### Path Parsing
The application handles various path formats:
- Unix paths: `/home/user/photos`
- Windows paths: `C:\Users\user\photos`
- Paths with spaces: `/home/user/My Photos`
- Multiple files: Takes the first file/folder
- Curly braces (Windows): `{C:\path\to\file}` → `C:\path\to\file`

## Use Cases

### Quick Navigation
Drag a folder from your file explorer to instantly navigate to it without using the Browse dialog.

### Database Selection
Drag your database file to quickly set the database path, especially useful when working with multiple databases.

### Workflow Integration
Integrate with your file manager workflow:
1. Browse files in your file manager
2. Drag the folder you want to process
3. Immediately start working with those files

### Batch Processing
When processing multiple directories:
1. Keep file manager open
2. Drag each directory in sequence
3. Process files
4. Drag next directory
5. Repeat

## Troubleshooting

### Drag and Drop Not Working

**Problem**: Nothing happens when I drag and drop

**Solutions**:
1. Check if tkinterdnd2 is installed:
   ```bash
   python3 -c "import tkinterdnd2; print('Installed')"
   ```

2. Install if missing:
   ```bash
   pip install tkinterdnd2
   ```

3. Restart the application after installing

### Wrong Path Detected

**Problem**: The dropped path is incorrect or truncated

**Possible causes**:
- Path contains special characters
- Multiple files were selected
- File manager uses a non-standard format

**Solution**: Use the Browse button as a fallback

### Database File Rejected

**Problem**: "Please drop a .db database file" warning appears

**Cause**: You dropped a file that doesn't have a `.db` extension

**Solution**: Ensure you're dropping a valid SQLite database file with `.db` extension

## Future Enhancements

Potential improvements for future versions:
- Drag and drop for destination fields in dialogs
- Visual feedback during drag (highlight drop zones)
- Support for dropping multiple files to add to selection
- Drag files from the file list to external applications

## Examples

### Example 1: Processing Photos from Downloads
1. Open Downloads folder in file manager
2. Drag the `vacation_photos` folder
3. Drop onto Directory field
4. Photos appear in file list
5. Select and process

### Example 2: Switching Databases
1. Have multiple database files: `main.db`, `backup.db`, `archive.db`
2. Drag `main.db` to Database field to work with main library
3. Later, drag `archive.db` to switch to archive library
4. No need to browse through file system each time

### Example 3: Quick File Location
1. Find an interesting photo in file manager
2. Drag the photo file onto Directory field
3. Application navigates to the photo's directory
4. See all other files in the same location
