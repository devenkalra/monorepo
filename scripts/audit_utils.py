#!/usr/bin/env python3
"""audit_utils.py - Shared audit logging utilities for media management scripts.

Provides consistent audit logging across all media management scripts.
Audit logs are append-only and provide a record of all operations for
disaster recovery and database reconstruction.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_audit_logger(script_name: str, audit_file: Optional[str] = None) -> logging.Logger:
    """Setup audit logger for a script.
    
    Args:
        script_name: Name of the script (e.g., 'index_media', 'move_media')
        audit_file: Path to audit log file. If None, uses default location.
    
    Returns:
        Configured logger instance
    """
    # Determine audit file path
    if audit_file is None:
        # Default to script directory
        script_dir = Path(__file__).parent
        audit_file = script_dir / f"{script_name}_audit.log"
    else:
        audit_file = Path(audit_file)
    
    # Create logger
    logger_name = f"audit.{script_name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create file handler (append mode)
    file_handler = logging.FileHandler(audit_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Create formatter
    # Format: timestamp | script | action | details
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(file_handler)
    
    # Don't propagate to root logger
    logger.propagate = False
    
    return logger


def log_session_start(logger: logging.Logger, script_name: str, args: dict):
    """Log the start of a script session.
    
    Args:
        logger: Audit logger
        script_name: Name of the script
        args: Dictionary of command-line arguments
    """
    # Filter out sensitive or overly verbose args
    safe_args = {k: v for k, v in args.items() 
                 if k not in ['password', 'token', 'secret']}
    
    logger.info(f"SESSION_START | script={script_name} | args={safe_args}")


def log_session_end(logger: logging.Logger, script_name: str, stats: dict):
    """Log the end of a script session with statistics.
    
    Args:
        logger: Audit logger
        script_name: Name of the script
        stats: Dictionary of statistics (files processed, errors, etc.)
    """
    logger.info(f"SESSION_END | script={script_name} | stats={stats}")


def log_file_indexed(logger: logging.Logger, file_path: str, file_id: int, 
                     volume: str, file_hash: str, action: str = 'indexed'):
    """Log a file being indexed.
    
    Args:
        logger: Audit logger
        file_path: Full path to file
        file_id: Database file ID
        volume: Volume tag
        file_hash: File hash
        action: Action taken ('indexed', 'updated', 'skipped')
    """
    logger.info(f"FILE_INDEXED | action={action} | file_id={file_id} | "
                f"path={file_path} | volume={volume} | hash={file_hash}")


def log_file_moved(logger: logging.Logger, source_path: str, dest_path: str,
                  file_id: int, volume: str, file_hash: str, action: str):
    """Log a file being moved.
    
    Args:
        logger: Audit logger
        source_path: Original file path
        dest_path: New file path
        file_id: Database file ID
        volume: Volume tag
        file_hash: File hash
        action: Action taken ('moved', 'updated', 'inserted', 'skipped')
    """
    logger.info(f"FILE_MOVED | action={action} | file_id={file_id} | "
                f"source={source_path} | dest={dest_path} | "
                f"volume={volume} | hash={file_hash}")


def log_file_duplicate(logger: logging.Logger, file_path: str, action: str,
                      file_hash: str, reason: str, dest_path: Optional[str] = None):
    """Log a duplicate file being handled.
    
    Args:
        logger: Audit logger
        file_path: File path
        action: Action taken ('moved', 'copied', 'skipped')
        file_hash: File hash
        reason: Reason for action
        dest_path: Destination path if moved/copied
    """
    dest_info = f" | dest={dest_path}" if dest_path else ""
    logger.info(f"FILE_DUPLICATE | action={action} | path={file_path} | "
                f"hash={file_hash} | reason={reason}{dest_info}")


def log_file_removed(logger: logging.Logger, file_path: str, file_id: int,
                    file_hash: str, reason: str, dest_path: Optional[str] = None):
    """Log a file being removed from database.
    
    Args:
        logger: Audit logger
        file_path: Original file path
        file_id: Database file ID
        file_hash: File hash
        reason: Reason for removal
        dest_path: Destination path if moved
    """
    dest_info = f" | dest={dest_path}" if dest_path else ""
    logger.info(f"FILE_REMOVED | file_id={file_id} | path={file_path} | "
                f"hash={file_hash} | reason={reason}{dest_info}")


def log_database_operation(logger: logging.Logger, operation: str, 
                          table: str, record_id: Optional[int] = None,
                          details: Optional[str] = None):
    """Log a database operation.
    
    Args:
        logger: Audit logger
        operation: Operation type ('INSERT', 'UPDATE', 'DELETE')
        table: Table name
        record_id: Record ID if applicable
        details: Additional details
    """
    id_info = f" | id={record_id}" if record_id else ""
    detail_info = f" | details={details}" if details else ""
    logger.info(f"DB_OPERATION | op={operation} | table={table}{id_info}{detail_info}")


def log_error(logger: logging.Logger, error_type: str, error_msg: str,
             context: Optional[str] = None):
    """Log an error.
    
    Args:
        logger: Audit logger
        error_type: Type of error
        error_msg: Error message
        context: Additional context
    """
    context_info = f" | context={context}" if context else ""
    logger.error(f"ERROR | type={error_type} | message={error_msg}{context_info}")


def log_skip(logger: logging.Logger, file_path: str, reason: str, details: Optional[str] = None):
    """Log a file being skipped.
    
    Args:
        logger: Audit logger
        file_path: File path
        reason: Skip reason
        details: Additional details
    """
    detail_info = f" | details={details}" if details else ""
    logger.info(f"FILE_SKIPPED | path={file_path} | reason={reason}{detail_info}")


# Convenience function for scripts
def get_audit_logger(script_name: str, audit_file: Optional[str] = None) -> logging.Logger:
    """Get or create audit logger for a script.
    
    This is the main entry point for scripts to get an audit logger.
    
    Args:
        script_name: Name of the script (e.g., 'index_media')
        audit_file: Optional custom audit file path
    
    Returns:
        Configured audit logger
    
    Example:
        from audit_utils import get_audit_logger, log_session_start
        
        audit_log = get_audit_logger('my_script')
        log_session_start(audit_log, 'my_script', vars(args))
    """
    return setup_audit_logger(script_name, audit_file)
