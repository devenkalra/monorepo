#!/usr/bin/env bash
#
# Photo Management Tools - Deployment Script
# Creates a self-contained package for deployment
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_NAME="photo-management-tools"
VERSION="1.0.0"
DIST_DIR="$SCRIPT_DIR/dist"
PACKAGE_DIR="$DIST_DIR/$PACKAGE_NAME-$VERSION"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}║  Photo Management Tools - Deployment Package Creator              ║${NC}"
echo -e "${BLUE}║                                                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo

# Clean previous builds
echo -e "${BLUE}Cleaning previous builds...${NC}"
rm -rf "$DIST_DIR"
rm -rf "$SCRIPT_DIR/build"
rm -rf "$SCRIPT_DIR"/*.egg-info

# Create distribution directory
mkdir -p "$PACKAGE_DIR"

# Copy Python scripts
echo -e "${BLUE}Copying Python scripts...${NC}"
cp "$SCRIPT_DIR"/*.py "$PACKAGE_DIR/" 2>/dev/null || true

# Copy configuration files
echo -e "${BLUE}Copying configuration files...${NC}"
cp "$SCRIPT_DIR"/*.yaml "$PACKAGE_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR"/*.json "$PACKAGE_DIR/" 2>/dev/null || true

# Copy requirements and setup files
cp "$SCRIPT_DIR/requirements.txt" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/setup.py" "$PACKAGE_DIR/"

# Copy documentation
echo -e "${BLUE}Copying documentation...${NC}"
cp "$SCRIPT_DIR/DEPLOYMENT_README.md" "$PACKAGE_DIR/README.md" 2>/dev/null || \
    echo "# Photo Management Tools" > "$PACKAGE_DIR/README.md"

cp "$SCRIPT_DIR"/*_usage.md "$PACKAGE_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR"/*_guide.md "$PACKAGE_DIR/" 2>/dev/null || true

# Copy tests (optional)
if [ -d "$SCRIPT_DIR/tests" ]; then
    echo -e "${BLUE}Copying tests...${NC}"
    mkdir -p "$PACKAGE_DIR/tests"
    cp "$SCRIPT_DIR/tests"/*.py "$PACKAGE_DIR/tests/" 2>/dev/null || true
    cp "$SCRIPT_DIR/tests"/*.sh "$PACKAGE_DIR/tests/" 2>/dev/null || true
    cp "$SCRIPT_DIR/tests"/*.md "$PACKAGE_DIR/tests/" 2>/dev/null || true
fi

# Create installation script
echo -e "${BLUE}Creating installation script...${NC}"
cat > "$PACKAGE_DIR/install.sh" << 'INSTALL_EOF'
#!/usr/bin/env bash
#
# Installation script for Photo Management Tools
#

set -e

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                                                                   ║"
echo "║  Photo Management Tools - Installation                           ║"
echo "║                                                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"

# Check for exiftool
if ! command -v exiftool &> /dev/null; then
    echo "⚠️  Warning: exiftool not found. Some features will not work."
    echo "   Install with: sudo apt-get install libimage-exiftool-perl (Ubuntu/Debian)"
    echo "   or: brew install exiftool (macOS)"
fi

# Create virtual environment
echo
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install package
echo
echo "Installing photo management tools..."
pip install -e .

echo
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                                                                   ║"
echo "║  ✅ Installation Complete!                                        ║"
echo "║                                                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo
echo "To use the tools:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo
echo "  2. Run any command:"
echo "     photo-index --help"
echo "     photo-apply-exif --help"
echo "     photo-gui"
echo
echo "Available commands:"
echo "  • photo-index          - Index media files"
echo "  • photo-apply-exif     - Apply EXIF metadata"
echo "  • photo-move           - Move media files"
echo "  • photo-locate         - Locate files in database"
echo "  • photo-show-exif      - Display EXIF data"
echo "  • photo-find-location  - Find location coordinates"
echo "  • photo-manage-dupes   - Manage duplicate files"
echo "  • photo-remove-dupes   - Remove duplicate files"
echo "  • photo-gui            - Launch GUI application"
echo
INSTALL_EOF

chmod +x "$PACKAGE_DIR/install.sh"

# Create uninstall script
cat > "$PACKAGE_DIR/uninstall.sh" << 'UNINSTALL_EOF'
#!/usr/bin/env bash
#
# Uninstallation script for Photo Management Tools
#

set -e

echo "Uninstalling Photo Management Tools..."

if [ -d "venv" ]; then
    source venv/bin/activate
    pip uninstall -y photo-management-tools
    deactivate
    rm -rf venv
fi

echo "✓ Uninstallation complete"
UNINSTALL_EOF

chmod +x "$PACKAGE_DIR/uninstall.sh"

# Create MANIFEST.in for package data
cat > "$PACKAGE_DIR/MANIFEST.in" << 'MANIFEST_EOF'
include README.md
include requirements.txt
include *.yaml
include *.json
include *_usage.md
include *_guide.md
recursive-include tests *.py *.sh *.md
MANIFEST_EOF

# Create .gitignore
cat > "$PACKAGE_DIR/.gitignore" << 'GITIGNORE_EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.coverage
htmlcov/
.pytest_cache/

# Database
*.db
*.db-journal

# Logs
*.log

# OS
.DS_Store
Thumbs.db
GITIGNORE_EOF

# Create archive
echo
echo -e "${BLUE}Creating archive...${NC}"
cd "$DIST_DIR"
tar -czf "$PACKAGE_NAME-$VERSION.tar.gz" "$PACKAGE_NAME-$VERSION"
zip -r -q "$PACKAGE_NAME-$VERSION.zip" "$PACKAGE_NAME-$VERSION"

# Calculate checksums
echo -e "${BLUE}Calculating checksums...${NC}"
cd "$DIST_DIR"
sha256sum "$PACKAGE_NAME-$VERSION.tar.gz" > "$PACKAGE_NAME-$VERSION.tar.gz.sha256"
sha256sum "$PACKAGE_NAME-$VERSION.zip" > "$PACKAGE_NAME-$VERSION.zip.sha256"

# Summary
echo
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                                   ║${NC}"
echo -e "${GREEN}║  ✅ Deployment Package Created Successfully!                      ║${NC}"
echo -e "${GREEN}║                                                                   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "${BLUE}Package Location:${NC}"
echo "  Directory: $PACKAGE_DIR"
echo "  Archive:   $DIST_DIR/$PACKAGE_NAME-$VERSION.tar.gz"
echo "  Archive:   $DIST_DIR/$PACKAGE_NAME-$VERSION.zip"
echo
echo -e "${BLUE}Package Contents:${NC}"
ls -lh "$PACKAGE_DIR" | tail -n +2 | awk '{print "  " $9 " (" $5 ")"}'
echo
echo -e "${BLUE}Archive Sizes:${NC}"
ls -lh "$DIST_DIR"/*.tar.gz "$DIST_DIR"/*.zip 2>/dev/null | awk '{print "  " $9 " - " $5}'
echo
echo -e "${BLUE}To deploy:${NC}"
echo "  1. Copy the archive to target system:"
echo "     scp $DIST_DIR/$PACKAGE_NAME-$VERSION.tar.gz user@host:/path/"
echo
echo "  2. Extract and install:"
echo "     tar -xzf $PACKAGE_NAME-$VERSION.tar.gz"
echo "     cd $PACKAGE_NAME-$VERSION"
echo "     ./install.sh"
echo
