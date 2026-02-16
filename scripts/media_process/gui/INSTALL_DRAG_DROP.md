# Installing Drag and Drop Support

## Quick Install

To enable drag and drop functionality in the Media Processor GUI, install the `tkinterdnd2` library:

```bash
pip install tkinterdnd2
```

That's it! Restart the application if it's already running.

## Verification

Check if tkinterdnd2 is installed:

```bash
python3 -c "import tkinterdnd2; print('✓ tkinterdnd2 is installed')"
```

If you see the success message, drag and drop is ready to use.

## Platform-Specific Notes

### Linux
Works on most distributions. If you encounter issues:

```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Fedora/RHEL
sudo dnf install python3-tkinter
```

### macOS
Should work out of the box. If not:

```bash
# Using Homebrew
brew install python-tk
```

### Windows
Should work out of the box with standard Python installation.

## Troubleshooting

### "No module named 'tkinterdnd2'"

**Solution**: Install the package:
```bash
pip install tkinterdnd2
```

### "ImportError: DLL load failed" (Windows)

**Solution**: Reinstall with:
```bash
pip uninstall tkinterdnd2
pip install --no-cache-dir tkinterdnd2
```

### Drag and Drop Not Working (Linux Wayland)

**Issue**: Some Wayland compositors have limited drag and drop support.

**Solution**: Run the application under XWayland:
```bash
GDK_BACKEND=x11 python3 media_processor_app.py
```

Or switch to X11 session temporarily.

### Permission Denied

**Issue**: pip install fails due to permissions.

**Solution**: Install for user only:
```bash
pip install --user tkinterdnd2
```

## Without Drag and Drop

The application works perfectly fine without tkinterdnd2:
- All features remain functional
- Use the "Browse..." buttons instead
- Drag and drop will simply not be available

## Testing

After installation, test drag and drop:

1. Start the application:
   ```bash
   python3 media_processor_app.py
   ```

2. Open your file manager

3. Drag a folder onto the "Directory:" field
   - Should populate the directory path
   - File list should refresh

4. Drag a `.db` file onto the "Database:" field
   - Should populate the database path

If both work, installation is successful!

## Updating

To update to the latest version:

```bash
pip install --upgrade tkinterdnd2
```

## Uninstalling

If you want to remove drag and drop support:

```bash
pip uninstall tkinterdnd2
```

The application will continue to work without it.
