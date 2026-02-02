#!/usr/bin/env python3
"""
Setup script for Photo Management Tools
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_file(filename):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

setup(
    name='photo-management-tools',
    version='1.0.0',
    description='Comprehensive photo and media management toolkit',
    long_description=read_file('DEPLOYMENT_README.md'),
    long_description_content_type='text/markdown',
    author='Your Name',
    author_email='your.email@example.com',
    url='https://github.com/yourusername/photo-management-tools',
    
    # Package discovery
    packages=find_packages(exclude=['tests', 'htmlcov']),
    py_modules=[
        'apply_exif',
        'audit_utils',
        'command_runner',
        'convert_non_photos',
        'download_images',
        'find_location',
        'image_process',
        'index_media',
        'locate_in_db',
        'location_utils',
        'manage_dupes',
        'media_utils',
        'move_media',
        'remove_dupes',
        'show_exif',
    ],
    
    # Dependencies
    install_requires=[
        'Pillow>=10.0.0',
        'geopy>=2.3.0',
        'requests>=2.31.0',
        'PyYAML>=6.0',
    ],
    
    # Optional dependencies
    extras_require={
        'gui': ['tkinterdnd2>=0.3.0'],
        'dev': ['coverage>=7.0.0', 'pytest>=7.0.0'],
    },
    
    # Python version requirement
    python_requires='>=3.8',
    
    # Entry points for command-line scripts
    entry_points={
        'console_scripts': [
            'photo-index=index_media:main',
            'photo-apply-exif=apply_exif:main',
            'photo-move=move_media:main',
            'photo-locate=locate_in_db:main',
            'photo-show-exif=show_exif:main',
            'photo-find-location=find_location:main',
            'photo-manage-dupes=manage_dupes:main',
            'photo-remove-dupes=remove_dupes:main',
            'photo-gui=image_process:main',
        ],
    },
    
    # Package data
    package_data={
        '': ['*.yaml', '*.json', '*.md'],
    },
    
    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Multimedia :: Graphics',
        'Topic :: System :: Archiving',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    
    # Keywords
    keywords='photo media management exif metadata indexing',
)
