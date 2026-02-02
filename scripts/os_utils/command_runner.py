#!/usr/bin/env python3
"""command_runner.py - Configurable GUI for executing shell commands.

This application provides a tkinter GUI that can be configured via YAML files
to execute different shell commands with user-provided parameters.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

# Try to import tkinterdnd2 for drag and drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    TkinterDnD = tk.Tk  # Fallback to regular Tk

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ==================== Configuration Schema ====================

CONFIG_SCHEMA = {
    "title": str,           # Window title
    "description": str,     # Description shown at top
    "command": str,         # Command template with {param} placeholders
    "working_dir": str,     # Optional working directory
    "parameters": list,     # List of parameter definitions
    "window_size": str,     # Optional window size "WIDTHxHEIGHT"
    "help_text": str,       # Optional detailed help text shown in popup
}

PARAMETER_SCHEMA = {
    "name": str,            # Parameter name (used in command template)
    "label": str,           # Display label
    "type": str,            # text, number, checkbox, dropdown, file, directory, multiline
    "default": Any,         # Default value
    "required": bool,       # Whether parameter is required
    "help": str,            # Help text shown as tooltip
    "options": list,        # For dropdown type
    "validation": str,      # Optional validation regex
    "multiple": bool,       # If true, each line/value becomes a repeated parameter
}


# ==================== Configuration Loading ====================

def load_config(config_path: str) -> Dict:
    """Load and validate configuration from YAML file.
    
    Args:
        config_path: Path to YAML configuration file
    
    Returns:
        Dictionary with configuration
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if not config:
        raise ValueError("Configuration file is empty")
    
    # Validate required fields
    if 'title' not in config:
        config['title'] = "Command Runner"
    
    if 'command' not in config:
        raise ValueError("Configuration must include 'command' field")
    
    if 'parameters' not in config:
        config['parameters'] = []
    
    # Validate parameters
    for i, param in enumerate(config['parameters']):
        if 'name' not in param:
            raise ValueError(f"Parameter {i} missing 'name' field")
        if 'label' not in param:
            param['label'] = param['name']
        if 'type' not in param:
            param['type'] = 'text'
        if 'required' not in param:
            param['required'] = False
        if param['type'] == 'dropdown' and 'options' not in param:
            raise ValueError(f"Parameter '{param['name']}' of type 'dropdown' requires 'options' field")
    
    return config


def save_example_configs():
    """Save example configuration files."""
    
    # Example 1: apply_exif.py
    example1 = {
        'title': 'Apply EXIF Tags',
        'description': 'Apply EXIF/XMP tags to image files',
        'command': 'python3 ~/monorepo/scripts/apply_exif.py {dry_run} {files} {add_keyword} {caption} {place} {date} {offset}',
        'working_dir': '~',
        'window_size': '800x600',
        'help_text': '''Apply EXIF Tags - Help

This tool applies EXIF/XMP metadata tags to image files using exiftool.

PARAMETERS:

Image Files (required):
  - Specify one or more image files to process
  - Each file on a separate line
  - Supports glob patterns (e.g., *.jpg)
  - Supports files with spaces in names

Keywords:
  - Add keywords/tags to images
  - One keyword per line
  - Keywords are added to existing keywords (not replaced)
  - Use --remove-keyword to remove specific keywords

Caption:
  - Add a caption/description to the image
  - Stored in Caption-Abstract field

Place:
  - Location name (e.g., "Fort Worth, Texas, USA")
  - Automatically geocodes to get GPS coordinates
  - Adds city, state, country metadata
  - Requires internet connection

Date/Time:
  - Format: YYYY:MM:DD HH:MM:SS
  - Example: 2024:08:15 14:30:00
  - Sets DateTimeOriginal and CreateDate

UTC Offset:
  - Time zone offset from UTC
  - Format: +HH:MM or -HH:MM
  - Example: -06:00 for Central Time

Dry Run:
  - When checked, shows what would be done without making changes
  - Always recommended to test first

EXAMPLES:

Add keywords to all JPG files:
  Files: *.jpg
  Keywords: vacation
            beach
            summer
  Dry Run: ☑

Add location to specific photo:
  Files: IMG_1234.jpg
  Place: Paris, France
  Date: 2024:08:15 14:30:00
  Offset: +02:00

NOTES:
- Changes are permanent (unless using dry run)
- Original files are overwritten (backup recommended)
- Requires exiftool to be installed
- Multiple files can be processed at once
''',
        'parameters': [
            {
                'name': 'files',
                'label': 'Image Files',
                'type': 'text',
                'multiple': True,
                'required': True,
                'help': 'Image files (one per line)',
                'default': '*.jpg'
            },
            {
                'name': 'add_keyword',
                'label': 'Add Keywords',
                'type': 'text',
                'multiple': True,
                'help': 'Keywords to add (one per line)',
                'default': ''
            },
            {
                'name': 'caption',
                'label': 'Caption',
                'type': 'text',
                'help': 'Caption text',
                'default': ''
            },
            {
                'name': 'place',
                'label': 'Place',
                'type': 'text',
                'help': 'Location (e.g., "Fort Worth, Texas, USA")',
                'default': ''
            },
            {
                'name': 'date',
                'label': 'Date/Time',
                'type': 'text',
                'help': 'Date in YYYY:MM:DD HH:MM:SS format',
                'default': ''
            },
            {
                'name': 'offset',
                'label': 'UTC Offset',
                'type': 'text',
                'help': 'UTC offset (e.g., "-06:00")',
                'default': ''
            },
            {
                'name': 'dry_run',
                'label': 'Dry Run',
                'type': 'checkbox',
                'help': 'Preview changes without applying',
                'default': True
            }
        ]
    }
    
    # Example 2: index_media.py
    example2 = {
        'title': 'Index Media Files',
        'description': 'Index photos and videos into SQLite database',
        'command': 'python3 ~/monorepo/scripts/index_media.py --path {path} --start-dir {start_dir} --volume {volume} --db-path {db_path} {verbose} {dry_run} {media_only} {skip_pattern} {max_depth}',
        'working_dir': '~',
        'window_size': '900x700',
        'help_text': '''Index Media Files - Help

This tool recursively scans directories and indexes media files (photos and videos) 
into a SQLite database with metadata extraction.

PARAMETERS:

Base Path (required):
  - Root directory containing your media files
  - Example: /home/user/Photos

Start Directory (required):
  - Subdirectories to scan (relative to Base Path)
  - One directory per line
  - Use "." for entire Base Path
  - Example:
    2020
    2021
    2024/vacation

Volume Tag (required):
  - Identifier for this collection
  - Used to distinguish different sources
  - Example: "MainLibrary", "Backup2024"

Database Path (required):
  - Path to SQLite database file
  - Will be created if doesn't exist
  - Example: media.db

Verbosity:
  0 = Quiet (only summary)
  1 = Normal (file names and status)
  2 = Detailed (metadata found)
  3 = Debug (full details)

Skip Patterns:
  - Patterns to exclude from indexing
  - One pattern per line
  - Uses regular expressions
  - Common patterns:
    .DS_Store
    @eaDir
    Thumbs.db
    \\.git

Max Depth:
  - Limit directory recursion depth
  - 0 = current directory only
  - Leave empty for unlimited

Media Files Only:
  - When checked, only indexes images and videos
  - Skips documents, text files, etc.

Dry Run:
  - Preview what would be indexed without making changes

WHAT GETS INDEXED:

For Images:
  - File information (path, size, dates, hash)
  - EXIF metadata (camera, lens, settings)
  - GPS coordinates and location
  - Keywords and captions
  - Thumbnails

For Videos:
  - File information
  - Video metadata (resolution, codec, duration)
  - Thumbnails

SUPPORTED FORMATS:

Images: JPG, PNG, GIF, TIFF, RAW formats (CR2, NEF, ARW, RW2, etc.)
Videos: MP4, MOV, AVI, MKV, MPG, WMV

EXAMPLES:

Index entire photo library:
  Base Path: /home/user/Photos
  Start Directory: .
  Volume: MainLibrary
  Database: media.db
  Media Only: ☑

Index specific years:
  Base Path: /mnt/photos
  Start Directory: 2020
                   2021
                   2022
  Volume: Archive
  Skip Patterns: .DS_Store
                 @eaDir

NOTES:
- First run may take time for large collections
- Subsequent runs update existing records
- Database can be queried with SQL
- Thumbnails stored in database
''',
        'parameters': [
            {
                'name': 'path',
                'label': 'Base Path',
                'type': 'directory',
                'required': True,
                'help': 'Base directory containing media files',
                'default': '/home/ubuntu/TestData/Images'
            },
            {
                'name': 'start_dir',
                'label': 'Start Directory',
                'type': 'text',
                'multiple': True,
                'required': True,
                'help': 'Starting subdirectories (one per line, relative to path)',
                'default': '.'
            },
            {
                'name': 'volume',
                'label': 'Volume Tag',
                'type': 'text',
                'required': True,
                'help': 'Volume identifier',
                'default': 'MainLibrary'
            },
            {
                'name': 'db_path',
                'label': 'Database Path',
                'type': 'file',
                'required': True,
                'help': 'Path to SQLite database file',
                'default': 'media.db'
            },
            {
                'name': 'verbose',
                'label': 'Verbosity',
                'type': 'dropdown',
                'options': ['0', '1', '2', '3'],
                'help': 'Verbosity level (0=quiet, 3=debug)',
                'default': '1'
            },
            {
                'name': 'skip_pattern',
                'label': 'Skip Patterns',
                'type': 'text',
                'multiple': True,
                'help': 'Patterns to skip (one per line, e.g., ".DS_Store")',
                'default': ''
            },
            {
                'name': 'max_depth',
                'label': 'Max Depth',
                'type': 'number',
                'help': 'Maximum directory depth (0=current only)',
                'default': ''
            },
            {
                'name': 'media_only',
                'label': 'Media Files Only',
                'type': 'checkbox',
                'help': 'Only process image/video files',
                'default': True
            },
            {
                'name': 'dry_run',
                'label': 'Dry Run',
                'type': 'checkbox',
                'help': 'Preview without making changes',
                'default': False
            }
        ]
    }
    
    # Example 3: Generic command
    example3 = {
        'title': 'File Search',
        'description': 'Search for files using find command',
        'command': 'find {directory} {name_pattern} {type} {max_depth}',
        'window_size': '700x500',
        'parameters': [
            {
                'name': 'directory',
                'label': 'Search Directory',
                'type': 'directory',
                'required': True,
                'help': 'Directory to search in',
                'default': '.'
            },
            {
                'name': 'name_pattern',
                'label': 'Name Pattern',
                'type': 'text',
                'help': 'File name pattern (e.g., "*.jpg")',
                'default': '*'
            },
            {
                'name': 'type',
                'label': 'File Type',
                'type': 'dropdown',
                'options': ['', 'f', 'd', 'l'],
                'help': 'f=file, d=directory, l=symlink',
                'default': ''
            },
            {
                'name': 'max_depth',
                'label': 'Max Depth',
                'type': 'number',
                'help': 'Maximum search depth',
                'default': ''
            }
        ]
    }
    
    # Save examples
    examples_dir = Path.home() / '.command_runner' / 'examples'
    examples_dir.mkdir(parents=True, exist_ok=True)
    
    with open(examples_dir / 'apply_exif.yaml', 'w') as f:
        yaml.dump(example1, f, default_flow_style=False, sort_keys=False)
    
    with open(examples_dir / 'index_media.yaml', 'w') as f:
        yaml.dump(example2, f, default_flow_style=False, sort_keys=False)
    
    with open(examples_dir / 'find_files.yaml', 'w') as f:
        yaml.dump(example3, f, default_flow_style=False, sort_keys=False)
    
    return examples_dir


# ==================== GUI Application ====================

class CommandRunnerApp:
    """Main application window for command runner."""
    
    def __init__(self, config: Dict, config_path: str = None):
        """Initialize the application.
        
        Args:
            config: Configuration dictionary
            config_path: Path to configuration file (for reloading)
        """
        self.config = config
        self.config_path = config_path
        self.param_widgets = {}
        self.running = False
        
        # Create main window with DnD support if available
        if TKDND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        self.root.title(config['title'])
        
        # Set window size if specified
        if 'window_size' in config:
            self.root.geometry(config['window_size'])
        else:
            self.root.geometry('800x600')
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create all GUI widgets."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Description
        if 'description' in self.config:
            desc_label = ttk.Label(main_frame, text=self.config['description'], 
                                  font=('TkDefaultFont', 10, 'bold'))
            desc_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # Parameters frame with scrollbar
        params_frame = ttk.LabelFrame(main_frame, text="Parameters", padding="10")
        params_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        main_frame.rowconfigure(1, weight=1)
        
        # Create canvas for scrolling
        canvas = tk.Canvas(params_frame)
        scrollbar = ttk.Scrollbar(params_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create parameter inputs
        for i, param in enumerate(self.config['parameters']):
            self.create_parameter_widget(scrollable_frame, i, param)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        params_frame.columnconfigure(0, weight=1)
        params_frame.rowconfigure(0, weight=1)
        
        # Command preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Command Preview", padding="5")
        preview_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.command_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=3, 
                                                      bg='#f0f0f0', font=('Courier', 9))
        self.command_text.pack(fill=tk.BOTH, expand=True)
        self.bind_text_shortcuts(self.command_text)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.run_button = ttk.Button(buttons_frame, text="Run Command", command=self.run_command)
        self.run_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(buttons_frame, text="Stop", command=self.stop_command, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(buttons_frame, text="Clear Output", command=self.clear_output).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Copy Command", command=self.copy_command).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Save Config", command=self.save_current_config).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Edit Metadata", command=self.edit_metadata).pack(side=tk.LEFT, padx=(0, 5))
        
        # Add Reload Config button if config_path is available
        if self.config_path:
            ttk.Button(buttons_frame, text="Reload Config", command=self.reload_config).pack(side=tk.LEFT, padx=(0, 5))
        
        # Add Help button if help_text is available
        if 'help_text' in self.config and self.config['help_text']:
            ttk.Button(buttons_frame, text="Help", command=self.show_help).pack(side=tk.LEFT)
        
        # Output frame
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="5")
        output_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.rowconfigure(4, weight=2)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=15)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.bind_text_shortcuts(self.output_text)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=5, column=0, sticky=(tk.W, tk.E))
        
        # Initial command preview update
        self.update_command_preview()
    
    def create_parameter_widget(self, parent, row, param):
        """Create a widget for a parameter.
        
        Args:
            parent: Parent widget
            row: Grid row number
            param: Parameter configuration
        """
        # Label
        label_text = param['label']
        if param.get('required', False):
            label_text += " *"
        
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        
        # Widget based on type
        param_type = param['type']
        
        if param_type == 'text':
            # Check if this is a multiple-value parameter
            if param.get('multiple', False):
                # Use multiline text widget
                widget = scrolledtext.ScrolledText(parent, width=50, height=4, wrap=tk.WORD)
                if 'default' in param:
                    widget.insert(1.0, str(param['default']))
                widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
                widget.bind('<KeyRelease>', lambda e: self.update_command_preview())
                self.bind_text_shortcuts(widget)
                self.enable_drag_drop(widget, 'text')
                self.param_widgets[param['name']] = widget
            else:
                widget = ttk.Entry(parent, width=50)
                if 'default' in param:
                    widget.insert(0, str(param['default']))
                widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
                widget.bind('<KeyRelease>', lambda e: self.update_command_preview())
                self.bind_text_shortcuts(widget)
                self.enable_drag_drop(widget, 'text')
                self.param_widgets[param['name']] = widget
        
        elif param_type == 'number':
            widget = ttk.Entry(parent, width=20)
            if 'default' in param:
                widget.insert(0, str(param['default']))
            widget.grid(row=row, column=1, sticky=tk.W, pady=5)
            widget.bind('<KeyRelease>', lambda e: self.update_command_preview())
            self.bind_text_shortcuts(widget)
            self.enable_drag_drop(widget, 'number')
            self.param_widgets[param['name']] = widget
        
        elif param_type == 'checkbox':
            var = tk.BooleanVar(value=param.get('default', False))
            widget = ttk.Checkbutton(parent, variable=var, command=self.update_command_preview)
            widget.grid(row=row, column=1, sticky=tk.W, pady=5)
            self.param_widgets[param['name']] = var
        
        elif param_type == 'dropdown':
            var = tk.StringVar(value=param.get('default', param['options'][0] if param['options'] else ''))
            widget = ttk.Combobox(parent, textvariable=var, values=param['options'], width=47)
            widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
            widget.bind('<<ComboboxSelected>>', lambda e: self.update_command_preview())
            self.param_widgets[param['name']] = var
        
        elif param_type == 'file':
            frame = ttk.Frame(parent)
            frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
            
            var = tk.StringVar(value=param.get('default', ''))
            var.trace_add('write', lambda *args: self.update_command_preview())
            entry = ttk.Entry(frame, textvariable=var, width=40)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.bind_text_shortcuts(entry)
            self.enable_drag_drop(entry, 'file')
            
            def browse_file():
                filename = filedialog.askopenfilename(initialdir=os.path.expanduser('~'))
                if filename:
                    var.set(filename)
            
            browse_btn = ttk.Button(frame, text="Browse...", command=browse_file)
            browse_btn.pack(side=tk.LEFT, padx=(5, 0))
            
            self.param_widgets[param['name']] = var
        
        elif param_type == 'directory':
            frame = ttk.Frame(parent)
            frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
            
            var = tk.StringVar(value=param.get('default', ''))
            var.trace_add('write', lambda *args: self.update_command_preview())
            entry = ttk.Entry(frame, textvariable=var, width=40)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.bind_text_shortcuts(entry)
            self.enable_drag_drop(entry, 'directory')
            
            def browse_dir():
                dirname = filedialog.askdirectory(initialdir=os.path.expanduser('~'))
                if dirname:
                    var.set(dirname)
            
            browse_btn = ttk.Button(frame, text="Browse...", command=browse_dir)
            browse_btn.pack(side=tk.LEFT, padx=(5, 0))
            
            self.param_widgets[param['name']] = var
        
        # Help text as tooltip
        if 'help' in param:
            self.create_tooltip(label, param['help'])
        
        parent.columnconfigure(1, weight=1)
    
    def bind_text_shortcuts(self, widget):
        """Bind standard keyboard shortcuts to a text widget.
        
        Args:
            widget: Text widget (Entry, Text, or ScrolledText)
        """
        # Detect platform for correct modifier key
        if sys.platform == 'darwin':
            # macOS uses Command key
            mod = 'Command'
        else:
            # Windows and Linux use Control key
            mod = 'Control'
        
        # For ScrolledText widgets (multiline)
        if isinstance(widget, scrolledtext.ScrolledText):
            # Select All
            widget.bind(f'<{mod}-a>', lambda e: self._select_all_text(widget))
            widget.bind(f'<{mod}-A>', lambda e: self._select_all_text(widget))
            
            # Cut, Copy, Paste (already work by default, but we'll ensure they're bound)
            widget.bind(f'<{mod}-x>', lambda e: self._cut_text(widget))
            widget.bind(f'<{mod}-X>', lambda e: self._cut_text(widget))
            widget.bind(f'<{mod}-c>', lambda e: self._copy_text(widget))
            widget.bind(f'<{mod}-C>', lambda e: self._copy_text(widget))
            widget.bind(f'<{mod}-v>', lambda e: self._paste_text(widget))
            widget.bind(f'<{mod}-V>', lambda e: self._paste_text(widget))
            
        # For Entry widgets (single line)
        elif isinstance(widget, (ttk.Entry, tk.Entry)):
            # Select All
            widget.bind(f'<{mod}-a>', lambda e: widget.select_range(0, tk.END) or 'break')
            widget.bind(f'<{mod}-A>', lambda e: widget.select_range(0, tk.END) or 'break')
            
            # Cut, Copy, Paste work by default in Entry widgets
    
    def _select_all_text(self, widget):
        """Select all text in a Text widget."""
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
        return 'break'
    
    def _cut_text(self, widget):
        """Cut selected text to clipboard."""
        try:
            if widget.tag_ranges(tk.SEL):
                text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                widget.clipboard_clear()
                widget.clipboard_append(text)
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        return 'break'
    
    def _copy_text(self, widget):
        """Copy selected text to clipboard."""
        try:
            if widget.tag_ranges(tk.SEL):
                text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                widget.clipboard_clear()
                widget.clipboard_append(text)
        except tk.TclError:
            pass
        return 'break'
    
    def _paste_text(self, widget):
        """Paste text from clipboard."""
        try:
            text = widget.clipboard_get()
            if widget.tag_ranges(tk.SEL):
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            widget.insert(tk.INSERT, text)
        except tk.TclError:
            pass
        return 'break'
    
    def enable_drag_drop(self, widget, param_type):
        """Enable drag and drop for a widget.
        
        Args:
            widget: Widget to enable drag and drop on
            param_type: Type of parameter (text, file, directory, etc.)
        """
        if not TKDND_AVAILABLE:
            # Add visual indicator that drag and drop is not available
            return
        
        def on_drop(event):
            """Handle drop event."""
            # Get the dropped data
            data = event.data
            
            # Parse the data - tkinter returns file paths in a specific format
            # On Linux/Mac: space-separated paths with {} for paths with spaces
            # On Windows: similar but may have different formatting
            files = self.parse_drop_data(data)
            
            if not files:
                return
            
            # Handle based on widget type
            if isinstance(widget, scrolledtext.ScrolledText):
                # For multiline text widgets, insert each file on a new line
                current = widget.get(1.0, tk.END).strip()
                if current:
                    widget.insert(tk.END, '\n')
                widget.insert(tk.END, '\n'.join(files))
            elif isinstance(widget, ttk.Entry):
                # For single-line entry, insert first file or all space-separated
                if param_type in ['file', 'directory']:
                    widget.delete(0, tk.END)
                    widget.insert(0, files[0])
                else:
                    widget.delete(0, tk.END)
                    widget.insert(0, ' '.join(files))
            elif hasattr(widget, 'set'):  # StringVar - used by Entry with textvariable
                if param_type in ['file', 'directory']:
                    widget.set(files[0])
                else:
                    widget.set(' '.join(files))
            
            # Update command preview
            self.update_command_preview()
            
            return 'break'
        
        try:
            # Register drop target
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', on_drop)
        except Exception:
            # Silently fail if drag and drop registration fails
            pass
    
    def parse_drop_data(self, data):
        """Parse dropped file data.
        
        Args:
            data: Raw drop data from tkinter
        
        Returns:
            List of file paths
        """
        files = []
        
        # Handle different formats
        if not data:
            return files
        
        # Try to parse as space-separated with {} for paths with spaces
        # Example: {/path/with spaces/file.txt} /path/without/spaces.txt
        pattern = r'\{([^}]+)\}|(\S+)'
        matches = re.findall(pattern, str(data))
        
        for match in matches:
            # match is a tuple: (braced_content, unbraced_content)
            path = match[0] if match[0] else match[1]
            if path:
                # Clean up the path
                path = path.strip()
                # Remove file:// prefix if present
                if path.startswith('file://'):
                    path = path[7:]
                files.append(path)
        
        return files
    
    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget.
        
        Args:
            widget: Widget to attach tooltip to
            text: Tooltip text
        """
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", 
                            relief=tk.SOLID, borderwidth=1, padding=5)
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)
    
    def get_parameter_values(self) -> Dict[str, str]:
        """Get current values of all parameters.
        
        Returns:
            Dictionary mapping parameter names to values
        """
        values = {}
        
        for param in self.config['parameters']:
            name = param['name']
            widget = self.param_widgets[name]
            
            if param['type'] == 'checkbox':
                # For checkbox, format as flag
                if widget.get():
                    values[name] = f"--{name.replace('_', '-')}"
                else:
                    values[name] = ""
            elif isinstance(widget, (tk.StringVar, tk.BooleanVar)):
                value = widget.get()
                values[name] = str(value) if value else ""
            elif isinstance(widget, scrolledtext.ScrolledText):
                # For multiline text widgets, get all text
                value = widget.get(1.0, tk.END).strip()
                values[name] = value if value else ""
            else:
                value = widget.get()
                values[name] = str(value) if value else ""
        
        return values
    
    def validate_parameters(self, values: Dict[str, str]) -> bool:
        """Validate parameter values.
        
        Args:
            values: Dictionary of parameter values
        
        Returns:
            True if valid, False otherwise
        """
        for param in self.config['parameters']:
            if param.get('required', False):
                value = values.get(param['name'], '')
                if not value or (param['type'] != 'checkbox' and not value.strip()):
                    messagebox.showerror("Validation Error", 
                                       f"Required parameter '{param['label']}' is missing")
                    return False
        return True
    
    def build_command(self, values: Dict[str, str]) -> str:
        """Build command string from template and values.
        
        Args:
            values: Dictionary of parameter values
        
        Returns:
            Command string
        """
        command = self.config['command']
        
        # Format parameters for command
        formatted_values = {}
        for param in self.config['parameters']:
            name = param['name']
            value = values.get(name, '')
            
            if param['type'] == 'checkbox':
                # Already formatted as flag or empty
                formatted_values[name] = value
            elif value:
                # Get parameter flag (or use empty if not specified or explicitly empty)
                flag = param.get('flag', '')
                if flag is None:
                    flag = ''
                
                # If no flag specified, generate default flag
                if flag == '' and 'flag' not in param:
                    flag = f"--{name.replace('_', '-')}"
                
                # Handle multiple values (multiline or comma-separated)
                if param.get('multiple', False):
                    # Split by newlines for multiline text
                    lines = [line.strip() for line in value.split('\n') if line.strip()]
                    if lines:
                        # Each line becomes a repeated parameter
                        # Use shlex.quote for proper shell escaping
                        if flag:
                            formatted_values[name] = ' '.join([f'{flag} {shlex.quote(line)}' for line in lines])
                        else:
                            # No flag - just the values
                            formatted_values[name] = ' '.join([shlex.quote(line) for line in lines])
                    else:
                        formatted_values[name] = ''
                elif param['type'] == 'text' and ' ' in value:
                    # Quote values with spaces using shlex.quote
                    if flag:
                        formatted_values[name] = f'{flag} {shlex.quote(value)}'
                    else:
                        formatted_values[name] = shlex.quote(value)
                else:
                    if flag:
                        formatted_values[name] = f'{flag} {value}'
                    else:
                        formatted_values[name] = value
            else:
                formatted_values[name] = ''
        
        # Replace placeholders
        try:
            command = command.format(**formatted_values)
            # Clean up extra spaces
            command = ' '.join(command.split())
            return command
        except KeyError as e:
            raise ValueError(f"Missing parameter in command template: {e}")
    
    def run_command(self):
        """Run the configured command."""
        if self.running:
            return
        
        # Get and validate parameters
        values = self.get_parameter_values()
        if not self.validate_parameters(values):
            return
        
        # Build command
        try:
            command = self.build_command(values)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        
        # Show command
        self.log_output(f"\n{'='*60}\n")
        self.log_output(f"Command: {command}\n")
        self.log_output(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_output(f"{'='*60}\n\n")
        
        # Update UI
        self.running = True
        self.run_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("Running...")
        
        # Run command in thread
        def run_thread():
            try:
                working_dir = self.config.get('working_dir')
                if working_dir:
                    working_dir = os.path.expanduser(working_dir)
                
                # Run command
                self.process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=working_dir,
                    bufsize=1
                )
                
                # Read output
                for line in self.process.stdout:
                    if not self.running:
                        break
                    self.log_output(line)
                
                # Wait for completion
                return_code = self.process.wait()
                
                # Show result
                if return_code == 0:
                    self.log_output(f"\n✓ Command completed successfully (exit code: 0)\n")
                    self.root.after(0, lambda: self.status_var.set("Completed successfully"))
                else:
                    self.log_output(f"\n✗ Command failed (exit code: {return_code})\n")
                    self.root.after(0, lambda: self.status_var.set(f"Failed (exit code: {return_code})"))
                
            except Exception as e:
                self.log_output(f"\n✗ Error: {e}\n")
                self.root.after(0, lambda: self.status_var.set(f"Error: {e}"))
            
            finally:
                self.running = False
                self.root.after(0, lambda: self.run_button.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
        
        thread = threading.Thread(target=run_thread, daemon=True)
        thread.start()
    
    def stop_command(self):
        """Stop the running command."""
        if self.running and hasattr(self, 'process'):
            self.running = False
            self.process.terminate()
            self.log_output("\n⚠ Command stopped by user\n")
            self.status_var.set("Stopped")
    
    def log_output(self, text):
        """Log text to output widget.
        
        Args:
            text: Text to log
        """
        def update():
            self.output_text.insert(tk.END, text)
            self.output_text.see(tk.END)
        
        self.root.after(0, update)
    
    def clear_output(self):
        """Clear the output text."""
        self.output_text.delete(1.0, tk.END)
        self.status_var.set("Ready")
    
    def update_command_preview(self):
        """Update the command preview text."""
        try:
            values = self.get_parameter_values()
            command = self.build_command(values)
            
            # Update preview
            self.command_text.delete(1.0, tk.END)
            self.command_text.insert(1.0, command)
        except Exception as e:
            # If command building fails, show error in preview
            self.command_text.delete(1.0, tk.END)
            self.command_text.insert(1.0, f"Error building command: {e}")
    
    def copy_command(self):
        """Copy the command preview to clipboard."""
        command = self.command_text.get(1.0, tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.status_var.set("Command copied to clipboard")
        self.root.after(2000, lambda: self.status_var.set("Ready") if not self.running else None)
    
    def edit_metadata(self):
        """Edit configuration metadata in a popup window."""
        # Create popup window
        metadata_window = tk.Toplevel(self.root)
        metadata_window.title("Edit Configuration Metadata")
        metadata_window.geometry("700x600")
        
        # Make it modal
        metadata_window.transient(self.root)
        metadata_window.grab_set()
        
        # Main frame with padding
        main_frame = ttk.Frame(metadata_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Configuration Metadata", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))
        
        # Create form fields
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Title field
        ttk.Label(fields_frame, text="Title:").grid(row=0, column=0, sticky=tk.W, pady=5)
        title_var = tk.StringVar(value=self.config.get('title', ''))
        title_entry = ttk.Entry(fields_frame, textvariable=title_var, width=60)
        title_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Description field
        ttk.Label(fields_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=5)
        desc_var = tk.StringVar(value=self.config.get('description', ''))
        desc_entry = ttk.Entry(fields_frame, textvariable=desc_var, width=60)
        desc_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Command field (multiline)
        ttk.Label(fields_frame, text="Command:").grid(row=2, column=0, sticky=(tk.W, tk.N), pady=5)
        command_text = scrolledtext.ScrolledText(fields_frame, width=60, height=4, wrap=tk.WORD)
        command_text.insert(1.0, self.config.get('command', ''))
        command_text.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Working directory field
        ttk.Label(fields_frame, text="Working Dir:").grid(row=3, column=0, sticky=tk.W, pady=5)
        workdir_var = tk.StringVar(value=self.config.get('working_dir', ''))
        workdir_entry = ttk.Entry(fields_frame, textvariable=workdir_var, width=60)
        workdir_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Window size field
        ttk.Label(fields_frame, text="Window Size:").grid(row=4, column=0, sticky=tk.W, pady=5)
        winsize_var = tk.StringVar(value=self.config.get('window_size', ''))
        winsize_entry = ttk.Entry(fields_frame, textvariable=winsize_var, width=60)
        winsize_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Label(fields_frame, text="(e.g., 800x600)", 
                 font=('TkDefaultFont', 8)).grid(row=5, column=1, sticky=tk.W, padx=(10, 0))
        
        # Help text field (multiline)
        ttk.Label(fields_frame, text="Help Text:").grid(row=6, column=0, sticky=(tk.W, tk.N), pady=5)
        help_text_widget = scrolledtext.ScrolledText(fields_frame, width=60, height=8, wrap=tk.WORD)
        help_text_widget.insert(1.0, self.config.get('help_text', ''))
        help_text_widget.grid(row=6, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        fields_frame.columnconfigure(1, weight=1)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_metadata():
            """Save metadata changes."""
            try:
                # Update configuration
                self.config['title'] = title_var.get()
                self.config['description'] = desc_var.get()
                self.config['command'] = command_text.get(1.0, tk.END).strip()
                
                working_dir = workdir_var.get().strip()
                if working_dir:
                    self.config['working_dir'] = working_dir
                elif 'working_dir' in self.config:
                    del self.config['working_dir']
                
                window_size = winsize_var.get().strip()
                if window_size:
                    self.config['window_size'] = window_size
                elif 'window_size' in self.config:
                    del self.config['window_size']
                
                help_text = help_text_widget.get(1.0, tk.END).strip()
                if help_text:
                    self.config['help_text'] = help_text
                elif 'help_text' in self.config:
                    del self.config['help_text']
                
                # Update window title
                self.root.title(self.config['title'])
                
                # Update description if widget exists
                for widget in self.root.winfo_children():
                    if isinstance(widget, ttk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Label) and hasattr(child, 'cget'):
                                try:
                                    font = child.cget('font')
                                    if 'bold' in str(font):
                                        child.config(text=self.config.get('description', ''))
                                        break
                                except:
                                    pass
                
                # Update command preview
                self.update_command_preview()
                
                # Show success message
                self.status_var.set("Metadata updated successfully")
                self.root.after(3000, lambda: self.status_var.set("Ready"))
                
                metadata_window.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save metadata: {e}")
        
        def save_and_write():
            """Save metadata and write to file."""
            save_metadata()
            if self.config_path:
                try:
                    with open(self.config_path, 'w') as f:
                        yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
                    messagebox.showinfo("Success", f"Configuration saved to {self.config_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to write configuration file: {e}")
        
        ttk.Button(buttons_frame, text="Apply", command=save_metadata).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Save to File", command=save_and_write).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Cancel", command=metadata_window.destroy).pack(side=tk.LEFT)
        
        # Center the window
        metadata_window.update_idletasks()
        x = (metadata_window.winfo_screenwidth() // 2) - (metadata_window.winfo_width() // 2)
        y = (metadata_window.winfo_screenheight() // 2) - (metadata_window.winfo_height() // 2)
        metadata_window.geometry(f"+{x}+{y}")
    
    def reload_config(self):
        """Reload the configuration file and rebuild the GUI."""
        if not self.config_path:
            messagebox.showerror("Error", "No configuration file path available")
            return
        
        if self.running:
            messagebox.showwarning("Warning", "Cannot reload while command is running")
            return
        
        # Confirm reload
        if not messagebox.askyesno("Reload Configuration", 
                                   "Reload configuration from file? Current parameter values will be lost."):
            return
        
        try:
            # Load new configuration
            new_config = load_config(self.config_path)
            
            # Store current window geometry
            geometry = self.root.geometry()
            
            # Update configuration
            self.config = new_config
            
            # Clear existing widgets
            for widget in self.root.winfo_children():
                widget.destroy()
            
            # Reset state
            self.param_widgets = {}
            self.running = False
            
            # Update window title
            self.root.title(new_config['title'])
            
            # Restore or set window size
            if 'window_size' in new_config:
                self.root.geometry(new_config['window_size'])
            else:
                self.root.geometry(geometry)
            
            # Recreate widgets
            self.create_widgets()
            
            # Show success message
            self.status_var.set("Configuration reloaded successfully")
            self.root.after(3000, lambda: self.status_var.set("Ready"))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reload configuration: {e}")
    
    def show_help(self):
        """Show help text in a popup window."""
        help_text = self.config.get('help_text', '')
        if not help_text:
            return
        
        # Create popup window
        help_window = tk.Toplevel(self.root)
        help_window.title(f"Help - {self.config['title']}")
        help_window.geometry("700x500")
        
        # Make it modal
        help_window.transient(self.root)
        help_window.grab_set()
        
        # Main frame with padding
        main_frame = ttk.Frame(help_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrolled text widget for help content
        help_text_widget = scrolledtext.ScrolledText(
            main_frame, 
            wrap=tk.WORD, 
            font=('TkDefaultFont', 10),
            padx=10,
            pady=10
        )
        help_text_widget.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        help_text_widget.insert(1.0, help_text)
        help_text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Close button
        close_btn = ttk.Button(main_frame, text="Close", command=help_window.destroy)
        close_btn.pack()
        
        # Center the window
        help_window.update_idletasks()
        x = (help_window.winfo_screenwidth() // 2) - (help_window.winfo_width() // 2)
        y = (help_window.winfo_screenheight() // 2) - (help_window.winfo_height() // 2)
        help_window.geometry(f"+{x}+{y}")
    
    def save_current_config(self):
        """Save current parameter values to a new config file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        
        if filename:
            # Update config with current values
            for param in self.config['parameters']:
                name = param['name']
                widget = self.param_widgets.get(name)
                
                if widget is None:
                    continue
                
                # Handle different widget types
                if param['type'] == 'checkbox':
                    # For checkbox, save the boolean value
                    param['default'] = widget.get()
                elif isinstance(widget, (tk.StringVar, tk.BooleanVar)):
                    # For StringVar/BooleanVar widgets
                    value = widget.get()
                    param['default'] = value if value else ''
                elif isinstance(widget, scrolledtext.ScrolledText):
                    # For multiline text widgets
                    value = widget.get(1.0, tk.END).strip()
                    param['default'] = value if value else ''
                else:
                    # For Entry widgets
                    value = widget.get()
                    param['default'] = value if value else ''
            
            with open(filename, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            
            messagebox.showinfo("Success", f"Configuration saved to {filename}")
    
    def run(self):
        """Start the application."""
        self.root.mainloop()


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Configurable GUI for executing shell commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with a configuration file
  python3 command_runner.py --config apply_exif.yaml
  
  # Generate example configurations
  python3 command_runner.py --examples
  
  # List available example configs
  python3 command_runner.py --list-examples
        """
    )
    
    parser.add_argument("--config", "-c", help="Path to YAML configuration file")
    parser.add_argument("--examples", action="store_true", help="Generate example configuration files")
    parser.add_argument("--list-examples", action="store_true", help="List available example configurations")
    
    args = parser.parse_args()
    
    # Generate examples
    if args.examples:
        examples_dir = save_example_configs()
        print(f"Example configurations saved to: {examples_dir}")
        print("\nAvailable examples:")
        for config_file in sorted(examples_dir.glob("*.yaml")):
            print(f"  - {config_file.name}")
        print(f"\nRun with: python3 command_runner.py --config {examples_dir}/apply_exif.yaml")
        return
    
    # List examples
    if args.list_examples:
        examples_dir = Path.home() / '.command_runner' / 'examples'
        if examples_dir.exists():
            print("Available example configurations:")
            for config_file in sorted(examples_dir.glob("*.yaml")):
                print(f"  - {config_file}")
        else:
            print("No examples found. Run with --examples to generate them.")
        return
    
    # Load config
    if not args.config:
        print("Error: --config is required", file=sys.stderr)
        print("Run with --examples to generate example configurations", file=sys.stderr)
        sys.exit(1)
    
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Create and run app
    app = CommandRunnerApp(config, config_path=args.config)
    app.run()


if __name__ == "__main__":
    main()
