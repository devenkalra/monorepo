#!/usr/bin/env python3
"""image_process.py - Unified GUI for all media management commands.

This application provides a single interface for all media management operations,
with dynamic parameter visibility based on the selected command.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

# Try to import tkinterdnd2 for drag and drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    TkinterDnD = tk.Tk


# Command configurations
COMMANDS = {
    'apply_exif': {
        'name': 'Apply EXIF Tags',
        'script': '~/monorepo/scripts/apply_exif.py',
        'description': 'Apply EXIF/XMP tags to images',
        'params': ['files', 'place', 'location_bookmark', 'gps_coords', 'city', 'state', 'country', 
                   'country_code', 'coverage', 'date', 'offset', 'add_keyword', 'remove_keyword', 
                   'caption', 'tags_yaml', 'db_path', 'reprocess_db', 'dry_run', 'limit']
    },
    'locate_in_db': {
        'name': 'Locate in Database',
        'script': '~/monorepo/scripts/locate_in_db.py',
        'description': 'Find files in database by hash',
        'params': ['files', 'db_path', 'metadata', 'json_output', 'show_hash', 'summary', 'limit']
    },
    'move_media': {
        'name': 'Move Media Files',
        'script': '~/monorepo/scripts/move_media.py',
        'description': 'Move media files and update database',
        'params': ['files', 'destination', 'volume', 'db_path', 'verbose', 'dry_run', 'audit_log', 'limit']
    },
    'find_location': {
        'name': 'Find Location Info',
        'script': '~/monorepo/scripts/find_location.py',
        'description': 'Geocode place name and show location metadata',
        'params': ['place_name', 'date', 'offset']
    },
    'manage_dupes': {
        'name': 'Manage Duplicates',
        'script': '~/monorepo/scripts/manage_dupes.py',
        'description': 'Find and manage duplicate files',
        'params': ['source', 'destination', 'db_path', 'action', 'media_only', 
                   'include_pattern', 'skip_pattern', 'literal_patterns', 'verbose', 'dry_run', 'limit']
    },
    'index_media': {
        'name': 'Index Media Files',
        'script': '~/monorepo/scripts/index_media.py',
        'description': 'Index media files into database',
        'params': ['path', 'start_dir', 'volume', 'db_path', 'include_pattern', 'skip_pattern',
                   'literal_patterns', 'max_depth', 'verbose', 'dry_run', 'limit']
    },
    'show_exif': {
        'name': 'Show EXIF Metadata',
        'script': '~/monorepo/scripts/show_exif.py',
        'description': 'Display EXIF/metadata information from files',
        'params': ['files', 'exif_mode', 'grouped', 'specific_tags', 'no_filenames', 
                   'extract_thumbnails', 'thumbnail_dir', 'limit']
    }
}

# Parameter definitions
PARAM_DEFS = {
    'files': {
        'label': 'Files',
        'type': 'multiline',
        'flag': '--file',
        'help': 'Files to process (one per line)',
        'default': ''
    },
    'place': {
        'label': 'Place',
        'type': 'text',
        'flag': '--place',
        'help': 'Location (e.g., "Fort Worth, Texas, USA")',
        'default': ''
    },
    'place_name': {
        'label': 'Place Name',
        'type': 'text',
        'flag': '',
        'help': 'Place to geocode',
        'default': ''
    },
    'location_bookmark': {
        'label': 'Location Bookmark',
        'type': 'bookmark_dropdown',  # Special type for bookmark selection
        'flag': '',  # No flag - this is UI only
        'help': 'Select saved location bookmark',
        'default': ''
    },
    'gps_coords': {
        'label': 'GPS Coordinates',
        'type': 'text',
        'flag': '',  # Special handling - will be parsed
        'help': 'GPS coordinates: lat,lon or lat,lon,altitude (e.g., 28.5439554,77.198706,1183)',
        'default': ''
    },
    'city': {
        'label': 'City',
        'type': 'text',
        'flag': '--city',
        'help': 'City name',
        'default': ''
    },
    'state': {
        'label': 'State',
        'type': 'text',
        'flag': '--state',
        'help': 'State/Province name',
        'default': ''
    },
    'country': {
        'label': 'Country',
        'type': 'text',
        'flag': '--country',
        'help': 'Country name',
        'default': ''
    },
    'country_code': {
        'label': 'Country Code',
        'type': 'text',
        'flag': '--country-code',
        'help': 'Country code (e.g., US, IN, FR)',
        'default': ''
    },
    'coverage': {
        'label': 'Full Address',
        'type': 'text',
        'flag': '--coverage',
        'help': 'Full address or location description',
        'default': ''
    },
    'date': {
        'label': 'Date/Time',
        'type': 'text',
        'flag': '--date',
        'help': 'Date in YYYY:MM:DD HH:MM:SS format',
        'default': ''
    },
    'offset': {
        'label': 'UTC Offset',
        'type': 'text',
        'flag': '--offset',
        'help': 'UTC offset (e.g., +05:30 or -06:00)',
        'default': ''
    },
    'add_keyword': {
        'label': 'Add Keywords',
        'type': 'multiline',
        'flag': '--add-keyword',
        'help': 'Keywords to add (one per line)',
        'default': ''
    },
    'remove_keyword': {
        'label': 'Remove Keywords',
        'type': 'multiline',
        'flag': '--remove-keyword',
        'help': 'Keywords to remove (one per line)',
        'default': ''
    },
    'caption': {
        'label': 'Caption',
        'type': 'text',
        'flag': '--caption',
        'help': 'Image caption/description',
        'default': ''
    },
    'tags_yaml': {
        'label': 'Tags YAML File',
        'type': 'file',
        'flag': '--tags-yaml',
        'help': 'YAML file with tags',
        'default': ''
    },
    'db_path': {
        'label': 'Database Path',
        'type': 'file',
        'flag': '--db-path',
        'help': 'Path to media database',
        'default': 'media.db'
    },
    'destination': {
        'label': 'Destination',
        'type': 'directory',
        'flag': '--destination',
        'help': 'Destination directory',
        'default': ''
    },
    'source': {
        'label': 'Source Directory',
        'type': 'directory',
        'flag': '--source',
        'help': 'Source directory to scan',
        'default': ''
    },
    'path': {
        'label': 'Base Path',
        'type': 'directory',
        'flag': '--path',
        'help': 'Base directory path',
        'default': ''
    },
    'start_dir': {
        'label': 'Start Directories',
        'type': 'multiline',
        'flag': '--start-dir',
        'help': 'Starting directories (one per line)',
        'default': ''
    },
    'volume': {
        'label': 'Volume Tag',
        'type': 'text',
        'flag': '--volume',
        'help': 'Volume identifier',
        'default': ''
    },
    'action': {
        'label': 'Action',
        'type': 'dropdown',
        'flag': '--action',
        'options': ['move', 'copy'],
        'help': 'Action to perform',
        'default': 'move'
    },
    'verbose': {
        'label': 'Verbosity',
        'type': 'dropdown',
        'flag': '--verbose',
        'options': ['0', '1', '2', '3'],
        'help': 'Verbosity level (0-3)',
        'default': '1'
    },
    'max_depth': {
        'label': 'Max Depth',
        'type': 'text',
        'flag': '--max-depth',
        'help': 'Maximum directory depth',
        'default': ''
    },
    'include_pattern': {
        'label': 'Include Pattern',
        'type': 'multiline',
        'flag': '--include-pattern',
        'help': 'Include patterns (one per line)',
        'default': ''
    },
    'skip_pattern': {
        'label': 'Skip Pattern',
        'type': 'multiline',
        'flag': '--skip-pattern',
        'help': 'Skip patterns (one per line)',
        'default': ''
    },
    'audit_log': {
        'label': 'Audit Log',
        'type': 'file',
        'flag': '--audit-log',
        'help': 'Audit log file path',
        'default': ''
    },
    'dry_run': {
        'label': 'Dry Run',
        'type': 'checkbox',
        'flag': '--dry-run',
        'help': 'Preview without making changes',
        'default': False
    },
    'metadata': {
        'label': 'Show Metadata',
        'type': 'checkbox',
        'flag': '--metadata',
        'help': 'Show detailed metadata',
        'default': False
    },
    'reprocess_db': {
        'label': 'Reprocess in Database',
        'type': 'checkbox',
        'flag': '--reprocess-db',
        'help': 'Reprocess files in database after EXIF update (requires Database Path)',
        'default': False
    },
    'json_output': {
        'label': 'JSON Output',
        'type': 'checkbox',
        'flag': '--json',
        'help': 'Output as JSON',
        'default': False
    },
    'show_hash': {
        'label': 'Show Hash',
        'type': 'checkbox',
        'flag': '--show-hash',
        'help': 'Show file hash',
        'default': False
    },
    'summary': {
        'label': 'Summary Only',
        'type': 'checkbox',
        'flag': '--summary',
        'help': 'Show only summary',
        'default': False
    },
    'media_only': {
        'label': 'Media Only',
        'type': 'checkbox',
        'flag': '--media-only',
        'help': 'Process only media files',
        'default': False
    },
    'literal_patterns': {
        'label': 'Literal Patterns',
        'type': 'checkbox',
        'flag': '--literal-patterns',
        'help': 'Use literal (not regex) patterns',
        'default': False
    },
    'limit': {
        'label': 'Limit Files',
        'type': 'text',
        'flag': '--limit',
        'help': 'Limit number of files to process (useful with dry-run)',
        'default': ''
    },
    'exif_mode': {
        'label': 'Display Mode',
        'type': 'multiselect',
        'flag': '--mode',
        'options': ['common', 'gps', 'all', 'specific', 'json', 'keywords', 'camera', 'video', 'thumbnail'],
        'help': 'Type(s) of EXIF information to display',
        'default': ['common']
    },
    'grouped': {
        'label': 'Group by Category',
        'type': 'checkbox',
        'flag': '--grouped',
        'help': 'Group tags by category (EXIF:, XMP:, etc.)',
        'default': False
    },
    'specific_tags': {
        'label': 'Specific Tags',
        'type': 'text',
        'flag': '--tags',
        'help': 'Space-separated tag names (for specific mode)',
        'default': ''
    },
    'no_filenames': {
        'label': 'Hide Filenames',
        'type': 'checkbox',
        'flag': '--no-filenames',
        'help': 'Show only values (no filenames)',
        'default': False
    },
    'extract_thumbnails': {
        'label': 'Extract Thumbnails',
        'type': 'checkbox',
        'flag': '--extract-thumbnails',
        'help': 'Extract and save thumbnails to files',
        'default': False
    },
    'thumbnail_dir': {
        'label': 'Thumbnail Directory',
        'type': 'directory',
        'flag': '--thumbnail-dir',
        'help': 'Directory to save extracted thumbnails (optional)',
        'default': ''
    }
}


class ImageProcessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Process - Unified Media Management")
        self.root.geometry("1000x800")
        
        # Storage for parameter widgets and values
        self.param_widgets = {}
        self.param_values = {}
        self.param_frames = {}
        
        # Current command
        self.current_command = None
        
        # Running process tracking
        self.running_process = None
        self.interrupt_requested = False
        
        # Location bookmarks
        self.bookmarks_file = os.path.expanduser('~/.image_process_bookmarks.json')
        self.location_bookmarks = self.load_bookmarks()
        
        # Create UI
        self.create_widgets()
        
        # Select default command
        self.command_var.set('apply_exif')
        self.on_command_change()
    
    def create_widgets(self):
        """Create the main UI widgets."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Command selection
        cmd_frame = ttk.LabelFrame(main_frame, text="Command", padding="10")
        cmd_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        cmd_frame.columnconfigure(1, weight=1)
        
        ttk.Label(cmd_frame, text="Select Command:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.command_var = tk.StringVar()
        command_combo = ttk.Combobox(cmd_frame, textvariable=self.command_var, state='readonly', width=40)
        command_combo['values'] = [f"{COMMANDS[k]['name']}" for k in sorted(COMMANDS.keys())]
        command_combo.grid(row=0, column=1, sticky=(tk.W, tk.E))
        command_combo.bind('<<ComboboxSelected>>', lambda e: self.on_command_change())
        
        # Description label
        self.desc_label = ttk.Label(cmd_frame, text="", foreground='gray')
        self.desc_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Parameters frame (scrollable)
        params_frame = ttk.LabelFrame(main_frame, text="Parameters", padding="10")
        params_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        params_frame.columnconfigure(0, weight=1)
        params_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Canvas for scrolling
        canvas = tk.Canvas(params_frame, height=300)
        scrollbar = ttk.Scrollbar(params_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.scrollable_frame.columnconfigure(1, weight=1)
        
        # Command preview
        preview_frame = ttk.LabelFrame(main_frame, text="Command Preview", padding="5")
        preview_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.command_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=3,
                                                      bg='#f0f0f0', font=('Courier', 9))
        self.command_text.pack(fill=tk.BOTH, expand=True)
        self.bind_text_shortcuts(self.command_text)
        
        # Buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(buttons_frame, text="Execute Command", command=self.execute_command).pack(side=tk.LEFT, padx=(0, 5))
        self.interrupt_button = ttk.Button(buttons_frame, text="⏹ Interrupt", command=self.interrupt_command, state='disabled')
        self.interrupt_button.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Copy Command", command=self.copy_command).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Clear Output", command=self.clear_output).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Help", command=self.show_help).pack(side=tk.LEFT, padx=(0, 5))
        
        # Separator
        ttk.Separator(buttons_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)
        
        ttk.Button(buttons_frame, text="Load Config", command=self.load_config).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="Save Config", command=self.save_config).pack(side=tk.LEFT)
        
        # Output
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="5")
        output_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        main_frame.rowconfigure(4, weight=2)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=15)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.bind_text_shortcuts(self.output_text)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=5, column=0, sticky=(tk.W, tk.E))
    
    def on_command_change(self):
        """Handle command selection change."""
        # Get selected command
        selected_name = self.command_var.get()
        cmd_key = None
        for key, cmd in COMMANDS.items():
            if cmd['name'] == selected_name:
                cmd_key = key
                break
        
        if not cmd_key:
            return
        
        self.current_command = cmd_key
        command = COMMANDS[cmd_key]
        
        # Update description
        self.desc_label.config(text=command['description'])
        
        # Save current values
        self.save_current_values()
        
        # Hide all parameter frames
        for frame in self.param_frames.values():
            frame.grid_remove()
        
        # Show/create parameters for this command in correct order
        # Dry-run first if present, then others
        params_to_show = command['params'].copy()
        
        # Reorder: dry_run first
        ordered_params = []
        if 'dry_run' in params_to_show:
            ordered_params.append('dry_run')
            params_to_show.remove('dry_run')
        ordered_params.extend(params_to_show)
        
        # Create/show parameters in order
        for param_name in ordered_params:
            if param_name not in self.param_frames:
                self.create_parameter_widget(param_name)
            self.param_frames[param_name].grid()
        
        # Restore saved values
        self.restore_saved_values()
        
        # Update command preview
        self.update_command_preview()
    
    def create_parameter_widget(self, param_name):
        """Create widget for a parameter."""
        if param_name not in PARAM_DEFS:
            return
        
        param = PARAM_DEFS[param_name]
        row = len(self.param_frames)
        
        frame = ttk.Frame(self.scrollable_frame)
        frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)
        frame.columnconfigure(1, weight=1)
        self.param_frames[param_name] = frame
        
        # Label (right-aligned, fixed width)
        label = ttk.Label(frame, text=param['label'] + ":", width=20, anchor='e')
        label.grid(row=0, column=0, sticky=tk.E, padx=(0, 10))
        
        # Widget based on type
        param_type = param['type']
        
        if param_type == 'text':
            widget = ttk.Entry(frame, width=50)
            if param['default']:
                widget.insert(0, str(param['default']))
            widget.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 0))
            widget.bind('<KeyRelease>', lambda e: self.update_command_preview())
            self.bind_text_shortcuts(widget)
            self.param_widgets[param_name] = widget
        
        elif param_type == 'multiline':
            widget = scrolledtext.ScrolledText(frame, width=50, height=4, wrap=tk.WORD)
            if param['default']:
                widget.insert(1.0, str(param['default']))
            widget.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 0))
            widget.bind('<KeyRelease>', lambda e: self.update_command_preview())
            self.bind_text_shortcuts(widget)
            self.enable_drag_drop(widget, 'text')
            self.param_widgets[param_name] = widget
            
            # Add tooltip for file selection
            if param_name == 'files' and not TKDND_AVAILABLE:
                tooltip_text = "Right-click to add files"
                self.create_tooltip(widget, tooltip_text)
        
        elif param_type == 'checkbox':
            var = tk.BooleanVar(value=param['default'])
            widget = ttk.Checkbutton(frame, text=param['help'], variable=var,
                                    command=self.update_command_preview)
            widget.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=(0, 0))
            self.param_widgets[param_name] = var
        
        elif param_type == 'dropdown':
            var = tk.StringVar(value=param['default'])
            widget = ttk.Combobox(frame, textvariable=var, values=param['options'],
                                 state='readonly', width=20)
            widget.grid(row=0, column=1, sticky=tk.W, padx=(0, 0))
            widget.bind('<<ComboboxSelected>>', lambda e: self.update_command_preview())
            self.param_widgets[param_name] = var
        
        elif param_type == 'bookmark_dropdown':
            # Create container for bookmark dropdown and buttons
            bookmark_frame = ttk.Frame(frame)
            bookmark_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 0))
            bookmark_frame.columnconfigure(0, weight=1)
            
            # Dropdown with bookmark names
            bookmark_names = [''] + list(self.location_bookmarks.keys())
            var = tk.StringVar(value=param['default'])
            combobox = ttk.Combobox(bookmark_frame, textvariable=var, values=bookmark_names,
                                   width=30)
            combobox.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
            combobox.bind('<<ComboboxSelected>>', lambda e: self.load_location_bookmark())
            
            # Load button
            load_btn = ttk.Button(bookmark_frame, text="📍 Load", command=self.load_location_bookmark, width=8)
            load_btn.grid(row=0, column=1, padx=(0, 5))
            
            # Save button
            save_btn = ttk.Button(bookmark_frame, text="💾 Save", command=self.save_location_bookmark, width=8)
            save_btn.grid(row=0, column=2)
            
            self.param_widgets[param_name] = var
        
        elif param_type == 'multiselect':
            # Create a frame for the listbox and scrollbar
            list_frame = ttk.Frame(frame)
            list_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 0))
            
            # Scrollbar for listbox
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
            
            # Listbox with multiple selection
            listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=6, width=30,
                                exportselection=False, yscrollcommand=scrollbar.set)
            scrollbar.config(command=listbox.yview)
            
            # Add options
            for option in param['options']:
                listbox.insert(tk.END, option)
            
            # Select defaults
            default_values = param['default'] if isinstance(param['default'], list) else [param['default']]
            for i, option in enumerate(param['options']):
                if option in default_values:
                    listbox.selection_set(i)
            
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Bind selection change
            listbox.bind('<<ListboxSelect>>', lambda e: self.update_command_preview())
            
            self.param_widgets[param_name] = listbox
        
        elif param_type == 'file':
            var = tk.StringVar(value=param['default'])
            entry = ttk.Entry(frame, textvariable=var, width=40)
            entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
            self.bind_text_shortcuts(entry)
            self.enable_drag_drop(entry, 'file')
            
            def browse_file():
                filename = filedialog.askopenfilename(initialdir=os.path.expanduser('~'))
                if filename:
                    var.set(filename)
                    self.update_command_preview()
            
            browse_btn = ttk.Button(frame, text="Browse...", command=browse_file)
            browse_btn.grid(row=0, column=2, sticky=tk.W, padx=(0, 0))
            var.trace_add('write', lambda *args: self.update_command_preview())
            self.param_widgets[param_name] = var
        
        elif param_type == 'directory':
            var = tk.StringVar(value=param['default'])
            entry = ttk.Entry(frame, textvariable=var, width=40)
            entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
            self.bind_text_shortcuts(entry)
            self.enable_drag_drop(entry, 'directory')
            
            def browse_dir():
                dirname = filedialog.askdirectory(initialdir=os.path.expanduser('~'))
                if dirname:
                    var.set(dirname)
                    self.update_command_preview()
            
            browse_btn = ttk.Button(frame, text="Browse...", command=browse_dir)
            browse_btn.grid(row=0, column=2, sticky=tk.W, padx=(0, 0))
            var.trace_add('write', lambda *args: self.update_command_preview())
            self.param_widgets[param_name] = var
    
    def save_current_values(self):
        """Save current parameter values."""
        for param_name, widget in self.param_widgets.items():
            param = PARAM_DEFS.get(param_name)
            if not param:
                continue
            
            if param['type'] == 'multiline':
                self.param_values[param_name] = widget.get(1.0, tk.END).strip()
            elif param['type'] == 'multiselect':
                # Save selected items as list
                selected_indices = widget.curselection()
                selected_values = [widget.get(i) for i in selected_indices]
                self.param_values[param_name] = selected_values
            elif param['type'] in ['checkbox', 'dropdown', 'file', 'directory', 'bookmark_dropdown']:
                self.param_values[param_name] = widget.get()
            elif param['type'] == 'text':
                self.param_values[param_name] = widget.get()
    
    def restore_saved_values(self):
        """Restore saved parameter values."""
        for param_name, value in self.param_values.items():
            if param_name not in self.param_widgets:
                continue
            
            widget = self.param_widgets[param_name]
            param = PARAM_DEFS.get(param_name)
            if not param:
                continue
            
            try:
                if param['type'] == 'multiline':
                    widget.delete(1.0, tk.END)
                    if value:
                        widget.insert(1.0, str(value))
                elif param['type'] == 'multiselect':
                    # Clear selection and select saved values
                    widget.selection_clear(0, tk.END)
                    if isinstance(value, list):
                        for i in range(widget.size()):
                            if widget.get(i) in value:
                                widget.selection_set(i)
                elif param['type'] == 'checkbox':
                    # Handle both boolean and string values
                    if isinstance(value, bool):
                        widget.set(value)
                    elif isinstance(value, str):
                        widget.set(value.lower() in ['true', '1', 'yes'])
                    else:
                        widget.set(bool(value))
                elif param['type'] in ['dropdown', 'file', 'directory', 'bookmark_dropdown']:
                    if value:
                        widget.set(str(value))
                elif param['type'] == 'text':
                    widget.delete(0, tk.END)
                    if value:
                        widget.insert(0, str(value))
            except Exception as e:
                print(f"Warning: Could not restore value for {param_name}: {e}", file=sys.stderr)
    
    def build_command(self):
        """Build the command string."""
        if not self.current_command:
            return ""
        
        command = COMMANDS[self.current_command]
        cmd_parts = ['python3', os.path.expanduser(command['script'])]
        
        for param_name in command['params']:
            if param_name not in self.param_widgets:
                continue
            
            param = PARAM_DEFS[param_name]
            widget = self.param_widgets[param_name]
            
            # Skip UI-only parameters (no command flag)
            if param['type'] == 'bookmark_dropdown':
                continue
            
            # Get value
            if param['type'] == 'multiline':
                value = widget.get(1.0, tk.END).strip()
                if value:
                    lines = value.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            if param['flag']:
                                cmd_parts.extend([param['flag'], shlex.quote(line)])
                            else:
                                cmd_parts.append(shlex.quote(line))
            
            elif param['type'] == 'checkbox':
                if widget.get():
                    cmd_parts.append(param['flag'])
            
            elif param['type'] == 'multiselect':
                # Get selected items
                selected_indices = widget.curselection()
                if selected_indices:
                    for idx in selected_indices:
                        selected_value = widget.get(idx)
                        cmd_parts.extend([param['flag'], selected_value])
            
            elif param['type'] in ['text', 'dropdown', 'file', 'directory']:
                value = widget.get().strip() if hasattr(widget, 'get') else str(widget)
                if value:
                    # Special handling for gps_coords - parse lat,lon or lat,lon,altitude
                    if param_name == 'gps_coords':
                        try:
                            parts = [p.strip() for p in value.split(',')]
                            if len(parts) >= 2:
                                latitude = parts[0]
                                longitude = parts[1]
                                cmd_parts.extend(['--latitude', latitude])
                                cmd_parts.extend(['--longitude', longitude])
                                if len(parts) >= 3:
                                    altitude = parts[2]
                                    cmd_parts.extend(['--altitude', altitude])
                        except Exception:
                            pass  # Invalid format, skip
                    # Special handling for specific_tags - split by space
                    elif param_name == 'specific_tags' and param['flag'] == '--tags':
                        tags = value.split()
                        if tags:
                            cmd_parts.append(param['flag'])
                            cmd_parts.extend(tags)
                    elif param['flag']:
                        if ' ' in value or any(c in value for c in ['&', '|', ';', '<', '>', '(', ')']):
                            cmd_parts.extend([param['flag'], shlex.quote(value)])
                        else:
                            cmd_parts.extend([param['flag'], value])
                    else:
                        if ' ' in value:
                            cmd_parts.append(shlex.quote(value))
                        else:
                            cmd_parts.append(value)
        
        return ' '.join(cmd_parts)
    
    def update_command_preview(self):
        """Update the command preview."""
        command = self.build_command()
        self.command_text.delete(1.0, tk.END)
        self.command_text.insert(1.0, command)
    
    def execute_command(self):
        """Execute the command."""
        command = self.build_command()
        if not command:
            messagebox.showwarning("Warning", "No command to execute")
            return
        
        # Check if already running
        if self.running_process and self.running_process.poll() is None:
            messagebox.showwarning("Warning", "A command is already running. Please wait or interrupt it first.")
            return
        
        # Clear output
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, f"Executing: {command}\n\n")
        self.status_var.set("Running...")
        self.interrupt_requested = False
        self.interrupt_button.config(state='normal')
        self.root.update()
        
        # Run in thread
        def run():
            try:
                # Parse command
                cmd_parts = shlex.split(command)
                
                # Execute
                self.running_process = subprocess.Popen(
                    cmd_parts,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # Stream output
                for line in self.running_process.stdout:
                    if self.interrupt_requested:
                        break
                    self.output_text.insert(tk.END, line)
                    self.output_text.see(tk.END)
                    self.root.update()
                
                # Wait for process to complete
                self.running_process.wait()
                
                # Check results
                if self.interrupt_requested:
                    self.output_text.insert(tk.END, "\n\n⏹ Command interrupted by user\n")
                    self.status_var.set("⏹ Command interrupted")
                elif self.running_process.returncode == 0:
                    self.status_var.set("✓ Command completed successfully")
                else:
                    self.status_var.set(f"✗ Command failed with exit code {self.running_process.returncode}")
                
            except Exception as e:
                self.output_text.insert(tk.END, f"\n\nError: {str(e)}\n")
                self.status_var.set("✗ Error executing command")
            finally:
                # Disable interrupt button
                self.interrupt_button.config(state='disabled')
                self.running_process = None
                self.interrupt_requested = False
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def interrupt_command(self):
        """Interrupt the running command."""
        if not self.running_process or self.running_process.poll() is not None:
            messagebox.showinfo("Info", "No command is currently running.")
            return
        
        if messagebox.askyesno("Confirm Interrupt", 
                              "Are you sure you want to interrupt the running command?"):
            self.interrupt_requested = True
            try:
                # Try to terminate gracefully first
                self.running_process.terminate()
                
                # Wait a bit for graceful termination
                import time
                time.sleep(0.5)
                
                # If still running, force kill
                if self.running_process.poll() is None:
                    self.running_process.kill()
                
                self.output_text.insert(tk.END, "\n\n⏹ Interrupt signal sent...\n")
                self.status_var.set("⏹ Interrupting...")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to interrupt command: {e}")
    
    def copy_command(self):
        """Copy command to clipboard."""
        command = self.build_command()
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.status_var.set("✓ Command copied to clipboard")
    
    def clear_output(self):
        """Clear the output text."""
        self.output_text.delete(1.0, tk.END)
        self.status_var.set("Ready")
    
    def show_help(self):
        """Show help for current command."""
        if not self.current_command:
            return
        
        command = COMMANDS[self.current_command]
        help_text = f"{command['name']}\n\n{command['description']}\n\n"
        help_text += "Parameters:\n\n"
        
        for param_name in command['params']:
            if param_name in PARAM_DEFS:
                param = PARAM_DEFS[param_name]
                help_text += f"• {param['label']}: {param['help']}\n"
        
        # Add specific help for show_exif modes
        if self.current_command == 'show_exif':
            help_text += "\n\nDisplay Modes:\n\n"
            help_text += "• common: Show commonly used EXIF tags (dimensions, camera, dates, exposure)\n"
            help_text += "• gps: Show GPS and location information\n"
            help_text += "• all: Show all available EXIF tags\n"
            help_text += "• specific: Show only specified tags (requires Specific Tags parameter)\n"
            help_text += "• json: Output all data in JSON format\n"
            help_text += "• keywords: Show keywords, subjects, and captions\n"
            help_text += "• camera: Show detailed camera settings\n"
            help_text += "• video: Show video-specific metadata\n"
            help_text += "• thumbnail: Show embedded thumbnail information\n"
            help_text += "\nExtract Thumbnails:\n\n"
            help_text += "• Check 'Extract Thumbnails' to save embedded thumbnails to files\n"
            help_text += "• Optionally specify 'Thumbnail Directory' for where to save them\n"
            help_text += "• If no directory specified, thumbnails are saved to a temporary directory\n"
        
        # Create help window
        help_window = tk.Toplevel(self.root)
        help_window.title(f"Help - {command['name']}")
        help_window.geometry("600x500")
        
        text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(1.0, help_text)
        text.config(state=tk.DISABLED)
        
        close_btn = ttk.Button(help_window, text="Close", command=help_window.destroy)
        close_btn.pack(pady=10)
    
    def save_config(self):
        """Save current configuration to file."""
        # Ask for save location
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="image_process_config.json",
            title="Save Configuration"
        )
        
        if not filename:
            return
        
        try:
            # Save current values
            self.save_current_values()
            
            # Build config
            config = {
                'version': '1.0',
                'current_command': self.current_command,
                'parameters': {}
            }
            
            # Save all parameter values
            for param_name, value in self.param_values.items():
                if value:  # Only save non-empty values
                    config['parameters'][param_name] = value
            
            # Write to file
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.status_var.set(f"✓ Configuration saved to {os.path.basename(filename)}")
            messagebox.showinfo("Success", f"Configuration saved to:\n{filename}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{str(e)}")
            self.status_var.set("✗ Failed to save configuration")
    
    def load_config(self):
        """Load configuration from file."""
        # Ask for file to load
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Load Configuration"
        )
        
        if not filename:
            return
        
        try:
            # Read config file
            with open(filename, 'r') as f:
                config = json.load(f)
            
            # Validate config
            if 'version' not in config or 'parameters' not in config:
                raise ValueError("Invalid configuration file format")
            
            # Load parameter values into temporary storage
            loaded_params = config['parameters']
            
            # Switch to saved command if available
            if 'current_command' in config and config['current_command']:
                saved_command = config['current_command']
                if saved_command in COMMANDS:
                    # Set command dropdown
                    self.command_var.set(COMMANDS[saved_command]['name'])
                    # Trigger command change which will create widgets
                    self.on_command_change()
                    
                    # Now restore the values after widgets are created
                    # Update param_values with loaded values
                    self.param_values.update(loaded_params)
                    
                    # Restore values to widgets
                    self.restore_saved_values()
                else:
                    raise ValueError(f"Unknown command: {saved_command}")
            else:
                # No command specified, just load the parameters
                self.param_values.update(loaded_params)
                self.restore_saved_values()
            
            # Update command preview
            self.update_command_preview()
            
            self.status_var.set(f"✓ Configuration loaded from {os.path.basename(filename)}")
            messagebox.showinfo("Success", f"Configuration loaded from:\n{filename}")
        
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON file:\n{str(e)}")
            self.status_var.set("✗ Failed to load configuration")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration:\n{str(e)}")
            self.status_var.set("✗ Failed to load configuration")
    
    def bind_text_shortcuts(self, widget):
        """Bind keyboard shortcuts to a text widget."""
        mod = 'Command' if sys.platform == 'darwin' else 'Control'
        
        if isinstance(widget, scrolledtext.ScrolledText):
            widget.bind(f'<{mod}-a>', lambda e: self._select_all_text(widget))
            widget.bind(f'<{mod}-A>', lambda e: self._select_all_text(widget))
        elif isinstance(widget, (ttk.Entry, tk.Entry)):
            widget.bind(f'<{mod}-a>', lambda e: widget.select_range(0, tk.END) or 'break')
            widget.bind(f'<{mod}-A>', lambda e: widget.select_range(0, tk.END) or 'break')
    
    def _select_all_text(self, widget):
        """Select all text in a Text widget."""
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
        return 'break'
    
    def enable_drag_drop(self, widget, param_type):
        """Enable drag and drop for a widget."""
        if TKDND_AVAILABLE:
            # Use tkinterdnd2 if available
            def on_drop(event):
                data = event.data
                files = self.parse_drop_data(data)
                if not files:
                    return
                
                if isinstance(widget, scrolledtext.ScrolledText):
                    current = widget.get(1.0, tk.END).strip()
                    if current:
                        widget.insert(tk.END, '\n')
                    widget.insert(tk.END, '\n'.join(files))
                elif isinstance(widget, ttk.Entry):
                    if param_type in ['file', 'directory']:
                        widget.delete(0, tk.END)
                        widget.insert(0, files[0])
                    else:
                        widget.delete(0, tk.END)
                        widget.insert(0, ' '.join(files))
                
                self.update_command_preview()
                return 'break'
            
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', on_drop)
            except:
                pass
        else:
            # Fallback: Add a right-click context menu to browse for files
            def show_context_menu(event):
                menu = tk.Menu(widget, tearoff=0)
                
                if isinstance(widget, scrolledtext.ScrolledText):
                    menu.add_command(label="Add Files...", command=lambda: self.browse_files_for_widget(widget, param_type))
                    menu.add_command(label="Clear", command=lambda: widget.delete(1.0, tk.END))
                elif isinstance(widget, ttk.Entry):
                    menu.add_command(label="Browse...", command=lambda: self.browse_files_for_widget(widget, param_type))
                    menu.add_command(label="Clear", command=lambda: widget.delete(0, tk.END))
                
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()
            
            # Bind right-click
            if sys.platform == 'darwin':
                widget.bind('<Button-2>', show_context_menu)
                widget.bind('<Control-Button-1>', show_context_menu)
            else:
                widget.bind('<Button-3>', show_context_menu)
    
    def browse_files_for_widget(self, widget, param_type):
        """Open file dialog to select files for a widget."""
        if param_type == 'directory':
            path = filedialog.askdirectory()
            if path:
                if isinstance(widget, scrolledtext.ScrolledText):
                    current = widget.get(1.0, tk.END).strip()
                    if current:
                        widget.insert(tk.END, '\n')
                    widget.insert(tk.END, path)
                else:
                    widget.delete(0, tk.END)
                    widget.insert(0, path)
                self.update_command_preview()
        else:
            paths = filedialog.askopenfilenames()
            if paths:
                if isinstance(widget, scrolledtext.ScrolledText):
                    current = widget.get(1.0, tk.END).strip()
                    if current:
                        widget.insert(tk.END, '\n')
                    widget.insert(tk.END, '\n'.join(paths))
                else:
                    widget.delete(0, tk.END)
                    widget.insert(0, paths[0] if len(paths) == 1 else ' '.join(paths))
                self.update_command_preview()
    
    def parse_drop_data(self, data):
        """Parse dropped file data."""
        files = []
        if not data:
            return files
        
        pattern = r'\{([^}]+)\}|(\S+)'
        matches = re.findall(pattern, str(data))
        
        for match in matches:
            path = match[0] if match[0] else match[1]
            if path:
                path = path.strip()
                if path.startswith('file://'):
                    path = path[7:]
                files.append(path)
        
        return files
    
    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        tooltip = None
        
        def show_tooltip(event):
            nonlocal tooltip
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                           background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                           font=("tahoma", "8", "normal"))
            label.pack(ipadx=1)
        
        def hide_tooltip(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None
        
        widget.bind('<Enter>', show_tooltip)
        widget.bind('<Leave>', hide_tooltip)
    
    def load_bookmarks(self):
        """Load location bookmarks from file."""
        if os.path.exists(self.bookmarks_file):
            try:
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading bookmarks: {e}")
                return {}
        return {}
    
    def save_bookmarks(self):
        """Save location bookmarks to file."""
        try:
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.location_bookmarks, f, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save bookmarks: {e}")
    
    def save_location_bookmark(self):
        """Save current location fields as a bookmark."""
        # Create dialog to get bookmark name
        dialog = tk.Toplevel(self.root)
        dialog.title("Save Location Bookmark")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Name label and entry
        ttk.Label(dialog, text="Bookmark Name:").pack(pady=(20, 5))
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=40)
        name_entry.pack(pady=5)
        name_entry.focus()
        
        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a bookmark name.", parent=dialog)
                return
            
            # Collect current location values
            bookmark_data = {}
            location_params = ['gps_coords', 'city', 'state', 'country', 'country_code', 'coverage']
            
            for param in location_params:
                if param in self.param_widgets:
                    widget = self.param_widgets[param]
                    if hasattr(widget, 'get'):
                        value = widget.get()
                        if isinstance(value, str):
                            value = value.strip()
                        if value:
                            bookmark_data[param] = value
            
            if not bookmark_data:
                messagebox.showwarning("Warning", "No location data to save.", parent=dialog)
                return
            
            # Save bookmark
            self.location_bookmarks[name] = bookmark_data
            self.save_bookmarks()
            
            # Update dropdown
            if 'location_bookmark' in self.param_widgets:
                bookmark_names = [''] + list(self.location_bookmarks.keys())
                # Find the combobox widget (it's a StringVar, need to find the actual widget)
                for widget in self.param_frames.get('location_bookmark', ttk.Frame()).winfo_children():
                    if isinstance(widget, ttk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Combobox):
                                child['values'] = bookmark_names
                                child.set(name)
                                break
            
            messagebox.showinfo("Success", f"Location bookmark '{name}' saved!", parent=dialog)
            dialog.destroy()
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key
        name_entry.bind('<Return>', lambda e: save())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def load_location_bookmark(self):
        """Load a location bookmark and populate location fields."""
        if 'location_bookmark' not in self.param_widgets:
            return
        
        bookmark_var = self.param_widgets['location_bookmark']
        bookmark_name = bookmark_var.get().strip()
        
        if not bookmark_name:
            return
        
        if bookmark_name not in self.location_bookmarks:
            messagebox.showwarning("Warning", f"Bookmark '{bookmark_name}' not found.")
            return
        
        # Load bookmark data
        bookmark_data = self.location_bookmarks[bookmark_name]
        
        # Populate location fields
        location_params = ['gps_coords', 'city', 'state', 'country', 'country_code', 'coverage']
        
        for param in location_params:
            if param in self.param_widgets and param in bookmark_data:
                widget = self.param_widgets[param]
                value = bookmark_data[param]
                
                # Clear and set new value
                if hasattr(widget, 'delete'):
                    widget.delete(0, tk.END)
                    widget.insert(0, value)
                elif hasattr(widget, 'set'):
                    widget.set(value)
        
        # Update command preview
        self.update_command_preview()
        
        # Show success message
        self.status_var.set(f"✓ Loaded bookmark: {bookmark_name}")


def main():
    if TKDND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = ImageProcessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
