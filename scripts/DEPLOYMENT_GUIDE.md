# Photo Management Tools - Deployment Guide

## Quick Start

### For the Deployer (You)

1. **Package is ready at:**
   ```
   /home/ubuntu/monorepo/scripts/dist/photo-management-tools-1.0.0.tar.gz
   /home/ubuntu/monorepo/scripts/dist/photo-management-tools-1.0.0.zip
   ```

2. **Transfer to target system:**
   ```bash
   # Via SCP
   scp photo-management-tools-1.0.0.tar.gz user@target-host:/tmp/
   
   # Via USB/Network share
   # Just copy the .tar.gz or .zip file
   ```

### For the Recipient (Target System)

1. **Extract the package:**
   ```bash
   tar -xzf photo-management-tools-1.0.0.tar.gz
   cd photo-management-tools-1.0.0
   ```

2. **Install:**
   ```bash
   ./install.sh
   ```

3. **Use:**
   ```bash
   source venv/bin/activate
   photo-gui  # Launch GUI
   # or
   photo-index --help  # Use command-line tools
   ```

## What's Included

### Python Scripts (Core Tools)
- `index_media.py` - Index media files into database
- `apply_exif.py` - Apply EXIF/GPS metadata
- `move_media.py` - Move files with database tracking
- `locate_in_db.py` - Find files in database
- `show_exif.py` - Display EXIF information
- `find_location.py` - Geocode locations
- `manage_dupes.py` - Detect duplicates
- `remove_dupes.py` - Remove duplicates
- `image_process.py` - Unified GUI application
- `command_runner.py` - Generic GUI runner

### Utility Modules
- `media_utils.py` - Shared media utilities
- `location_utils.py` - Location/geocoding utilities
- `audit_utils.py` - Audit logging utilities

### Configuration Files
- `*.yaml` - GUI configuration files
- `image_process_config.json` - GUI state
- `requirements.txt` - Python dependencies
- `setup.py` - Package installation

### Documentation
- `README.md` - Main documentation
- `*_usage.md` - Individual tool guides
- `*_guide.md` - Feature guides

### Installation Scripts
- `install.sh` - Automated installation
- `uninstall.sh` - Removal script

### Tests (Optional)
- `tests/` - Test suite for development

## System Requirements

### Minimum Requirements
- **OS**: Linux, macOS, or Windows with WSL
- **Python**: 3.8 or higher
- **Disk**: 100MB for installation
- **RAM**: 512MB minimum

### Recommended
- **Python**: 3.10 or higher
- **Disk**: 1GB+ (for media database)
- **RAM**: 2GB+ (for large collections)

### External Dependencies
- **exiftool** (required for EXIF operations)
  - Ubuntu/Debian: `sudo apt-get install libimage-exiftool-perl`
  - macOS: `brew install exiftool`
  - Windows: Download from https://exiftool.org/

## Installation Methods

### Method 1: Automated (Recommended)

```bash
tar -xzf photo-management-tools-1.0.0.tar.gz
cd photo-management-tools-1.0.0
./install.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Set up command-line tools
- Verify installation

### Method 2: Manual

```bash
# Extract
tar -xzf photo-management-tools-1.0.0.tar.gz
cd photo-management-tools-1.0.0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install package
pip install -e .
```

### Method 3: System-wide (Not Recommended)

```bash
# Extract
tar -xzf photo-management-tools-1.0.0.tar.gz
cd photo-management-tools-1.0.0

# Install system-wide (requires sudo)
sudo pip3 install -r requirements.txt
sudo pip3 install -e .
```

## Verification

### Check Installation

```bash
source venv/bin/activate

# Check commands are available
photo-index --version
photo-apply-exif --help
photo-gui --help

# Check Python modules
python3 -c "import media_utils; print('✓ media_utils OK')"
python3 -c "import location_utils; print('✓ location_utils OK')"
```

### Test Basic Functionality

```bash
# Create test directory
mkdir -p /tmp/photo-test
cd /tmp/photo-test

# Test indexing (dry-run)
photo-index --source . --db test.db --volume "Test" --dry-run --verbose 2

# Test location lookup
photo-find-location --place "New York, NY"

# Launch GUI
photo-gui
```

## Usage Examples

### Example 1: Index Photo Collection

```bash
source venv/bin/activate

photo-index \
  --source /mnt/photos/vacation-2024 \
  --db /home/user/photos.db \
  --volume "Vacation2024" \
  --verbose 2
```

### Example 2: Add GPS Tags

```bash
photo-apply-exif \
  --files /mnt/photos/vacation-2024/*.jpg \
  --place "Paris, France" \
  --keywords "vacation,2024,europe" \
  --db /home/user/photos.db
```

### Example 3: Find Duplicates

```bash
photo-manage-dupes \
  --source /mnt/photos \
  --db /home/user/photos.db \
  --dry-run
```

### Example 4: Use GUI

```bash
photo-gui
```

Then:
1. Select command from dropdown
2. Fill in parameters
3. Click "Preview Command" to see what will run
4. Enable "Dry Run" to test
5. Click "Run Command"

## Deployment Scenarios

### Scenario 1: Single User Desktop

```bash
# Install in home directory
cd ~
tar -xzf photo-management-tools-1.0.0.tar.gz
cd photo-management-tools-1.0.0
./install.sh

# Add to .bashrc for easy access
echo 'alias photo-tools="cd ~/photo-management-tools-1.0.0 && source venv/bin/activate"' >> ~/.bashrc
```

### Scenario 2: Shared Server

```bash
# Install in shared location
sudo mkdir -p /opt/photo-tools
sudo tar -xzf photo-management-tools-1.0.0.tar.gz -C /opt/photo-tools
cd /opt/photo-tools/photo-management-tools-1.0.0
sudo ./install.sh

# Make accessible to all users
sudo chmod -R 755 /opt/photo-tools
```

### Scenario 3: Air-Gapped System

1. On internet-connected system:
   ```bash
   # Download all dependencies
   pip download -r requirements.txt -d ./wheels
   
   # Create complete package
   tar -czf photo-tools-complete.tar.gz \
     photo-management-tools-1.0.0/ \
     wheels/
   ```

2. Transfer `photo-tools-complete.tar.gz` to air-gapped system

3. On air-gapped system:
   ```bash
   tar -xzf photo-tools-complete.tar.gz
   cd photo-management-tools-1.0.0
   
   python3 -m venv venv
   source venv/bin/activate
   pip install --no-index --find-links=../wheels -r requirements.txt
   pip install -e .
   ```

## Troubleshooting

### Issue: "python3: command not found"

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install python3 python3-pip python3-venv

# macOS
brew install python3

# Verify
python3 --version
```

### Issue: "exiftool: command not found"

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install libimage-exiftool-perl

# macOS
brew install exiftool

# Verify
exiftool -ver
```

### Issue: "Permission denied"

**Solution:**
```bash
# Make scripts executable
chmod +x *.py *.sh

# Or run with python3
python3 index_media.py --help
```

### Issue: "Module not found"

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

### Issue: "Database is locked"

**Solution:**
```bash
# Check for other processes
lsof media.db

# Or use a different database location
photo-index --db /tmp/media.db ...
```

## Updating

To update to a new version:

```bash
# Uninstall old version
./uninstall.sh

# Extract new version
tar -xzf photo-management-tools-2.0.0.tar.gz
cd photo-management-tools-2.0.0

# Install new version
./install.sh
```

## Uninstallation

```bash
cd photo-management-tools-1.0.0
./uninstall.sh
```

Or manually:

```bash
source venv/bin/activate
pip uninstall -y photo-management-tools
deactivate
rm -rf venv
```

## Package Integrity

Verify package integrity using checksums:

```bash
# For .tar.gz
sha256sum -c photo-management-tools-1.0.0.tar.gz.sha256

# For .zip
sha256sum -c photo-management-tools-1.0.0.zip.sha256
```

Expected checksums:
- **tar.gz**: `450ad016a91a305e2c7b23bd8875e658db1755fdadc14541660671c0acb63404`
- **zip**: `ed6ab1b6ba14fb412f1ebb5be167ff8cdbe5b613eb5b2d33c9abf2301e59f806`

## Support

For issues or questions:
- Check documentation in `README.md`
- Review individual tool guides (`*_usage.md`)
- Check test examples in `tests/`

## License

MIT License - Free to use, modify, and distribute.
