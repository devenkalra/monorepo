#!/bin/bash
# Launch script for Media Processor GUI

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory
cd "$SCRIPT_DIR"

# Check if Python3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH"
    exit 1
fi

# Check if Pillow is installed
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "Warning: Pillow is not installed. Image preview may not work."
    echo "Install with: pip install Pillow"
    echo ""
fi

# Check if exiftool is available
if ! command -v exiftool &> /dev/null; then
    echo "Warning: exiftool is not installed or not in PATH"
    echo "EXIF operations will not work without it."
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install libimage-exiftool-perl"
    echo "  macOS: brew install exiftool"
    echo ""
fi

# Launch the application
echo "Starting Media Processor GUI..."
python3 media_processor_app.py "$@"
