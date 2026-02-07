#!/usr/bin/env python3
"""
Check Prerequisites - Verify system requirements for Media Processor GUI

This script checks if all required dependencies and tools are installed.
Run this before launching the Media Processor GUI.
"""

import sys
import subprocess
import os


def check_python_version():
    """Check if Python version is 3.7 or later."""
    print("Checking Python version...", end=" ")
    version = sys.version_info
    if version >= (3, 7):
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} (Need 3.7+)")
        return False


def check_tkinter():
    """Check if tkinter is available."""
    print("Checking tkinter...", end=" ")
    try:
        import tkinter
        print(f"✓ tkinter {tkinter.TkVersion}")
        return True
    except ImportError:
        print("✗ Not installed")
        print("  Install: sudo apt-get install python3-tk (Ubuntu/Debian)")
        return False


def check_pillow():
    """Check if Pillow (PIL) is installed."""
    print("Checking Pillow...", end=" ")
    try:
        import PIL
        from PIL import Image
        print(f"✓ Pillow {PIL.__version__}")
        return True
    except ImportError:
        print("✗ Not installed")
        print("  Install: pip3 install Pillow")
        return False


def check_exiftool():
    """Check if exiftool is installed."""
    print("Checking exiftool...", end=" ")
    try:
        result = subprocess.run(
            ['exiftool', '-ver'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✓ exiftool {version}")
            return True
        else:
            print("✗ Not working properly")
            return False
    except FileNotFoundError:
        print("✗ Not installed")
        print("  Install: sudo apt-get install libimage-exiftool-perl (Ubuntu/Debian)")
        print("          brew install exiftool (macOS)")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def check_parent_scripts():
    """Check if required parent scripts exist."""
    print("\nChecking parent scripts:")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    required_scripts = [
        'index_media.py',
        'move_media.py',
        'manage_dupes.py',
        'locate_in_db.py',
        'apply_exif.py',
        'media_utils.py'
    ]
    
    all_present = True
    for script in required_scripts:
        script_path = os.path.join(parent_dir, script)
        if os.path.exists(script_path):
            print(f"  ✓ {script}")
        else:
            print(f"  ✗ {script} (not found)")
            all_present = False
            
    return all_present


def check_optional_dependencies():
    """Check optional dependencies."""
    print("\nChecking optional dependencies:")
    
    # pillow-heif for HEIC/HEIF support
    print("  pillow-heif...", end=" ")
    try:
        import pillow_heif
        print(f"✓ {pillow_heif.__version__}")
    except ImportError:
        print("⚠ Not installed (optional, needed for HEIC/HEIF preview)")
        print("    Install: pip3 install pillow-heif")
    
    # rawpy for RAW support
    print("  rawpy...", end=" ")
    try:
        import rawpy
        print(f"✓ {rawpy.__version__}")
    except ImportError:
        print("⚠ Not installed (optional, needed for RAW file preview)")
        print("    Install: pip3 install rawpy")
    
    # ImageMagick (alternative for HEIF/RAW)
    print("  ImageMagick...", end=" ")
    try:
        result = subprocess.run(
            ['convert', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✓ {version_line}")
        else:
            print("⚠ Not working")
    except FileNotFoundError:
        print("⚠ Not installed (alternative for HEIC/RAW preview)")
        print("    Install: sudo apt-get install imagemagick (Ubuntu)")
        print("            brew install imagemagick (macOS)")
    except Exception:
        print("⚠ Error checking")
    
    # dcraw (alternative for RAW)
    print("  dcraw...", end=" ")
    try:
        result = subprocess.run(
            ['dcraw'],
            capture_output=True,
            text=True,
            timeout=5
        )
        # dcraw returns non-zero when called without args, but is installed
        print("✓ Installed")
    except FileNotFoundError:
        print("⚠ Not installed (alternative for RAW preview)")
        print("    Install: sudo apt-get install dcraw (Ubuntu)")
        print("            brew install dcraw (macOS)")
    except Exception:
        print("⚠ Error checking")
    
    # PyYAML
    print("  PyYAML...", end=" ")
    try:
        import yaml
        print(f"✓ {yaml.__version__}")
    except ImportError:
        print("⚠ Not installed (optional, needed for YAML configs)")
        
    # geopy
    print("  geopy...", end=" ")
    try:
        import geopy
        print(f"✓ {geopy.__version__}")
    except ImportError:
        print("⚠ Not installed (optional, needed for geocoding)")
        
    # requests
    print("  requests...", end=" ")
    try:
        import requests
        print(f"✓ {requests.__version__}")
    except ImportError:
        print("⚠ Not installed (optional, needed for elevation API)")


def main():
    """Run all checks."""
    print("=" * 60)
    print("Media Processor GUI - Prerequisites Check")
    print("=" * 60)
    print()
    
    results = []
    
    # Required dependencies
    results.append(("Python 3.7+", check_python_version()))
    results.append(("tkinter", check_tkinter()))
    results.append(("Pillow", check_pillow()))
    results.append(("exiftool", check_exiftool()))
    results.append(("Parent scripts", check_parent_scripts()))
    
    # Optional dependencies (informational only)
    check_optional_dependencies()
    
    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    required_ok = all(result for name, result in results)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
    
    print()
    
    if required_ok:
        print("✓ All required dependencies are installed!")
        print()
        print("You can now run the Media Processor GUI:")
        print("  ./run_media_processor.sh")
        print("  or")
        print("  python3 media_processor_app.py")
        return 0
    else:
        print("✗ Some required dependencies are missing.")
        print()
        print("Please install missing dependencies and run this check again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
