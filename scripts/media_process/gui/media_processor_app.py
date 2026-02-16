#!/usr/bin/env python3
"""
Media Processor GUI - A tkinter application for processing media files.

Features:
- Directory browsing
- File preview (images)
- EXIF information display
- Bulk operations: Index, Move, Manage Duplicates, Locate in database
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import subprocess
import json
import yaml
import sqlite3
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
import threading

# Try to import tkinterdnd2 for drag and drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    # Fallback: will use Tk() instead of TkinterDnD.Tk()
    TkinterDnD = None

# Add parent directory to path to import utilities
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from media_utils import (
        get_mime_type, is_image_file, is_video_file, calculate_file_hash,
        create_database_schema, log_audit
    )
except ImportError:
    print("Warning: media_utils not found, some features may be limited")
    def get_mime_type(path): return ""
    def is_image_file(mime, ext): return ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2']
    def is_video_file(mime): return mime.startswith('video/')
    def calculate_file_hash(path): return ""
    def create_database_schema(conn): pass
    def log_audit(conn, operation, file_path, **kwargs): pass

# Additional imports for HEIC/HEIF/RAW support
try:
    import pillow_heif
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

try:
    import rawpy
    RAW_AVAILABLE = True
except ImportError:
    RAW_AVAILABLE = False

# Supported RAW formats
RAW_EXTENSIONS = {
    '.cr2', '.cr3',  # Canon
    '.nef', '.nrw',  # Nikon
    '.arw', '.srf', '.sr2',  # Sony
    '.dng',  # Adobe/Generic
    '.orf',  # Olympus
    '.rw2',  # Panasonic
    '.pef',  # Pentax
    '.raf',  # Fujifilm
    '.3fr',  # Hasselblad
    '.dcr', '.k25', '.kdc',  # Kodak
    '.mef',  # Mamiya
    '.mos',  # Leaf
    '.mrw',  # Minolta
    '.nrw',  # Nikon
    '.ptx', '.pxn',  # Pentax
    '.r3d',  # RED
    '.rwl',  # Leica
    '.rwz',  # Rawzor
    '.srw',  # Samsung
    '.x3f',  # Sigma
}

HEIF_EXTENSIONS = {'.heic', '.heif', '.avif'}


def is_raw_file(file_path: str) -> bool:
    """Check if file is a RAW format."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in RAW_EXTENSIONS


def is_heif_file(file_path: str) -> bool:
    """Check if file is a HEIF/HEIC format."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in HEIF_EXTENSIONS


def load_image_with_fallback(file_path: str) -> Optional[Image.Image]:
    """Load an image with support for HEIC/HEIF and RAW formats.
    
    Tries multiple methods to load the image:
    1. Standard PIL/Pillow (JPEG, PNG, etc.)
    2. HEIF support via pillow_heif
    3. RAW support via rawpy
    4. Fallback to ImageMagick convert
    
    Returns PIL Image object or None if all methods fail.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    # Try standard PIL first (works for JPEG, PNG, BMP, GIF, etc.)
    if ext not in RAW_EXTENSIONS and ext not in HEIF_EXTENSIONS:
        try:
            return Image.open(file_path)
        except Exception as e:
            print(f"PIL failed to load {file_path}: {e}")
            return None
    
    # Try HEIF/HEIC
    if ext in HEIF_EXTENSIONS:
        # Method 1: pillow_heif plugin
        if HEIF_AVAILABLE:
            try:
                pillow_heif.register_heif_opener()
                img = Image.open(file_path)
                # Convert to RGB if needed
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                return img
            except Exception as e:
                print(f"pillow_heif failed to load {file_path}: {e}")
        
        # Method 2: Try ImageMagick convert
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            result = subprocess.run(
                ['convert', file_path, tmp_path],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0 and os.path.exists(tmp_path):
                img = Image.open(tmp_path)
                os.unlink(tmp_path)
                return img
            
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            print(f"ImageMagick failed to load {file_path}: {e}")
        
        return None
    
    # Try RAW formats
    if ext in RAW_EXTENSIONS:
        # Method 1: rawpy
        if RAW_AVAILABLE:
            try:
                with rawpy.imread(file_path) as raw:
                    # Process RAW to RGB array
                    rgb = raw.postprocess()
                    img = Image.fromarray(rgb)
                    return img
            except Exception as e:
                print(f"rawpy failed to load {file_path}: {e}")
        
        # Method 2: Try ImageMagick convert
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            result = subprocess.run(
                ['convert', file_path, tmp_path],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0 and os.path.exists(tmp_path):
                img = Image.open(tmp_path)
                os.unlink(tmp_path)
                return img
            
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            print(f"ImageMagick failed to load {file_path}: {e}")
        
        # Method 3: Try dcraw
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.ppm', delete=False) as tmp:
                tmp_path = tmp.name
            
            result = subprocess.run(
                ['dcraw', '-c', file_path],
                stdout=open(tmp_path, 'wb'),
                stderr=subprocess.PIPE,
                timeout=10
            )
            
            if result.returncode == 0 and os.path.exists(tmp_path):
                img = Image.open(tmp_path)
                os.unlink(tmp_path)
                return img
            
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            print(f"dcraw failed to load {file_path}: {e}")
        
        return None
    
    # Fallback: try PIL anyway
    try:
        return Image.open(file_path)
    except Exception as e:
        print(f"All methods failed to load {file_path}: {e}")
        return None


class MediaProcessorApp:
    """Main application window for media processing."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Media Processor")
        self.root.geometry("1200x800")
        
        # Config file path
        self.config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'media_processor_config.yaml'
        )
        
        # State
        self.current_directory = os.path.expanduser("~")
        self.selected_files: List[str] = []
        self.all_files: List[str] = []
        self.current_preview_image = None
        self._updating_filter = False  # Flag to prevent recursive updates
        
        # Preview state
        self.original_preview_image = None  # Thumbnail PIL Image for default view
        self.full_preview_image = None  # Full resolution PIL Image for zooming
        self.current_preview_file = None  # Path to currently previewed file
        self.preview_rotation = 0  # Current rotation in degrees
        self.preview_zoom = 1.0  # Current zoom level
        
        # Remembered location data
        self.remembered_location = {
            'latitude': None,
            'longitude': None,
            'altitude': None,
            'city': None,
            'state': None,
            'country': None,
            'country_code': None,
            'coverage': None
        }
        
        # Remembered last destination for move operation
        self.last_move_destination = None
        
        # Setup UI
        self.setup_ui()
        
        # Load configuration after UI is set up
        self.load_config()
        
    def setup_ui(self):
        """Setup the user interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights for resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Top bar - Directory selection
        self.setup_top_bar(main_frame)
        
        # Left panel - File browser
        self.setup_file_browser(main_frame)
        
        # Right panel - Preview and info
        self.setup_right_panel(main_frame)
        
        # Bottom bar - Operations
        self.setup_bottom_bar(main_frame)
        
        # Status bar
        self.setup_status_bar(main_frame)
        
    def setup_top_bar(self, parent):
        """Setup the top directory selection bar."""
        top_frame = ttk.Frame(parent)
        top_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        top_frame.columnconfigure(1, weight=1)
        
        ttk.Label(top_frame, text="Directory:").grid(row=0, column=0, padx=(0, 5))
        
        self.dir_var = tk.StringVar(value=self.current_directory)
        dir_entry = ttk.Entry(top_frame, textvariable=self.dir_var, state='readonly')
        dir_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        # Enable drag and drop for directory
        self.enable_drop(dir_entry, self.on_directory_drop)
        
        ttk.Button(top_frame, text="Browse...", command=self.browse_directory).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(top_frame, text="Refresh", command=self.refresh_file_list).grid(row=0, column=3)
        
    def setup_file_browser(self, parent):
        """Setup the left panel file browser."""
        browser_frame = ttk.LabelFrame(parent, text="Files", padding="5")
        browser_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        browser_frame.columnconfigure(0, weight=1)
        browser_frame.rowconfigure(1, weight=1)
        
        # Search/filter bar
        filter_frame = ttk.Frame(browser_frame)
        filter_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        filter_frame.columnconfigure(1, weight=1)
        
        ttk.Label(filter_frame, text="Filter:").grid(row=0, column=0, padx=(0, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', lambda *args: self.apply_filter())
        ttk.Entry(filter_frame, textvariable=self.filter_var).grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        # File type filter
        type_frame = ttk.Frame(browser_frame)
        type_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.show_images_var = tk.BooleanVar(value=True)
        self.show_videos_var = tk.BooleanVar(value=True)
        self.show_other_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(type_frame, text="Images", variable=self.show_images_var, 
                       command=self.apply_filter).grid(row=0, column=0, padx=5)
        ttk.Checkbutton(type_frame, text="Videos", variable=self.show_videos_var,
                       command=self.apply_filter).grid(row=0, column=1, padx=5)
        ttk.Checkbutton(type_frame, text="Other", variable=self.show_other_var,
                       command=self.apply_filter).grid(row=0, column=2, padx=5)
        
        # Subdirectory options
        subdir_frame = ttk.Frame(browser_frame)
        subdir_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.include_subdirs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(subdir_frame, text="Include subdirectories", 
                       variable=self.include_subdirs_var,
                       command=self.refresh_file_list).grid(row=0, column=0, padx=5)
        
        ttk.Label(subdir_frame, text="Depth:").grid(row=0, column=1, padx=(10, 5))
        self.subdir_depth_var = tk.StringVar(value="1")
        depth_spinbox = ttk.Spinbox(subdir_frame, textvariable=self.subdir_depth_var, 
                                    from_=1, to=10, width=5,
                                    command=self.on_depth_change)
        depth_spinbox.grid(row=0, column=2)
        depth_spinbox.bind('<Return>', lambda e: self.on_depth_change())
        
        # File list with scrollbar
        list_frame = ttk.Frame(browser_frame)
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                       selectmode=tk.EXTENDED, width=40, height=25)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)
        
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        
        # Selection buttons
        selection_btn_frame = ttk.Frame(browser_frame)
        selection_btn_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        ttk.Button(selection_btn_frame, text="Select All", command=self.select_all_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(selection_btn_frame, text="Clear Selection", command=self.clear_selection).pack(side=tk.LEFT)
        
        # Selection info
        self.selection_label = ttk.Label(browser_frame, text="Selected: 0 files")
        self.selection_label.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
    def setup_right_panel(self, parent):
        """Setup the right panel with preview and info."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # Preview area
        preview_frame = ttk.LabelFrame(right_frame, text="Preview", padding="5")
        preview_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        
        # Preview controls (at top so they don't move)
        preview_controls = ttk.Frame(preview_frame)
        preview_controls.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Zoom controls
        ttk.Label(preview_controls, text="Zoom:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(preview_controls, text="-", command=self.zoom_out, width=3).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(preview_controls, text="+", command=self.zoom_in, width=3).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(preview_controls, text="Fit", command=self.zoom_fit, width=5).pack(side=tk.LEFT, padx=(0, 10))
        
        # Rotate controls
        ttk.Label(preview_controls, text="Rotate:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(preview_controls, text="↶ 90°", command=self.rotate_left, width=6).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(preview_controls, text="↷ 90°", command=self.rotate_right, width=6).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(preview_controls, text="↻ 180°", command=self.rotate_180, width=6).pack(side=tk.LEFT)
        
        # Preview label (below controls)
        self.preview_label = ttk.Label(preview_frame, text="No file selected", 
                                       background='gray85', anchor=tk.CENTER)
        self.preview_label.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Info area
        info_frame = ttk.LabelFrame(right_frame, text="File Information", padding="5")
        info_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)
        
        # EXIF filter controls
        exif_control_frame = ttk.Frame(info_frame)
        exif_control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(exif_control_frame, text="EXIF Display:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.exif_filter_var = tk.StringVar(value="All")
        exif_filter_options = ["All", "Common", "GPS/Location", "Camera", "Keywords", "Video"]
        exif_dropdown = ttk.Combobox(exif_control_frame, textvariable=self.exif_filter_var, 
                                     values=exif_filter_options, state='readonly', width=15)
        exif_dropdown.pack(side=tk.LEFT, padx=(0, 5))
        
        # Show Location button
        self.show_location_btn = ttk.Button(exif_control_frame, text="Show Location", 
                                           command=self.show_location, state='disabled')
        self.show_location_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Remember Location button
        self.remember_location_btn = ttk.Button(exif_control_frame, text="Remember Location", 
                                               command=self.remember_location, state='disabled')
        self.remember_location_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Use trace on StringVar for more reliable updates
        self.exif_filter_var.trace('w', lambda *args: self.on_exif_filter_change())
        
        # Scrollable text widget for info
        info_scroll = ttk.Scrollbar(info_frame, orient=tk.VERTICAL)
        info_scroll.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        self.info_text = tk.Text(info_frame, wrap=tk.WORD, yscrollcommand=info_scroll.set,
                                height=20, width=50)
        self.info_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        info_scroll.config(command=self.info_text.yview)
        
    def setup_bottom_bar(self, parent):
        """Setup the bottom operations bar."""
        ops_frame = ttk.LabelFrame(parent, text="Bulk Operations", padding="10")
        ops_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 5))
        
        # Database path
        db_frame = ttk.Frame(ops_frame)
        db_frame.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        db_frame.columnconfigure(1, weight=1)
        
        ttk.Label(db_frame, text="Database:").grid(row=0, column=0, padx=(0, 5))
        self.db_path_var = tk.StringVar()
        db_entry = ttk.Entry(db_frame, textvariable=self.db_path_var)
        db_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        # Enable drag and drop for database
        self.enable_drop(db_entry, self.on_database_drop)
        
        ttk.Button(db_frame, text="Browse...", command=self.browse_database).grid(row=0, column=2)
        
        # Volume filter
        ttk.Label(db_frame, text="Volume Filter:").grid(row=0, column=3, padx=(10, 5))
        self.volume_filter_var = tk.StringVar()
        volume_entry = ttk.Entry(db_frame, textvariable=self.volume_filter_var, width=20)
        volume_entry.grid(row=0, column=4, sticky=(tk.W, tk.E), padx=(0, 5))
        
        # Add trace to update info when volume filter changes
        self.volume_filter_var.trace('w', lambda *args: self.on_volume_filter_change())
        
        # Operation buttons
        btn_frame = ttk.Frame(ops_frame)
        btn_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E))
        
        ttk.Button(btn_frame, text="Index Media Files", command=self.index_media).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Move Media Files", command=self.move_media).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="Manage Duplicates", command=self.manage_duplicates).grid(row=0, column=2, padx=5)
        ttk.Button(btn_frame, text="Locate in Database", command=self.locate_in_db).grid(row=0, column=3, padx=5)
        ttk.Button(btn_frame, text="Apply EXIF", command=self.apply_exif).grid(row=0, column=4, padx=5)
        ttk.Button(btn_frame, text="Delete Files", command=self.delete_files).grid(row=0, column=5, padx=5)
        
    def setup_status_bar(self, parent):
        """Setup the status bar at the bottom."""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        # Add save config button
        ttk.Button(status_frame, text="Save Settings", command=self.save_config).grid(row=0, column=1)
        
    def enable_drop(self, widget, callback):
        """Enable drag and drop on a widget."""
        if TKDND_AVAILABLE:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', callback)
        else:
            # Fallback: just show a tooltip
            widget.bind('<Button-3>', lambda e: messagebox.showinfo(
                "Drag and Drop", 
                "Install tkinterdnd2 for drag and drop support:\npip install tkinterdnd2"
            ))
    
    def on_directory_drop(self, event):
        """Handle directory drop event."""
        if TKDND_AVAILABLE:
            # Parse the dropped path
            path = event.data
            # Remove curly braces if present (Windows)
            if path.startswith('{') and path.endswith('}'):
                path = path[1:-1]
            # Handle multiple files - take first one
            if ' ' in path and not os.path.exists(path):
                path = path.split()[0]
            
            # If it's a file, get its directory
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            if os.path.isdir(path):
                self.current_directory = path
                self.dir_var.set(path)
                self.refresh_file_list()
    
    def on_database_drop(self, event):
        """Handle database file drop event."""
        if TKDND_AVAILABLE:
            # Parse the dropped path
            path = event.data
            # Remove curly braces if present (Windows)
            if path.startswith('{') and path.endswith('}'):
                path = path[1:-1]
            # Handle multiple files - take first one
            if ' ' in path and not os.path.exists(path):
                path = path.split()[0]
            
            # Only accept .db files
            if os.path.isfile(path) and path.lower().endswith('.db'):
                self.db_path_var.set(path)
            elif os.path.isfile(path):
                messagebox.showwarning("Invalid File", "Please drop a .db database file")
    
    def browse_directory(self):
        """Open directory browser dialog."""
        directory = filedialog.askdirectory(initialdir=self.current_directory,
                                           title="Select Directory")
        if directory:
            self.current_directory = directory
            self.dir_var.set(directory)
            self.refresh_file_list()
            
    def browse_database(self):
        """Open database file browser dialog."""
        db_path = filedialog.askopenfilename(
            title="Select Database File",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
            initialdir=self.current_directory
        )
        if db_path:
            self.db_path_var.set(db_path)
    
    def load_config(self):
        """Load configuration from YAML file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f)
                    
                if config:
                    # Load directory
                    if 'current_directory' in config:
                        directory = config['current_directory']
                        if os.path.exists(directory):
                            self.current_directory = directory
                            self.dir_var.set(directory)
                            # Load files in background
                            threading.Thread(target=self.refresh_file_list, daemon=True).start()
                    
                    # Load database path
                    if 'database_path' in config:
                        db_path = config['database_path']
                        if os.path.exists(db_path):
                            self.db_path_var.set(db_path)
                    
                    # Load volume filter
                    if 'volume_filter' in config:
                        self.volume_filter_var.set(config['volume_filter'])
                    
                    # Load filter settings
                    if 'show_images' in config:
                        self.show_images_var.set(config['show_images'])
                    if 'show_videos' in config:
                        self.show_videos_var.set(config['show_videos'])
                    if 'show_other' in config:
                        self.show_other_var.set(config['show_other'])
                    
                    # Load window geometry
                    if 'window_geometry' in config:
                        self.root.geometry(config['window_geometry'])
                    
                    # Load EXIF filter preference
                    if 'exif_filter' in config:
                        exif_filter = config['exif_filter']
                        if exif_filter in ["All", "Common", "GPS/Location", "Camera", "Keywords", "Video"]:
                            self.exif_filter_var.set(exif_filter)
                    
                    # Load last move destination
                    if 'last_move_destination' in config:
                        dest = config['last_move_destination']
                        if dest and os.path.exists(dest):
                            self.last_move_destination = dest
                    
                    # Load subdirectory settings
                    if 'include_subdirs' in config:
                        self.include_subdirs_var.set(config['include_subdirs'])
                    if 'subdir_depth' in config:
                        self.subdir_depth_var.set(config['subdir_depth'])
                    
                    self.status_var.set("Settings loaded")
        except Exception as e:
            print(f"Error loading config: {e}")
            self.status_var.set("Error loading settings")
    
    def save_config(self, silent=False):
        """Save configuration to YAML file.
        
        Args:
            silent: If True, don't show success messagebox (default: False)
        """
        try:
            config = {
                'current_directory': self.current_directory,
                'database_path': self.db_path_var.get(),
                'volume_filter': self.volume_filter_var.get(),
                'exif_filter': self.exif_filter_var.get(),
                'show_images': self.show_images_var.get(),
                'show_videos': self.show_videos_var.get(),
                'show_other': self.show_other_var.get(),
                'window_geometry': self.root.geometry(),
                'last_move_destination': self.last_move_destination,
                'include_subdirs': self.include_subdirs_var.get(),
                'subdir_depth': self.subdir_depth_var.get(),
            }
            
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            self.status_var.set("Settings saved")
            if not silent:
                messagebox.showinfo("Settings Saved", "Settings have been saved successfully!")
        except Exception as e:
            error_msg = f"Error saving config: {e}"
            print(error_msg)
            self.status_var.set("Error saving settings")
            if not silent:
                messagebox.showerror("Save Error", error_msg)
            
    def refresh_file_list(self):
        """Refresh the file list from the current directory."""
        self.status_var.set("Loading files...")
        self.file_listbox.delete(0, tk.END)
        self.all_files = []
        
        try:
            include_subdirs = self.include_subdirs_var.get()
            max_depth = int(self.subdir_depth_var.get()) if include_subdirs else 0
            max_files = 1000
            
            # Get all files in directory and optionally subdirectories
            base_depth = self.current_directory.rstrip(os.sep).count(os.sep)
            
            for root, dirs, files in os.walk(self.current_directory):
                # Calculate current depth relative to base directory
                current_depth = root.count(os.sep) - base_depth
                
                # If not including subdirs, only process the root directory
                if not include_subdirs and current_depth > 0:
                    break
                
                # If including subdirs, respect the depth limit
                if include_subdirs and current_depth >= max_depth:
                    # Don't descend further
                    dirs[:] = []
                
                for file in files:
                    if len(self.all_files) >= max_files:
                        self.status_var.set(f"Loaded {len(self.all_files)} files (limit reached)")
                        messagebox.showwarning("File Limit", 
                                             f"Reached maximum of {max_files} files. "
                                             "Some files may not be shown.")
                        break
                    
                    file_path = os.path.join(root, file)
                    self.all_files.append(file_path)
                
                if len(self.all_files) >= max_files:
                    break
            
            self.apply_filter()
            depth_info = f" (depth {max_depth})" if include_subdirs else ""
            self.status_var.set(f"Loaded {len(self.all_files)} files{depth_info}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load files: {e}")
            self.status_var.set("Error loading files")
            
    def apply_filter(self):
        """Apply current filter to file list."""
        self.file_listbox.delete(0, tk.END)
        filter_text = self.filter_var.get().lower()
        
        for file_path in self.all_files:
            # Check filename filter
            if filter_text and filter_text not in os.path.basename(file_path).lower():
                continue
                
            # Check file type filter
            mime_type = get_mime_type(file_path)
            extension = os.path.splitext(file_path)[1].lower()
            
            # Consider HEIF and RAW as images
            is_image = (is_image_file(mime_type, extension) or 
                       is_heif_file(file_path) or 
                       is_raw_file(file_path))
            is_video = is_video_file(mime_type)
            
            if is_image and not self.show_images_var.get():
                continue
            if is_video and not self.show_videos_var.get():
                continue
            if not is_image and not is_video and not self.show_other_var.get():
                continue
                
            # Show relative path for cleaner display
            rel_path = os.path.relpath(file_path, self.current_directory)
            self.file_listbox.insert(tk.END, rel_path)
            
    def on_file_select(self, event):
        """Handle file selection in the listbox."""
        selection = self.file_listbox.curselection()
        self.selected_files = [
            os.path.join(self.current_directory, self.file_listbox.get(i))
            for i in selection
        ]
        
        # Update selection count
        self.selection_label.config(text=f"Selected: {len(self.selected_files)} files")
        
        # If single file selected, show preview and info
        if len(self.selected_files) == 1:
            self.show_file_preview(self.selected_files[0])
            self.show_file_info(self.selected_files[0])
        else:
            self.preview_label.config(image='', text=f"{len(self.selected_files)} files selected")
            self.current_preview_image = None
            # Disable Show Location and Remember Location buttons when no single file selected
            self.show_location_btn.config(state='disabled')
            self.remember_location_btn.config(state='disabled')
            if len(self.selected_files) > 1:
                self.show_multiple_files_info()
            else:
                self.info_text.delete(1.0, tk.END)
    
    def select_all_files(self):
        """Select all files in the listbox."""
        self.file_listbox.select_set(0, tk.END)
        # Manually trigger the selection event
        self.file_listbox.event_generate('<<ListboxSelect>>')
    
    def clear_selection(self):
        """Clear all file selections."""
        self.file_listbox.selection_clear(0, tk.END)
        # Manually trigger the selection event
        self.file_listbox.event_generate('<<ListboxSelect>>')
    
    def on_depth_change(self):
        """Handle depth spinbox change."""
        if self.include_subdirs_var.get():
            self.refresh_file_list()
                
    def check_file_in_database(self, file_path, volume_filter=None):
        """Check if file exists in database and return status info.
        
        Args:
            file_path: Path to file
            volume_filter: Optional volume name to filter by
            
        Returns:
            Dictionary with keys:
            - exists: bool - File exists in database
            - volume: str - Volume name if exists
            - in_volume: bool - True if exists in specified volume
            - file_id: int - Database ID if exists
        """
        db_path = self.db_path_var.get()
        if not db_path or not os.path.exists(db_path):
            return {'exists': False, 'volume': None, 'in_volume': False, 'file_id': None}
            
        try:
            import sqlite3
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get absolute path for comparison
            abs_path = os.path.abspath(file_path)
            
            # Query for file
            cursor.execute("""
                SELECT id, volume
                FROM files
                WHERE fullpath = ?
            """, (abs_path,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                file_id, volume = result
                in_volume = (volume == volume_filter) if volume_filter else True
                return {
                    'exists': True,
                    'volume': volume,
                    'in_volume': in_volume,
                    'file_id': file_id
                }
            
            return {'exists': False, 'volume': None, 'in_volume': False, 'file_id': None}
            
        except Exception as e:
            print(f"Database check failed: {e}")
            return {'exists': False, 'volume': None, 'in_volume': False, 'file_id': None}
    
    def get_thumbnail_from_database(self, file_path):
        """Get thumbnail from database if file is indexed.
        
        Returns PIL Image object or None if not found.
        """
        db_path = self.db_path_var.get()
        if not db_path or not os.path.exists(db_path):
            return None
            
        try:
            import sqlite3
            import io
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get absolute path for comparison
            abs_path = os.path.abspath(file_path)
            
            # Query for thumbnail
            cursor.execute("""
                SELECT t.thumbnail_data 
                FROM thumbnails t
                JOIN files f ON t.file_id = f.id
                WHERE f.fullpath = ?
            """, (abs_path,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                # Convert bytes to PIL Image
                thumbnail_bytes = result[0]
                img = Image.open(io.BytesIO(thumbnail_bytes))
                return img
            
            return None
            
        except Exception as e:
            # Silently fail - will fall back to loading from file
            print(f"Database thumbnail lookup failed: {e}")
            return None
    
    def show_file_preview(self, file_path):
        """Show preview of the selected file."""
        # Reset zoom and rotation for new file
        self.preview_rotation = 0
        self.preview_zoom = 1.0
        self.current_preview_file = file_path
        
        mime_type = get_mime_type(file_path)
        extension = os.path.splitext(file_path)[1].lower()
        
        # Check if it's an image (including HEIF and RAW)
        is_image = (is_image_file(mime_type, extension) or 
                   is_heif_file(file_path) or 
                   is_raw_file(file_path))
        
        if is_image:
            try:
                # First, try to get thumbnail from database (fast!)
                thumbnail_img = self.get_thumbnail_from_database(file_path)
                
                if thumbnail_img is None:
                    # Not in database, load from file and create thumbnail
                    # Show loading message for RAW/HEIF files (they can be slow)
                    if is_raw_file(file_path) or is_heif_file(file_path):
                        format_name = "RAW" if is_raw_file(file_path) else "HEIF/HEIC"
                        self.preview_label.config(image='', text=f"Loading {format_name} preview...")
                        self.root.update()
                    
                    # Load full image with fallback support for HEIC/HEIF/RAW
                    full_img = load_image_with_fallback(file_path)
                    
                    if full_img is None:
                        # Failed to load
                        format_name = "RAW" if is_raw_file(file_path) else "HEIF/HEIC" if is_heif_file(file_path) else "image"
                        self.preview_label.config(
                            image='', 
                            text=f"Preview unavailable\n({format_name} format)\n\nTry installing:\n" +
                                 ("pillow_heif" if is_heif_file(file_path) else "rawpy or ImageMagick")
                        )
                        self.current_preview_image = None
                        self.original_preview_image = None
                        self.full_preview_image = None
                        return
                    
                    # Create thumbnail from full image
                    thumbnail_img = full_img.copy()
                    thumbnail_img.thumbnail((500, 400), Image.Resampling.LANCZOS)
                    
                    # Store full image for zooming (don't store if it's huge to save memory)
                    if full_img.size[0] * full_img.size[1] < 50000000:  # < 50 megapixels
                        self.full_preview_image = full_img
                    else:
                        self.full_preview_image = None
                else:
                    # Got thumbnail from database, full image not loaded yet
                    self.full_preview_image = None
                
                # Store thumbnail for default view
                self.original_preview_image = thumbnail_img
                
                # Apply current transformations and display
                self._update_preview_display()
                
            except Exception as e:
                self.preview_label.config(image='', text=f"Preview error: {e}")
                self.current_preview_image = None
                self.original_preview_image = None
                self.full_preview_image = None
        elif is_video_file(mime_type):
            self.preview_label.config(image='', text="Video file\n(Preview not available)")
            self.current_preview_image = None
            self.original_preview_image = None
            self.full_preview_image = None
        else:
            self.preview_label.config(image='', text="No preview available")
            self.current_preview_image = None
            self.original_preview_image = None
            self.full_preview_image = None
    
    def _update_preview_display(self):
        """Update preview display with current zoom and rotation."""
        if self.original_preview_image is None:
            return
        
        try:
            # Decide which image to use based on zoom level
            if self.preview_zoom == 1.0:
                # Default view: use thumbnail as-is
                img = self.original_preview_image.copy()
            else:
                # Zoomed view: use full image if available, otherwise zoom the thumbnail
                if self.full_preview_image is not None:
                    img = self.full_preview_image.copy()
                else:
                    # Full image not available, try to load it now if zooming
                    if self.current_preview_file and os.path.exists(self.current_preview_file):
                        try:
                            full_img = load_image_with_fallback(self.current_preview_file)
                            if full_img and full_img.size[0] * full_img.size[1] < 50000000:
                                self.full_preview_image = full_img
                                img = full_img.copy()
                            else:
                                # Too large or failed to load, use thumbnail
                                img = self.original_preview_image.copy()
                        except:
                            # Failed to load, use thumbnail
                            img = self.original_preview_image.copy()
                    else:
                        # No file path, use thumbnail
                        img = self.original_preview_image.copy()
            
            # Apply rotation
            if self.preview_rotation != 0:
                img = img.rotate(-self.preview_rotation, expand=True)
            
            # Calculate display size
            max_width, max_height = 500, 400
            
            if self.preview_zoom == 1.0:
                # Fit mode: image is already thumbnailed, just display it
                display_img = img
            else:
                # Zoomed mode: calculate size based on zoom
                img_width, img_height = img.size
                width_ratio = max_width / img_width
                height_ratio = max_height / img_height
                fit_ratio = min(width_ratio, height_ratio)
                
                # Apply zoom to the fit ratio
                final_ratio = fit_ratio * self.preview_zoom
                
                # Calculate final dimensions
                new_width = int(img_width * final_ratio)
                new_height = int(img_height * final_ratio)
                
                # Resize image (use LANCZOS for quality)
                if new_width > 0 and new_height > 0:
                    display_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    display_img = img
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(display_img)
            self.current_preview_image = photo  # Keep reference
            
            self.preview_label.config(image=photo, text='')
        except Exception as e:
            self.preview_label.config(image='', text=f"Preview error: {e}")
    
    def zoom_in(self):
        """Zoom in on preview."""
        if self.original_preview_image:
            self.preview_zoom = min(self.preview_zoom * 1.25, 5.0)  # Max 5x zoom
            self._update_preview_display()
    
    def zoom_out(self):
        """Zoom out on preview."""
        if self.original_preview_image:
            self.preview_zoom = max(self.preview_zoom / 1.25, 0.25)  # Min 0.25x zoom
            self._update_preview_display()
    
    def zoom_fit(self):
        """Reset zoom to fit."""
        if self.original_preview_image:
            self.preview_zoom = 1.0
            self._update_preview_display()
    
    def rotate_left(self):
        """Rotate preview 90 degrees counter-clockwise."""
        if self.original_preview_image:
            self.preview_rotation = (self.preview_rotation - 90) % 360
            self._update_preview_display()
    
    def rotate_right(self):
        """Rotate preview 90 degrees clockwise."""
        if self.original_preview_image:
            self.preview_rotation = (self.preview_rotation + 90) % 360
            self._update_preview_display()
    
    def rotate_180(self):
        """Rotate preview 180 degrees."""
        if self.original_preview_image:
            self.preview_rotation = (self.preview_rotation + 180) % 360
            self._update_preview_display()
            
    def show_file_info(self, file_path):
        """Show file information and EXIF data."""
        # Clear info panel ONCE at the start
        self.info_text.delete('1.0', tk.END)
        
        try:
            # Get basic file info
            stat = os.stat(file_path)
            
            # Check database status
            volume_filter = self.volume_filter_var.get().strip() or None
            db_status = self.check_file_in_database(file_path, volume_filter)
            
            # Get EXIF data using exiftool with current filter
            filter_mode = self.exif_filter_var.get()
            exif_data = self.get_exif_data(file_path, filter_mode)
            
            # Now build the complete display
            self.info_text.insert(tk.END, f"File: {os.path.basename(file_path)}\n")
            self.info_text.insert(tk.END, f"Path: {file_path}\n")
            self.info_text.insert(tk.END, f"Size: {self.format_size(stat.st_size)}\n")
            self.info_text.insert(tk.END, f"Modified: {self.format_time(stat.st_mtime)}\n")
            
            # Database status section
            self.info_text.insert(tk.END, "\n--- Database Status ---\n")
            if db_status['exists']:
                self.info_text.insert(tk.END, "✓ Indexed in database\n", 'db_indexed')
                self.info_text.insert(tk.END, f"  Volume: {db_status['volume']}\n")
                self.info_text.insert(tk.END, f"  File ID: {db_status['file_id']}\n")
                
                if volume_filter:
                    if db_status['in_volume']:
                        self.info_text.insert(tk.END, f"✓ Exists in volume '{volume_filter}'\n", 'volume_match')
                    else:
                        self.info_text.insert(tk.END, f"✗ NOT in volume '{volume_filter}'\n", 'volume_mismatch')
            else:
                self.info_text.insert(tk.END, "✗ NOT in database\n", 'db_not_indexed')
            
            # EXIF section
            if filter_mode == "GPS/Location":
                self.info_text.insert(tk.END, "\n--- GPS/Location Data ---\n")
            elif filter_mode == "Camera":
                self.info_text.insert(tk.END, "\n--- Camera Settings ---\n")
            elif filter_mode == "Keywords":
                self.info_text.insert(tk.END, "\n--- Keywords & Captions ---\n")
            elif filter_mode == "Video":
                self.info_text.insert(tk.END, "\n--- Video Metadata ---\n")
            else:
                self.info_text.insert(tk.END, "\n--- EXIF Data ---\n")
            
            if exif_data and len(exif_data) > 0:
                for key, value in exif_data.items():
                    # Skip SourceFile which might still be in filtered results
                    if key == 'SourceFile':
                        continue
                    self.info_text.insert(tk.END, f"{key}: {value}\n")
            else:
                self.info_text.insert(tk.END, f"No {filter_mode.lower()} data found\n")
            
            # Configure tags for colored text (do this once at the end)
            self.info_text.tag_config('db_indexed', foreground='green')
            self.info_text.tag_config('db_not_indexed', foreground='red')
            self.info_text.tag_config('volume_match', foreground='green')
            self.info_text.tag_config('volume_mismatch', foreground='orange')
            
            # Enable/disable Show Location and Remember Location buttons based on GPS data
            gps_data = self.get_gps_coordinates(file_path)
            if gps_data:
                self.show_location_btn.config(state='normal')
                self.remember_location_btn.config(state='normal')
            else:
                self.show_location_btn.config(state='disabled')
                self.remember_location_btn.config(state='disabled')
                
        except Exception as e:
            self.info_text.insert(tk.END, f"\nError loading info: {e}\n")
            self.show_location_btn.config(state='disabled')
            self.remember_location_btn.config(state='disabled')
            
    def on_volume_filter_change(self):
        """Handle volume filter change - refresh info if file is selected."""
        # Guard against early initialization calls
        if not hasattr(self, 'selected_files') or not hasattr(self, 'file_listbox'):
            return
        
        # Prevent recursive calls
        if self._updating_filter:
            return
        
        # Skip if no files selected
        if not self.selected_files:
            return
        
        self._updating_filter = True
        try:
            # Refresh display based on selection
            if len(self.selected_files) == 1:
                self.show_file_info(self.selected_files[0])
            elif len(self.selected_files) > 1:
                self.show_multiple_files_info()
        finally:
            self._updating_filter = False
    
    def show_multiple_files_info(self):
        """Show summary info for multiple selected files."""
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, f"Selected {len(self.selected_files)} files\n\n")
        
        # Calculate total size and categorize files
        total_size = 0
        image_count = 0
        raw_count = 0
        heif_count = 0
        video_count = 0
        other_count = 0
        
        # Database stats
        in_db_count = 0
        not_in_db_count = 0
        in_volume_count = 0
        not_in_volume_count = 0
        volume_filter = self.volume_filter_var.get().strip() or None
        
        for file_path in self.selected_files:
            try:
                stat = os.stat(file_path)
                total_size += stat.st_size
                
                mime_type = get_mime_type(file_path)
                extension = os.path.splitext(file_path)[1].lower()
                
                if is_raw_file(file_path):
                    raw_count += 1
                elif is_heif_file(file_path):
                    heif_count += 1
                elif is_image_file(mime_type, extension):
                    image_count += 1
                elif is_video_file(mime_type):
                    video_count += 1
                else:
                    other_count += 1
                
                # Check database status
                db_status = self.check_file_in_database(file_path, volume_filter)
                if db_status['exists']:
                    in_db_count += 1
                    if volume_filter:
                        if db_status['in_volume']:
                            in_volume_count += 1
                        else:
                            not_in_volume_count += 1
                else:
                    not_in_db_count += 1
                    
            except Exception:
                pass
        
        # File type summary
        self.info_text.insert(tk.END, "--- File Types ---\n")
        self.info_text.insert(tk.END, f"Images: {image_count}\n")
        if heif_count > 0:
            self.info_text.insert(tk.END, f"HEIF/HEIC: {heif_count}\n")
        if raw_count > 0:
            self.info_text.insert(tk.END, f"RAW: {raw_count}\n")
        self.info_text.insert(tk.END, f"Videos: {video_count}\n")
        if other_count > 0:
            self.info_text.insert(tk.END, f"Other: {other_count}\n")
        self.info_text.insert(tk.END, f"\nTotal size: {self.format_size(total_size)}\n")
        
        # Database summary
        self.info_text.insert(tk.END, "\n--- Database Status ---\n")
        self.info_text.insert(tk.END, f"✓ In database: {in_db_count}\n", 'db_indexed' if in_db_count > 0 else None)
        self.info_text.insert(tk.END, f"✗ Not in database: {not_in_db_count}\n", 'db_not_indexed' if not_in_db_count > 0 else None)
        
        if volume_filter:
            self.info_text.insert(tk.END, f"\nVolume '{volume_filter}':\n")
            self.info_text.insert(tk.END, f"  ✓ In volume: {in_volume_count}\n", 'volume_match' if in_volume_count > 0 else None)
            self.info_text.insert(tk.END, f"  ✗ Not in volume: {not_in_volume_count}\n", 'volume_mismatch' if not_in_volume_count > 0 else None)
        
        # Configure tags
        self.info_text.tag_config('db_indexed', foreground='green')
        self.info_text.tag_config('db_not_indexed', foreground='red')
        self.info_text.tag_config('volume_match', foreground='green')
        self.info_text.tag_config('volume_mismatch', foreground='orange')
        
    def get_exif_data(self, file_path, filter_mode="All") -> Optional[Dict[str, Any]]:
        """Get EXIF data for a file using exiftool with optional filtering.
        
        Args:
            file_path: Path to file
            filter_mode: One of "All", "Common", "GPS/Location", "Camera", "Keywords", "Video"
        
        Returns:
            Dictionary of EXIF data
        """
        try:
            # Build exiftool command based on filter mode
            cmd = ['exiftool', '-json']
            
            if filter_mode == "Common":
                # Common tags
                tags = ['FileName', 'FileSize', 'FileType', 'MIMEType',
                       'ImageWidth', 'ImageHeight', 'Make', 'Model',
                       'DateTimeOriginal', 'CreateDate', 'ModifyDate',
                       'ISO', 'FNumber', 'ExposureTime', 'FocalLength',
                       'LensModel', 'Orientation']
                for tag in tags:
                    cmd.append(f'-{tag}')
                    
            elif filter_mode == "GPS/Location":
                # GPS and location tags
                cmd.extend(['-a', '-GPS:all', '-XMP-photoshop:City', '-XMP-photoshop:State',
                           '-XMP-photoshop:Country', '-XMP-iptcExt:LocationShown*',
                           '-XMP-dc:Coverage'])
                           
            elif filter_mode == "Camera":
                # Camera settings
                tags = ['Make', 'Model', 'LensModel', 'LensInfo',
                       'ISO', 'FNumber', 'ExposureTime', 'FocalLength',
                       'FocalLengthIn35mmFormat', 'WhiteBalance', 'Flash',
                       'ExposureProgram', 'MeteringMode', 'ExposureCompensation']
                for tag in tags:
                    cmd.append(f'-{tag}')
                    
            elif filter_mode == "Keywords":
                # Keywords and captions
                cmd.extend(['-a', '-Keywords', '-Subject', '-XMP-dc:Subject',
                           '-IPTC:Keywords', '-Caption-Abstract', '-ImageDescription',
                           '-XMP-dc:Description', '-XMP-dc:Title'])
                           
            elif filter_mode == "Video":
                # Video metadata
                tags = ['ImageWidth', 'ImageHeight', 'Duration', 'VideoFrameRate',
                       'VideoCodec', 'AudioChannels', 'AudioBitrate', 'AudioCodec',
                       'CompressorName', 'BitDepth', 'ColorSpace']
                for tag in tags:
                    cmd.append(f'-{tag}')
            else:
                # All tags (default)
                cmd.append('-a')
            
            cmd.append(file_path)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                if data and isinstance(data, list) and len(data) > 0:
                    exif_data = data[0]
                    
                    # For "All" mode, filter out some verbose fields
                    if filter_mode == "All":
                        filtered = {k: v for k, v in exif_data.items() 
                                  if not k.startswith('SourceFile') and
                                     not k.startswith('ExifTool') and
                                     not k.startswith('File') or
                                     k in ['FileName', 'FileSize', 'FileType', 'MIMEType']}
                        return filtered
                    else:
                        # For filtered modes, return all retrieved data
                        return exif_data
        except Exception as e:
            print(f"Error getting EXIF data: {e}")
            
        return None
    
    def on_exif_filter_change(self):
        """Handle EXIF filter change - refresh info if file is selected."""
        # Guard against early initialization calls
        if not hasattr(self, 'selected_files') or not hasattr(self, 'file_listbox'):
            return
        
        # Prevent recursive calls
        if self._updating_filter:
            return
        
        # Skip if no files selected
        if not self.selected_files:
            return
        
        # Save current listbox selection indices
        current_selection = list(self.file_listbox.curselection())
        
        # If there was a selection, reselect it to trigger refresh with new filter
        if current_selection:
            self._updating_filter = True
            try:
                # Just call show_file_info directly - don't mess with selection
                if len(self.selected_files) == 1:
                    self.show_file_info(self.selected_files[0])
                # No need to update for multiple files as they don't show EXIF
                
                # Use after_idle to restore selection after all events have processed
                self.root.after_idle(lambda: self._restore_selection(current_selection))
            finally:
                self._updating_filter = False
    
    def _restore_selection(self, indices):
        """Restore listbox selection after filter change."""
        if not self.file_listbox.curselection():
            for idx in indices:
                self.file_listbox.selection_set(idx)
            
            # Manually trigger the selection event to redisplay preview/info
            self.file_listbox.event_generate('<<ListboxSelect>>')
    
    def get_full_location_data(self, file_path):
        """Extract complete location data from a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with location data or None if no GPS data
        """
        try:
            # Use exiftool to get GPS and location data
            result = subprocess.run(
                ['exiftool', '-GPSLatitude', '-GPSLongitude', '-GPSLatitudeRef', 
                 '-GPSLongitudeRef', '-GPSAltitude', '-City', '-State', '-Country',
                 '-CountryCode', '-Coverage', '-json', file_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    exif = data[0]
                    
                    # Check if GPS data exists
                    if 'GPSLatitude' in exif and 'GPSLongitude' in exif:
                        lat = exif['GPSLatitude']
                        lon = exif['GPSLongitude']
                        lat_ref = exif.get('GPSLatitudeRef', 'N')
                        lon_ref = exif.get('GPSLongitudeRef', 'E')
                        
                        # Normalize reference to single letter
                        lat_ref = lat_ref[0].upper() if lat_ref else 'N'
                        lon_ref = lon_ref[0].upper() if lon_ref else 'E'
                        
                        # Convert to decimal if needed, always applying reference
                        if isinstance(lat, str):
                            lat = self._parse_gps_coordinate(lat, lat_ref)
                        else:
                            lat = float(lat)
                            if lat_ref == 'S':
                                lat = -lat
                        
                        if isinstance(lon, str):
                            lon = self._parse_gps_coordinate(lon, lon_ref)
                        else:
                            lon = float(lon)
                            if lon_ref == 'W':
                                lon = -lon
                        
                        # Get altitude if available
                        altitude = exif.get('GPSAltitude')
                        if altitude and isinstance(altitude, str):
                            # Parse altitude like "123.4 m"
                            try:
                                altitude = float(altitude.split()[0])
                            except:
                                altitude = None
                        
                        return {
                            'latitude': lat,
                            'longitude': lon,
                            'altitude': altitude,
                            'city': exif.get('City'),
                            'state': exif.get('State'),
                            'country': exif.get('Country'),
                            'country_code': exif.get('CountryCode'),
                            'coverage': exif.get('Coverage')
                        }
        except Exception as e:
            print(f"Error extracting location data: {e}")
        
        return None
    
    def get_gps_coordinates(self, file_path):
        """Extract GPS coordinates from a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Tuple of (latitude, longitude, location_name) or None if no GPS data
        """
        try:
            # Use exiftool to get GPS data
            result = subprocess.run(
                ['exiftool', '-GPSLatitude', '-GPSLongitude', '-GPSLatitudeRef', 
                 '-GPSLongitudeRef', '-City', '-State', '-Country', '-json', file_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    exif = data[0]
                    
                    # Debug: print raw GPS data
                    print(f"DEBUG GPS data: {json.dumps(exif, indent=2)}")
                    
                    # Check if GPS data exists
                    if 'GPSLatitude' in exif and 'GPSLongitude' in exif:
                        lat = exif['GPSLatitude']
                        lon = exif['GPSLongitude']
                        lat_ref = exif.get('GPSLatitudeRef', 'N')
                        lon_ref = exif.get('GPSLongitudeRef', 'E')
                        
                        print(f"DEBUG: Raw lat={lat}, lat_ref={lat_ref}")
                        print(f"DEBUG: Raw lon={lon}, lon_ref={lon_ref}")
                        
                        # Normalize reference to single letter (handle both "N" and "North" formats)
                        lat_ref = lat_ref[0].upper() if lat_ref else 'N'
                        lon_ref = lon_ref[0].upper() if lon_ref else 'E'
                        
                        print(f"DEBUG: Normalized lat_ref={lat_ref}, lon_ref={lon_ref}")
                        
                        # Convert to decimal if needed, always applying reference
                        if isinstance(lat, str):
                            # Parse formats like "37 deg 46' 29.99\" N"
                            lat = self._parse_gps_coordinate(lat, lat_ref)
                        else:
                            # Already a number, but still need to apply reference
                            lat = float(lat)
                            if lat_ref == 'S':
                                lat = -lat
                        
                        if isinstance(lon, str):
                            lon = self._parse_gps_coordinate(lon, lon_ref)
                        else:
                            # Already a number, but still need to apply reference
                            lon = float(lon)
                            if lon_ref == 'W':
                                lon = -lon
                        
                        print(f"DEBUG: Final lat={lat}, lon={lon}")
                        
                        # Build location name
                        location_parts = []
                        if 'City' in exif:
                            location_parts.append(exif['City'])
                        if 'State' in exif:
                            location_parts.append(exif['State'])
                        if 'Country' in exif:
                            location_parts.append(exif['Country'])
                        
                        location_name = ', '.join(location_parts) if location_parts else None
                        
                        return (lat, lon, location_name)
        except Exception as e:
            print(f"Error extracting GPS data: {e}")
        
        return None
    
    def _parse_gps_coordinate(self, coord_str, ref):
        """Parse GPS coordinate string to decimal degrees.
        
        Args:
            coord_str: Coordinate string like "37 deg 46' 29.99\" N" or just a number
            ref: Reference (N/S for latitude, E/W for longitude)
            
        Returns:
            Decimal degrees as float
        """
        try:
            # If already a number, just return it
            if isinstance(coord_str, (int, float)):
                decimal = float(coord_str)
            else:
                # Parse "37 deg 46' 29.99\"" format
                parts = coord_str.replace('deg', '').replace("'", '').replace('"', '').split()
                if len(parts) >= 3:
                    degrees = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2])
                    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
                elif len(parts) == 1:
                    decimal = float(parts[0])
                else:
                    return None
            
            # Apply reference (negative for South and West)
            if ref in ['S', 'W']:
                decimal = -decimal
            
            return decimal
        except Exception as e:
            print(f"Error parsing GPS coordinate: {e}")
            return None
    
    def show_location(self):
        """Show location of selected file on a map."""
        if not self.selected_files or len(self.selected_files) != 1:
            messagebox.showinfo("Show Location", "Please select a single file to show its location.")
            return
        
        file_path = self.selected_files[0]
        
        # Get GPS coordinates
        gps_data = self.get_gps_coordinates(file_path)
        
        if not gps_data:
            messagebox.showinfo("No GPS Data", 
                              f"No GPS coordinates found in:\n{os.path.basename(file_path)}")
            return
        
        lat, lon, location_name = gps_data
        
        # Build map URL (using OpenStreetMap)
        map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
        
        # Also provide Google Maps as alternative
        google_url = f"https://www.google.com/maps?q={lat},{lon}"
        
        # Show dialog with options
        location_str = f"\nLocation: {location_name}" if location_name else ""
        message = (f"GPS Coordinates:\n"
                  f"Latitude: {lat:.6f}\n"
                  f"Longitude: {lon:.6f}"
                  f"{location_str}\n\n"
                  f"Opening in web browser...")
        
        # Open in default browser
        import webbrowser
        try:
            webbrowser.open(map_url)
            messagebox.showinfo("Location", message)
        except Exception as e:
            # If opening fails, show the URLs
            messagebox.showinfo("Location", 
                              f"{message}\n\n"
                              f"OpenStreetMap:\n{map_url}\n\n"
                              f"Google Maps:\n{google_url}")
    
    def remember_location(self):
        """Remember the location data from the selected file."""
        if not self.selected_files or len(self.selected_files) != 1:
            messagebox.showinfo("Remember Location", "Please select a single file.")
            return
        
        file_path = self.selected_files[0]
        
        # Get full location data
        location_data = self.get_full_location_data(file_path)
        
        if not location_data:
            messagebox.showinfo("No Location Data", 
                              f"No location data found in:\n{os.path.basename(file_path)}")
            return
        
        # Store the location data
        self.remembered_location = location_data
        
        # Build summary message
        parts = []
        if location_data['latitude'] is not None and location_data['longitude'] is not None:
            parts.append(f"GPS: {location_data['latitude']:.6f}, {location_data['longitude']:.6f}")
        if location_data['altitude'] is not None:
            parts.append(f"Altitude: {location_data['altitude']} m")
        
        location_parts = []
        if location_data['city']:
            location_parts.append(location_data['city'])
        if location_data['state']:
            location_parts.append(location_data['state'])
        if location_data['country']:
            location_parts.append(location_data['country'])
        
        if location_parts:
            parts.append(f"Location: {', '.join(location_parts)}")
        
        if location_data['country_code']:
            parts.append(f"Country Code: {location_data['country_code']}")
        if location_data['coverage']:
            parts.append(f"Coverage: {location_data['coverage']}")
        
        message = "Location data remembered:\n\n" + "\n".join(parts)
        messagebox.showinfo("Location Remembered", message)
        
        # Update status
        self.status_var.set("Location data remembered")
        
    def format_size(self, size_bytes):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
        
    def format_time(self, timestamp):
        """Format timestamp in human-readable format."""
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
        
    # Operation methods
    def check_prerequisites(self, require_db=False, require_selection=True):
        """Check if prerequisites for an operation are met."""
        if require_selection and not self.selected_files:
            messagebox.showwarning("No Selection", "Please select one or more files first.")
            return False
            
        if require_db and not self.db_path_var.get():
            messagebox.showwarning("No Database", "Please specify a database file first.")
            return False
            
        return True
        
    def index_media(self):
        """Launch index media dialog."""
        if not self.check_prerequisites(require_db=True):
            return
            
        IndexMediaDialog(self.root, self.selected_files, self.db_path_var.get())
        
    def move_media(self):
        """Launch move media dialog."""
        if not self.check_prerequisites(require_db=True):
            return
        
        # Get volume from main window filter, or use default
        volume = self.volume_filter_var.get().strip() or "MediaLibrary"
        MoveMediaDialog(self.root, self.selected_files, self.db_path_var.get(), volume, 
                       last_destination=self.last_move_destination, parent_app=self)
        
    def manage_duplicates(self):
        """Launch manage duplicates dialog."""
        if not self.check_prerequisites(require_db=True, require_selection=False):
            return
            
        ManageDuplicatesDialog(self.root, self.current_directory, self.db_path_var.get())
        
    def locate_in_db(self):
        """Launch locate in database dialog."""
        if not self.check_prerequisites(require_db=True):
            return
            
        LocateInDbDialog(self.root, self.selected_files, self.db_path_var.get())
        
    def apply_exif(self):
        """Launch apply EXIF dialog."""
        if not self.check_prerequisites(require_selection=True):
            return
            
        ApplyExifDialog(self.root, self.selected_files, self.db_path_var.get(), 
                       self.remembered_location, parent_app=self)
    
    def delete_files(self):
        """Launch delete files dialog."""
        if not self.check_prerequisites(require_selection=True):
            return
        
        DeleteFilesDialog(self.root, self.selected_files, self.db_path_var.get(), parent_app=self)


class OperationDialogBase(tk.Toplevel):
    """Base class for operation dialogs."""
    
    def __init__(self, parent, title, width=600, height=400):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        
        # Make modal
        self.grab_set()
        
    def add_output_area(self, parent):
        """Add output text area with scrollbar."""
        output_frame = ttk.LabelFrame(parent, text="Output", padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.output_text = tk.Text(output_frame, wrap=tk.WORD, 
                                   yscrollcommand=scrollbar.set, height=15)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.output_text.yview)
        
    def log(self, message):
        """Add message to output area."""
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.update()
    
    def _append_output(self, message):
        """Add message to output area (thread-safe version)."""
        def append():
            self.output_text.insert(tk.END, message)
            self.output_text.see(tk.END)
        # Schedule on main thread
        self.after(0, append)
        
    def run_command_async(self, cmd, on_complete=None):
        """Run a command asynchronously."""
        def run():
            try:
                self.log(f"Running: {' '.join(cmd)}\n")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                for line in process.stdout:
                    self.log(line.rstrip())
                    
                process.wait()
                
                if process.returncode == 0:
                    self.log("\n✓ Operation completed successfully")
                else:
                    self.log(f"\n✗ Operation failed with code {process.returncode}")
                    
                if on_complete:
                    on_complete(process.returncode == 0)
                    
            except Exception as e:
                self.log(f"\n✗ Error: {e}")
                if on_complete:
                    on_complete(False)
                    
        thread = threading.Thread(target=run, daemon=True)
        thread.start()


class IndexMediaDialog(OperationDialogBase):
    """Dialog for indexing media files."""
    
    def __init__(self, parent, files, db_path):
        super().__init__(parent, "Index Media Files", 700, 500)
        
        self.files = files
        self.db_path = db_path
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        ttk.Label(main_frame, text=f"Indexing {len(self.files)} file(s)").pack(anchor=tk.W)
        ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.volume_var = tk.StringVar(value="MediaLibrary")
        ttk.Label(options_frame, text="Volume:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Entry(options_frame, textvariable=self.volume_var, width=30).grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Dry run (preview only)", 
                       variable=self.dry_run_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Output area
        self.add_output_area(main_frame)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
        
    def start(self):
        """Start the indexing operation."""
        # Find index_media.py in parent directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        index_script = os.path.join(script_dir, 'index_media.py')
        
        if not os.path.exists(index_script):
            messagebox.showerror("Error", f"index_media.py not found at {index_script}")
            return
            
        # Get parent directory of files for --path
        if self.files:
            paths = list(set([os.path.dirname(f) for f in self.files]))
            
            # Build command
            cmd = ['python3', index_script]
            
            for path in paths:
                cmd.extend(['--path', path])
                
            cmd.extend(['--volume', self.volume_var.get()])
            cmd.extend(['--db-path', self.db_path])
            cmd.extend(['--verbose', '2'])
            
            if self.dry_run_var.get():
                cmd.append('--dry-run')
                
            self.run_command_async(cmd)


class MoveMediaDialog(OperationDialogBase):
    """Dialog for moving media files."""
    
    def __init__(self, parent, files, db_path, volume="MediaLibrary", last_destination=None, parent_app=None):
        super().__init__(parent, "Move Media Files", 700, 500)
        
        self.files = files
        self.db_path = db_path
        self.default_volume = volume
        self.last_destination = last_destination
        self.parent_app = parent_app
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        ttk.Label(main_frame, text=f"Moving {len(self.files)} file(s)").pack(anchor=tk.W)
        ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Destination
        dest_frame = ttk.Frame(options_frame)
        dest_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(dest_frame, text="Destination:").pack(side=tk.LEFT, padx=(0, 5))
        self.dest_var = tk.StringVar(value=self.last_destination or '')
        ttk.Entry(dest_frame, textvariable=self.dest_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(dest_frame, text="Browse...", command=self.browse_dest).pack(side=tk.LEFT)
        
        # Volume
        volume_frame = ttk.Frame(options_frame)
        volume_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(volume_frame, text="Volume:").pack(side=tk.LEFT, padx=(0, 5))
        self.volume_var = tk.StringVar(value=self.default_volume)
        ttk.Entry(volume_frame, textvariable=self.volume_var, width=30).pack(side=tk.LEFT)
        
        # Dry run (default to True for safety)
        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Dry run (preview only)", 
                       variable=self.dry_run_var).pack(anchor=tk.W, pady=(5, 0))
        
        # Buttons (before output area so they're always visible)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
        
        # Output area (at bottom, can expand)
        self.add_output_area(main_frame)
        
    def browse_dest(self):
        """Browse for destination directory."""
        directory = filedialog.askdirectory(title="Select Destination Directory")
        if directory:
            self.dest_var.set(directory)
            
    def start(self):
        """Start the move operation."""
        if not self.dest_var.get():
            messagebox.showwarning("No Destination", "Please specify a destination directory.")
            return
        
        if not self.volume_var.get():
            messagebox.showwarning("No Volume", "Please specify a volume name.")
            return
        
        self.output_text.delete(1.0, tk.END)
        threading.Thread(target=self._move_files, daemon=True).start()
    
    def _move_files(self):
        """Move files and update database (runs in background thread)."""
        dest_dir = self.dest_var.get()
        volume = self.volume_var.get()
        dry_run = self.dry_run_var.get()
        
        try:
            # Create destination directory if needed (not in dry run)
            if not dry_run and not os.path.exists(dest_dir):
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    self._append_output(f"Created destination directory: {dest_dir}\n")
                except Exception as e:
                    self._append_output(f"Error creating destination directory: {e}\n")
                    return
            
            # Connect to database
            conn = sqlite3.connect(self.db_path)
            create_database_schema(conn)
            
            # Print header
            self._append_output("=" * 70 + "\n")
            self._append_output("Move Media Files\n")
            self._append_output("=" * 70 + "\n")
            self._append_output(f"Files to move: {len(self.files)}\n")
            self._append_output(f"Destination: {dest_dir}\n")
            self._append_output(f"Volume: {volume}\n")
            if dry_run:
                self._append_output("Mode: DRY RUN (no changes will be made)\n")
            self._append_output("\n")
            
            # Counters
            moved_count = 0
            updated_count = 0
            inserted_count = 0
            skipped_count = 0
            error_count = 0
            skip_reasons = {}
            
            # Process each file
            for file_path in self.files:
                status, action = self._process_file(
                    file_path, dest_dir, volume, conn, dry_run
                )
                
                if status == 'success':
                    moved_count += 1
                    if action == 'updated':
                        updated_count += 1
                    elif action == 'inserted':
                        inserted_count += 1
                elif status == 'skipped':
                    skipped_count += 1
                    skip_reasons[action] = skip_reasons.get(action, 0) + 1
                else:
                    error_count += 1
            
            # Commit changes
            if not dry_run:
                conn.commit()
                self._append_output("\n✓ Database changes committed\n")
            
            conn.close()
            
            # Print summary
            self._append_output("\n" + "=" * 70 + "\n")
            self._append_output("Move complete!\n")
            self._append_output(f"Files moved: {moved_count}\n")
            self._append_output(f"  Database updated: {updated_count}\n")
            self._append_output(f"  Database inserted: {inserted_count}\n")
            self._append_output(f"Files skipped: {skipped_count}\n")
            if skip_reasons:
                for reason, count in sorted(skip_reasons.items()):
                    reason_display = reason.replace('_', ' ').title()
                    self._append_output(f"  {reason_display}: {count}\n")
            self._append_output(f"Errors: {error_count}\n")
            if dry_run:
                self._append_output("\n[DRY RUN] No actual changes were made\n")
            self._append_output("=" * 70 + "\n")
            
            # Save the destination for future use (only if not dry run and at least one file moved)
            if not dry_run and moved_count > 0 and self.parent_app:
                self.parent_app.last_move_destination = dest_dir
                self.parent_app.save_config(silent=True)
            
        except Exception as e:
            self._append_output(f"\nError: {e}\n")
            import traceback
            self._append_output(f"{traceback.format_exc()}\n")
    
    def _process_file(self, source_path: str, dest_dir: str, volume: str,
                     conn: sqlite3.Connection, dry_run: bool) -> Tuple[str, str]:
        """Process a single file: move and update database."""
        self._append_output(f"\nProcessing: {source_path}\n")
        
        # Check if source exists
        if not os.path.exists(source_path):
            self._append_output(f"  ✗ Source file not found\n")
            return 'error', 'File not found'
        
        # Get file info before moving
        old_path = os.path.abspath(source_path)
        
        try:
            source_hash = calculate_file_hash(source_path)
            if not source_hash:
                self._append_output(f"  ✗ Could not calculate file hash\n")
                return 'error', 'Hash calculation failed'
        except Exception as e:
            self._append_output(f"  ✗ Error calculating hash: {e}\n")
            return 'error', 'Hash calculation failed'
        
        mime_type = get_mime_type(source_path)
        extension = os.path.splitext(source_path)[1].lower()
        
        # Determine destination path
        filename = os.path.basename(source_path)
        dest_path = os.path.join(dest_dir, filename)
        
        # Check if destination already exists with different name
        if os.path.exists(dest_path):
            # Check if same content
            if os.path.exists(dest_path):
                dest_hash = calculate_file_hash(dest_path)
                if dest_hash == source_hash:
                    self._append_output(f"  Skipping: File already exists in destination with same content\n")
                    return 'skipped', 'destination_exists_same_hash'
            
            # Generate unique name
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest_path):
                new_filename = f"{base}_{counter}{ext}"
                dest_path = os.path.join(dest_dir, new_filename)
                counter += 1
            self._append_output(f"  Destination exists, using: {os.path.basename(dest_path)}\n")
        
        # Check if file exists in database at destination path
        cursor = conn.cursor()
        cursor.execute("SELECT id, file_hash FROM files WHERE fullpath = ?", (dest_path,))
        result = cursor.fetchone()
        
        if result:
            file_id, db_hash = result
            if db_hash == source_hash:
                self._append_output(f"  Skipping: File already in database at destination\n")
                return 'skipped', 'db_exact_match'
        
        # Move the file
        if dry_run:
            self._append_output(f"  [DRY RUN] Would move to: {dest_path}\n")
            new_path = dest_path
        else:
            try:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(source_path, dest_path)
                new_path = dest_path
                self._append_output(f"  ✓ Moved to: {dest_path}\n")
            except Exception as e:
                self._append_output(f"  ✗ Error moving file: {e}\n")
                return 'error', 'Failed to move file'
        
        # Update or insert database record
        action, file_id = self._update_or_insert_file(
            conn, old_path, new_path, volume, dry_run
        )
        
        if action == 'error':
            self._append_output(f"  ✗ Database update failed\n")
            return 'error', 'Database update failed'
        
        action_str = "Would be " + action if dry_run else action.capitalize()
        self._append_output(f"  ✓ {action_str}\n")
        
        # Log audit record
        if not dry_run:
            # Get old volume if it existed in database
            cursor = conn.cursor()
            cursor.execute("SELECT volume FROM files WHERE id = ?", (file_id,))
            result = cursor.fetchone()
            old_volume = result[0] if result else None
            
            log_audit(
                conn=conn,
                operation='move',
                file_path=new_path,
                success=True,
                file_hash=source_hash,
                old_path=old_path,
                new_path=new_path,
                old_volume=old_volume,
                new_volume=volume,
                additional_info=f"Database action: {action}"
            )
        
        return 'success', action
    
    def _update_or_insert_file(self, conn: sqlite3.Connection, old_path: str,
                               new_path: str, volume: str, dry_run: bool) -> Tuple[str, int]:
        """Update existing file record or insert new one."""
        cursor = conn.cursor()
        
        try:
            # Check if file exists in database by old path
            cursor.execute("SELECT id FROM files WHERE fullpath = ?", (old_path,))
            existing = cursor.fetchone()
            
            if existing:
                file_id = existing[0]
                
                # Update the record with new path
                if not dry_run:
                    modified_date = datetime.fromtimestamp(os.path.getmtime(new_path)).isoformat()
                    
                    cursor.execute("""
                        UPDATE files 
                        SET fullpath = ?, 
                            volume = ?,
                            name = ?,
                            modified_date = ?,
                            indexed_date = ?
                        WHERE id = ?
                    """, (
                        new_path,
                        volume,
                        os.path.basename(new_path),
                        modified_date,
                        datetime.now().isoformat(),
                        file_id
                    ))
                
                self._append_output(f"  Updated database record (ID: {file_id})\n")
                return 'updated', file_id
            else:
                # File not in database, insert new record
                stat = os.stat(new_path)
                mime_type = get_mime_type(new_path)
                extension = os.path.splitext(new_path)[1].lower()
                file_hash = calculate_file_hash(new_path)
                
                modified_date = datetime.fromtimestamp(stat.st_mtime).isoformat()
                try:
                    created_date = datetime.fromtimestamp(stat.st_ctime).isoformat()
                except Exception:
                    created_date = modified_date
                
                if not dry_run:
                    cursor.execute("""
                        INSERT INTO files (
                            volume, fullpath, name, created_date, modified_date,
                            size, mime_type, extension, file_hash, indexed_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        volume,
                        new_path,
                        os.path.basename(new_path),
                        created_date,
                        modified_date,
                        stat.st_size,
                        mime_type,
                        extension,
                        file_hash,
                        datetime.now().isoformat()
                    ))
                    file_id = cursor.lastrowid
                else:
                    file_id = -1
                
                self._append_output(f"  Inserted new database record (ID: {file_id})\n")
                return 'inserted', file_id
                
        except Exception as e:
            self._append_output(f"  Error updating database: {e}\n")
            return 'error', -1
    
    def _append_output(self, text):
        """Thread-safe append to output text widget."""
        self.output_text.after(0, lambda: self.output_text.insert(tk.END, text))
        self.output_text.after(0, lambda: self.output_text.see(tk.END))


class ManageDuplicatesDialog(OperationDialogBase):
    """Dialog for managing duplicate files."""
    
    def __init__(self, parent, source_dir, db_path):
        super().__init__(parent, "Manage Duplicates", 700, 500)
        
        self.source_dir = source_dir
        self.db_path = db_path
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        ttk.Label(main_frame, text=f"Source: {self.source_dir}").pack(anchor=tk.W)
        ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Destination
        dest_frame = ttk.Frame(options_frame)
        dest_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(dest_frame, text="Duplicate Destination:").pack(side=tk.LEFT, padx=(0, 5))
        self.dest_var = tk.StringVar()
        ttk.Entry(dest_frame, textvariable=self.dest_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(dest_frame, text="Browse...", command=self.browse_dest).pack(side=tk.LEFT)
        
        # Action
        action_frame = ttk.Frame(options_frame)
        action_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(action_frame, text="Action:").pack(side=tk.LEFT, padx=(0, 5))
        self.action_var = tk.StringVar(value="move")
        ttk.Radiobutton(action_frame, text="Move", variable=self.action_var, value="move").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(action_frame, text="Copy", variable=self.action_var, value="copy").pack(side=tk.LEFT)
        
        # Media only
        self.media_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Media files only (images and videos)", 
                       variable=self.media_only_var).pack(anchor=tk.W, pady=(5, 0))
        
        # Dry run
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Dry run (preview only)", 
                       variable=self.dry_run_var).pack(anchor=tk.W, pady=(5, 0))
        
        # Output area
        self.add_output_area(main_frame)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
        
    def browse_dest(self):
        """Browse for destination directory."""
        directory = filedialog.askdirectory(title="Select Duplicate Destination Directory")
        if directory:
            self.dest_var.set(directory)
            
    def start(self):
        """Start the duplicate management operation."""
        if not self.dest_var.get():
            messagebox.showwarning("No Destination", "Please specify a destination directory for duplicates.")
            return
            
        # Find manage_dupes.py in parent directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dupes_script = os.path.join(script_dir, 'manage_dupes.py')
        
        if not os.path.exists(dupes_script):
            messagebox.showerror("Error", f"manage_dupes.py not found at {dupes_script}")
            return
            
        # Build command
        cmd = ['python3', dupes_script]
        cmd.extend(['--source', self.source_dir])
        cmd.extend(['--destination', self.dest_var.get()])
        cmd.extend(['--db-path', self.db_path])
        cmd.extend(['--action', self.action_var.get()])
        cmd.extend(['--verbose', '2'])
        
        if self.media_only_var.get():
            cmd.append('--media-only')
            
        if self.dry_run_var.get():
            cmd.append('--dry-run')
            
        self.run_command_async(cmd)


class LocateInDbDialog(OperationDialogBase):
    """Dialog for locating files in database."""
    
    def __init__(self, parent, files, db_path):
        super().__init__(parent, "Locate in Database", 800, 600)
        
        self.files = files
        self.db_path = db_path
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        ttk.Label(main_frame, text=f"Locating {len(self.files)} file(s)").pack(anchor=tk.W)
        ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.show_metadata_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Show metadata", variable=self.show_metadata_var).pack(anchor=tk.W)
        
        self.show_hash_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Show file hash", variable=self.show_hash_var).pack(anchor=tk.W)
        
        # Output area
        self.add_output_area(main_frame)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
        
    def start(self):
        """Start the locate operation."""
        self.output_text.delete(1.0, tk.END)
        threading.Thread(target=self._locate_files, daemon=True).start()
        
    def _locate_files(self):
        """Locate files in database (runs in background thread)."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Collect results
            not_found = []
            uniques = []
            dupes = []
            
            for file_path in self.files:
                if not os.path.exists(file_path):
                    self._append_output(f"Warning: File not found: {file_path}\n")
                    continue
                
                self._append_output(f"Processing: {os.path.basename(file_path)}...\n")
                
                # Calculate hash
                try:
                    file_hash = calculate_file_hash(file_path)
                    if not file_hash:
                        self._append_output(f"  Error: Could not calculate hash\n")
                        continue
                except Exception as e:
                    self._append_output(f"  Error calculating hash: {e}\n")
                    continue
                
                # Find matches
                matches = self._find_by_hash(conn, file_hash)
                
                # Categorize
                if len(matches) == 0:
                    not_found.append(file_path)
                elif len(matches) == 1:
                    uniques.append({
                        'query_file': file_path,
                        'match': matches[0],
                        'file_hash': file_hash
                    })
                else:
                    dupes.append({
                        'query_file': file_path,
                        'matches': matches,
                        'file_hash': file_hash
                    })
            
            # Print results
            self._append_output("\n" + "=" * 80 + "\n")
            self._append_output("RESULTS SUMMARY\n")
            self._append_output("=" * 80 + "\n\n")
            
            # Not Found section
            if not_found:
                self._append_output("NOT FOUND IN DATABASE\n")
                self._append_output("-" * 80 + "\n")
                for file_path in not_found:
                    self._append_output(f"  {file_path}\n")
                self._append_output("\n")
            
            # Uniques section
            if uniques:
                self._append_output("UNIQUE FILES (Found once)\n")
                self._append_output("-" * 80 + "\n")
                for item in uniques:
                    self._append_output(f"  Candidate: {item['query_file']}\n")
                    if self.show_hash_var.get():
                        self._append_output(f"    Hash: {item['file_hash']}\n")
                    self._append_output(f"    Match:\n")
                    self._print_match(conn, item['match'])
                    self._append_output("\n")
            
            # Duplicates section
            if dupes:
                self._append_output("DUPLICATES (Found multiple times)\n")
                self._append_output("-" * 80 + "\n")
                for item in dupes:
                    self._append_output(f"  Candidate: {item['query_file']}\n")
                    if self.show_hash_var.get():
                        self._append_output(f"    Hash: {item['file_hash']}\n")
                    self._append_output(f"    Duplicates ({len(item['matches'])}):\n")
                    for match in item['matches']:
                        self._print_match(conn, match)
                    self._append_output("\n")
            
            self._append_output("=" * 80 + "\n")
            self._append_output(f"Total: {len(not_found)} not found, {len(uniques)} unique, {len(dupes)} with duplicates\n")
            self._append_output("=" * 80 + "\n")
            
            conn.close()
            
        except Exception as e:
            self._append_output(f"\nError: {e}\n")
    
    def _find_by_hash(self, conn, file_hash):
        """Find all files in database with matching hash."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, volume, fullpath, name, created_date, modified_date, 
                   size, mime_type, extension, indexed_date
            FROM files
            WHERE file_hash = ?
            ORDER BY indexed_date DESC
        """, (file_hash,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'volume': row[1],
                'fullpath': row[2],
                'name': row[3],
                'created_date': row[4],
                'modified_date': row[5],
                'size': row[6],
                'mime_type': row[7],
                'extension': row[8],
                'indexed_date': row[9]
            })
        return results
    
    def _print_match(self, conn, match):
        """Print a single match with details."""
        self._append_output(f"      {match['fullpath']}\n")
        
        if self.show_metadata_var.get():
            details = []
            details.append(f"Vol:{match['volume']}")
            details.append(f"Size:{self._format_size(match['size'])}")
            
            # Check existence
            if os.path.exists(match['fullpath']):
                details.append("✓Exists")
            else:
                details.append("✗Missing")
            
            # Get metadata
            metadata = self._get_file_metadata(conn, match['id'], match['mime_type'])
            if metadata:
                if metadata['type'] == 'image':
                    if metadata['width'] and metadata['height']:
                        details.append(f"{metadata['width']}x{metadata['height']}")
                    if metadata['date_taken']:
                        details.append(f"Date:{metadata['date_taken']}")
                    if metadata['city'] or metadata['state']:
                        loc = ', '.join(filter(None, [metadata['city'], metadata['state']]))
                        if loc:
                            details.append(f"Loc:{loc}")
                elif metadata['type'] == 'video':
                    if metadata['width'] and metadata['height']:
                        details.append(f"{metadata['width']}x{metadata['height']}")
                    if metadata['duration']:
                        minutes, seconds = divmod(int(metadata['duration']), 60)
                        details.append(f"Dur:{minutes}:{seconds:02d}")
            
            self._append_output(f"        [{' | '.join(details)}]\n")
    
    def _get_file_metadata(self, conn, file_id, mime_type):
        """Get metadata for a file."""
        cursor = conn.cursor()
        
        if mime_type and mime_type.startswith('image/'):
            cursor.execute("""
                SELECT width, height, date_taken, camera_make, camera_model,
                       latitude, longitude, city, state, country, keywords
                FROM image_metadata
                WHERE file_id = ?
            """, (file_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'type': 'image',
                    'width': row[0],
                    'height': row[1],
                    'date_taken': row[2],
                    'camera_make': row[3],
                    'camera_model': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'city': row[7],
                    'state': row[8],
                    'country': row[9],
                    'keywords': row[10]
                }
        
        elif mime_type and mime_type.startswith('video/'):
            cursor.execute("""
                SELECT width, height, duration_seconds, frame_rate, video_codec
                FROM video_metadata
                WHERE file_id = ?
            """, (file_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'type': 'video',
                    'width': row[0],
                    'height': row[1],
                    'duration': row[2],
                    'frame_rate': row[3],
                    'video_codec': row[4]
                }
        
        return None
    
    def _format_size(self, size_bytes):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def _append_output(self, text):
        """Thread-safe append to output text widget."""
        self.output_text.after(0, lambda: self.output_text.insert(tk.END, text))
        self.output_text.after(0, lambda: self.output_text.see(tk.END))


class ApplyExifDialog(OperationDialogBase):
    """Dialog for applying EXIF tags."""
    
    def __init__(self, parent, files, db_path, remembered_location=None, parent_app=None):
        super().__init__(parent, "Apply EXIF Tags", 750, 700)
        
        self.files = files
        self.db_path = db_path
        self.remembered_location = remembered_location or {}
        self.parent_app = parent_app  # Reference to main app for updating remembered location
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        ttk.Label(main_frame, text=f"Applying EXIF to {len(self.files)} file(s)").pack(anchor=tk.W)
        if self.db_path:
            ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Location & Metadata", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # GPS Coordinates section
        gps_frame = ttk.LabelFrame(options_frame, text="GPS Coordinates", padding="5")
        gps_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Latitude
        lat_frame = ttk.Frame(gps_frame)
        lat_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(lat_frame, text="Latitude:").pack(side=tk.LEFT, padx=(0, 5))
        self.latitude_var = tk.StringVar(value=str(self.remembered_location.get('latitude', '')) if self.remembered_location.get('latitude') else '')
        ttk.Entry(lat_frame, textvariable=self.latitude_var, width=20).pack(side=tk.LEFT)
        
        # Longitude
        lon_frame = ttk.Frame(gps_frame)
        lon_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(lon_frame, text="Longitude:").pack(side=tk.LEFT, padx=(0, 5))
        self.longitude_var = tk.StringVar(value=str(self.remembered_location.get('longitude', '')) if self.remembered_location.get('longitude') else '')
        ttk.Entry(lon_frame, textvariable=self.longitude_var, width=20).pack(side=tk.LEFT)
        
        # Altitude
        alt_frame = ttk.Frame(gps_frame)
        alt_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(alt_frame, text="Altitude (m):").pack(side=tk.LEFT, padx=(0, 5))
        self.altitude_var = tk.StringVar(value=str(self.remembered_location.get('altitude', '')) if self.remembered_location.get('altitude') else '')
        ttk.Entry(alt_frame, textvariable=self.altitude_var, width=20).pack(side=tk.LEFT)
        
        # Clear GPS button
        ttk.Button(gps_frame, text="Clear GPS", command=self.clear_gps).pack(anchor=tk.W, pady=(5, 0))
        
        # Location details section
        location_detail_frame = ttk.LabelFrame(options_frame, text="Location Details", padding="5")
        location_detail_frame.pack(fill=tk.X, pady=(5, 5))
        
        # City
        city_frame = ttk.Frame(location_detail_frame)
        city_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(city_frame, text="City:").pack(side=tk.LEFT, padx=(0, 5))
        self.city_var = tk.StringVar(value=self.remembered_location.get('city', ''))
        ttk.Entry(city_frame, textvariable=self.city_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # State
        state_frame = ttk.Frame(location_detail_frame)
        state_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(state_frame, text="State:").pack(side=tk.LEFT, padx=(0, 5))
        self.state_var = tk.StringVar(value=self.remembered_location.get('state', ''))
        ttk.Entry(state_frame, textvariable=self.state_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Country
        country_frame = ttk.Frame(location_detail_frame)
        country_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(country_frame, text="Country:").pack(side=tk.LEFT, padx=(0, 5))
        self.country_var = tk.StringVar(value=self.remembered_location.get('country', ''))
        ttk.Entry(country_frame, textvariable=self.country_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Country Code
        country_code_frame = ttk.Frame(location_detail_frame)
        country_code_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(country_code_frame, text="Country Code:").pack(side=tk.LEFT, padx=(0, 5))
        self.country_code_var = tk.StringVar(value=self.remembered_location.get('country_code', ''))
        ttk.Entry(country_code_frame, textvariable=self.country_code_var, width=10).pack(side=tk.LEFT)
        
        # Coverage
        coverage_frame = ttk.Frame(location_detail_frame)
        coverage_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(coverage_frame, text="Coverage:").pack(side=tk.LEFT, padx=(0, 5))
        self.coverage_var = tk.StringVar(value=self.remembered_location.get('coverage', ''))
        ttk.Entry(coverage_frame, textvariable=self.coverage_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Other metadata section
        other_frame = ttk.LabelFrame(options_frame, text="Other Metadata", padding="5")
        other_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Place (legacy field)
        location_frame = ttk.Frame(other_frame)
        location_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(location_frame, text="Place:").pack(side=tk.LEFT, padx=(0, 5))
        self.place_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.place_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Keywords
        keywords_frame = ttk.Frame(other_frame)
        keywords_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(keywords_frame, text="Add Keywords:").pack(side=tk.LEFT, padx=(0, 5))
        self.keywords_var = tk.StringVar()
        ttk.Entry(keywords_frame, textvariable=self.keywords_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(keywords_frame, text="(comma-separated)").pack(side=tk.LEFT, padx=(5, 0))
        
        # Caption
        caption_frame = ttk.Frame(other_frame)
        caption_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(caption_frame, text="Caption:").pack(side=tk.LEFT, padx=(0, 5))
        self.caption_var = tk.StringVar()
        ttk.Entry(caption_frame, textvariable=self.caption_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Reprocess database
        if self.db_path:
            self.reprocess_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(other_frame, text="Update database after applying EXIF", 
                           variable=self.reprocess_var).pack(anchor=tk.W, pady=(5, 0))
        
        # Dry run
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(other_frame, text="Dry run (preview only)", 
                       variable=self.dry_run_var).pack(anchor=tk.W, pady=(5, 0))
        
        # Output area
        self.add_output_area(main_frame)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Remember", command=self.remember_current_location).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
    
    def remember_current_location(self):
        """Remember the current location data from the dialog fields."""
        if not self.parent_app:
            messagebox.showwarning("Cannot Remember", "No parent application reference available.")
            return
        
        # Parse and validate GPS coordinates
        latitude = None
        longitude = None
        altitude = None
        
        if self.latitude_var.get().strip():
            try:
                latitude = float(self.latitude_var.get().strip())
            except ValueError:
                messagebox.showerror("Invalid Latitude", "Latitude must be a number")
                return
        
        if self.longitude_var.get().strip():
            try:
                longitude = float(self.longitude_var.get().strip())
            except ValueError:
                messagebox.showerror("Invalid Longitude", "Longitude must be a number")
                return
        
        if self.altitude_var.get().strip():
            try:
                altitude = float(self.altitude_var.get().strip())
            except ValueError:
                messagebox.showerror("Invalid Altitude", "Altitude must be a number")
                return
        
        # Update parent app's remembered location
        self.parent_app.remembered_location = {
            'latitude': latitude,
            'longitude': longitude,
            'altitude': altitude,
            'city': self.city_var.get().strip() or None,
            'state': self.state_var.get().strip() or None,
            'country': self.country_var.get().strip() or None,
            'country_code': self.country_code_var.get().strip() or None,
            'coverage': self.coverage_var.get().strip() or None
        }
        
        # Build summary message
        parts = []
        if latitude is not None and longitude is not None:
            parts.append(f"GPS: {latitude:.6f}, {longitude:.6f}")
        if altitude is not None:
            parts.append(f"Altitude: {altitude} m")
        
        location_parts = []
        if self.city_var.get().strip():
            location_parts.append(self.city_var.get().strip())
        if self.state_var.get().strip():
            location_parts.append(self.state_var.get().strip())
        if self.country_var.get().strip():
            location_parts.append(self.country_var.get().strip())
        
        if location_parts:
            parts.append(f"Location: {', '.join(location_parts)}")
        
        if self.country_code_var.get().strip():
            parts.append(f"Country Code: {self.country_code_var.get().strip()}")
        if self.coverage_var.get().strip():
            parts.append(f"Coverage: {self.coverage_var.get().strip()}")
        
        message = "Location data remembered:\n\n" + "\n".join(parts) if parts else "No location data to remember"
        messagebox.showinfo("Location Remembered", message)
    
    def clear_gps(self):
        """Clear all GPS and location fields."""
        self.latitude_var.set('')
        self.longitude_var.set('')
        self.altitude_var.set('')
        self.city_var.set('')
        self.state_var.set('')
        self.country_var.set('')
        self.country_code_var.set('')
        self.coverage_var.set('')
        
    def start(self):
        """Start the EXIF application."""
        # Find apply_exif.py in parent directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        exif_script = os.path.join(script_dir, 'apply_exif.py')
        
        if not os.path.exists(exif_script):
            messagebox.showerror("Error", f"apply_exif.py not found at {exif_script}")
            return
            
        # Build command
        cmd = ['python3', exif_script]
        
        for file_path in self.files:
            cmd.extend(['--files', file_path])
        
        # GPS coordinates
        if self.latitude_var.get().strip():
            try:
                lat = float(self.latitude_var.get().strip())
                cmd.extend(['--latitude', str(lat)])
            except ValueError:
                messagebox.showerror("Invalid Latitude", "Latitude must be a number between -90 and 90")
                return
        
        if self.longitude_var.get().strip():
            try:
                lon = float(self.longitude_var.get().strip())
                cmd.extend(['--longitude', str(lon)])
            except ValueError:
                messagebox.showerror("Invalid Longitude", "Longitude must be a number between -180 and 180")
                return
        
        if self.altitude_var.get().strip():
            try:
                alt = float(self.altitude_var.get().strip())
                cmd.extend(['--altitude', str(alt)])
            except ValueError:
                messagebox.showerror("Invalid Altitude", "Altitude must be a number")
                return
        
        # Location details
        if self.city_var.get().strip():
            cmd.extend(['--city', self.city_var.get().strip()])
        
        if self.state_var.get().strip():
            cmd.extend(['--state', self.state_var.get().strip()])
        
        if self.country_var.get().strip():
            cmd.extend(['--country', self.country_var.get().strip()])
        
        if self.country_code_var.get().strip():
            cmd.extend(['--country-code', self.country_code_var.get().strip()])
        
        if self.coverage_var.get().strip():
            cmd.extend(['--coverage', self.coverage_var.get().strip()])
            
        # Other metadata
        if self.place_var.get():
            cmd.extend(['--place', self.place_var.get()])
            
        if self.keywords_var.get():
            for keyword in self.keywords_var.get().split(','):
                keyword = keyword.strip()
                if keyword:
                    cmd.extend(['--add-keyword', keyword])
                    
        if self.caption_var.get():
            cmd.extend(['--caption', self.caption_var.get()])
            
        if self.db_path:
            cmd.extend(['--db-path', self.db_path])
            if hasattr(self, 'reprocess_var') and self.reprocess_var.get():
                cmd.append('--reprocess-db')
                
        cmd.extend(['--verbose', '2'])
        
        if self.dry_run_var.get():
            cmd.append('--dry-run')
            
        self.run_command_async(cmd)


class DeleteFilesDialog(OperationDialogBase):
    """Dialog for deleting files and their database records."""
    
    def __init__(self, parent, files, db_path, parent_app=None):
        super().__init__(parent, "Delete Files", 700, 500)
        
        self.files = files
        self.db_path = db_path
        self.parent_app = parent_app
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning message
        warning_frame = ttk.Frame(main_frame)
        warning_frame.pack(fill=tk.X, pady=(0, 10))
        
        warning_label = ttk.Label(warning_frame, 
                                 text="⚠ WARNING: This will permanently delete files!",
                                 foreground="red",
                                 font=('TkDefaultFont', 10, 'bold'))
        warning_label.pack(anchor=tk.W)
        
        # Info
        ttk.Label(main_frame, text=f"Deleting {len(self.files)} file(s)").pack(anchor=tk.W)
        ttk.Label(main_frame, text=f"Database: {self.db_path}").pack(anchor=tk.W, pady=(0, 10))
        
        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Delete from database checkbox
        self.delete_from_db_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, 
                       text="Also delete records from database (if exists)", 
                       variable=self.delete_from_db_var).pack(anchor=tk.W, pady=(0, 5))
        
        # Dry run (default to True for safety)
        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Dry run (preview only)", 
                       variable=self.dry_run_var).pack(anchor=tk.W)
        
        # Buttons (before output area so they're always visible)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Start", command=self.start).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.LEFT)
        
        # Output area (at bottom, can expand)
        self.add_output_area(main_frame)
        
        # List candidate files with full paths
        self._list_candidate_files()
    
    def _list_candidate_files(self):
        """List all candidate files for deletion in the output window."""
        self._append_output("=" * 70 + "\n")
        self._append_output("Files selected for deletion:\n")
        self._append_output("=" * 70 + "\n\n")
        
        for i, file_path in enumerate(self.files, 1):
            self._append_output(f"{i}. {file_path}\n")
        
        self._append_output("\n" + "=" * 70 + "\n")
        self._append_output(f"Total: {len(self.files)} file(s)\n")
        self._append_output("=" * 70 + "\n\n")
        self._append_output("Click 'Start' to begin deletion (dry run is enabled by default)\n")
        
    def start(self):
        """Start the delete operation."""
        # Confirmation dialog if not dry run
        if not self.dry_run_var.get():
            # Build file list for confirmation
            file_list = "\n".join([f"  • {os.path.basename(f)}" for f in self.files[:10]])
            if len(self.files) > 10:
                file_list += f"\n  ... and {len(self.files) - 10} more files"
            
            message = (
                f"Are you sure you want to permanently delete {len(self.files)} file(s)?\n\n"
                "Files to be deleted:\n"
                f"{file_list}\n\n"
                "This action cannot be undone!"
            )
            
            result = messagebox.askyesno(
                "Confirm Delete",
                message,
                icon='warning'
            )
            if not result:
                return
        
        self.output_text.delete(1.0, tk.END)
        threading.Thread(target=self._delete_files, daemon=True).start()
    
    def _delete_files(self):
        """Delete files and database records (runs in background thread)."""
        dry_run = self.dry_run_var.get()
        delete_from_db = self.delete_from_db_var.get()
        
        try:
            # Connect to database if needed
            conn = None
            if delete_from_db and self.db_path:
                conn = sqlite3.connect(self.db_path)
                create_database_schema(conn)
            
            # Print header
            self._append_output("=" * 70 + "\n")
            self._append_output("Delete Files\n")
            self._append_output("=" * 70 + "\n")
            self._append_output(f"Files to delete: {len(self.files)}\n")
            if dry_run:
                self._append_output("Mode: DRY RUN (no changes will be made)\n")
            self._append_output("\n")
            
            # Counters
            deleted_count = 0
            db_deleted_count = 0
            skipped_count = 0
            error_count = 0
            
            # Process each file
            for file_path in self.files:
                status, db_deleted = self._process_file(file_path, conn, dry_run, delete_from_db)
                
                if status == 'success':
                    deleted_count += 1
                    if db_deleted:
                        db_deleted_count += 1
                elif status == 'skipped':
                    skipped_count += 1
                else:
                    error_count += 1
            
            # Commit changes
            if conn and not dry_run:
                conn.commit()
                self._append_output("\n✓ Database changes committed\n")
            
            if conn:
                conn.close()
            
            # Print summary
            self._append_output("\n" + "=" * 70 + "\n")
            self._append_output("Delete complete!\n")
            self._append_output(f"Files deleted: {deleted_count}\n")
            self._append_output(f"Database records deleted: {db_deleted_count}\n")
            self._append_output(f"Files skipped: {skipped_count}\n")
            self._append_output(f"Errors: {error_count}\n")
            if dry_run:
                self._append_output("\n[DRY RUN] No actual changes were made\n")
            self._append_output("=" * 70 + "\n")
            
            # Refresh file list in parent app if not dry run
            if not dry_run and deleted_count > 0 and self.parent_app:
                self.parent_app.root.after(100, self.parent_app.refresh_file_list)
            
        except Exception as e:
            self._append_output(f"\nError: {e}\n")
            import traceback
            self._append_output(f"{traceback.format_exc()}\n")
    
    def _process_file(self, file_path: str, conn: sqlite3.Connection, 
                     dry_run: bool, delete_from_db: bool) -> tuple:
        """Process a single file: delete from filesystem and database.
        
        Returns:
            tuple: (status, db_deleted) where status is 'success', 'skipped', or 'error'
                   and db_deleted is True if database record was deleted
        """
        self._append_output(f"\nProcessing: {file_path}\n")
        db_deleted = False
        
        # Check if source exists
        if not os.path.exists(file_path):
            self._append_output(f"  ⚠ File not found (may already be deleted)\n")
            return 'skipped', False
        
        try:
            # Get file info for audit log
            file_hash = calculate_file_hash(file_path)
            file_size = os.path.getsize(file_path)
            
            # Check if file exists in database
            file_id = None
            metadata_before = None
            if conn and delete_from_db:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM files WHERE fullpath = ?", (file_path,))
                result = cursor.fetchone()
                
                if result:
                    file_id = result[0]
                    self._append_output(f"  Found in database (file_id: {file_id})\n")
                    
                    # Get metadata for audit log
                    cursor.execute("""
                        SELECT f.*, im.*, vm.*
                        FROM files f
                        LEFT JOIN image_metadata im ON f.id = im.file_id
                        LEFT JOIN video_metadata vm ON f.id = vm.file_id
                        WHERE f.id = ?
                    """, (file_id,))
                    metadata_result = cursor.fetchone()
                    if metadata_result:
                        import json
                        metadata_before = json.dumps({
                            'file_size': file_size,
                            'file_hash': file_hash,
                            'db_record': str(metadata_result)
                        })
                else:
                    self._append_output(f"  Not found in database\n")
            
            # Delete file from filesystem
            if not dry_run:
                os.remove(file_path)
                self._append_output(f"  ✓ File deleted from filesystem\n")
            else:
                self._append_output(f"  [DRY RUN] Would delete file from filesystem\n")
            
            # Delete from database
            if conn and delete_from_db and file_id:
                if not dry_run:
                    cursor = conn.cursor()
                    # Delete will cascade to related tables (metadata, thumbnails)
                    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
                    self._append_output(f"  ✓ Database record deleted (cascaded to metadata/thumbnails)\n")
                    db_deleted = True
                    
                    # Log audit record
                    log_audit(
                        conn=conn,
                        operation='delete',
                        file_path=file_path,
                        success=True,
                        file_hash=file_hash,
                        metadata_before=metadata_before,
                        additional_info=f"File size: {file_size} bytes"
                    )
                else:
                    self._append_output(f"  [DRY RUN] Would delete database record\n")
            
            return 'success', db_deleted
            
        except Exception as e:
            self._append_output(f"  ✗ Error: {e}\n")
            
            # Log failed operation to audit
            if conn and not dry_run:
                try:
                    log_audit(
                        conn=conn,
                        operation='delete',
                        file_path=file_path,
                        success=False,
                        error_message=str(e),
                        file_hash=file_hash if 'file_hash' in locals() else None
                    )
                except:
                    pass
            
            return 'error', False


def main():
    """Main entry point."""
    if TKDND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = MediaProcessorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
