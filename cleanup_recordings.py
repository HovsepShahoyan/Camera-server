#!/usr/bin/env python3
"""
Recording Cleanup Script

This script cleans up old continuous recordings while preserving event recordings.
Event recordings (with 'keep': True in metadata) are never deleted.

Usage:
    python cleanup_recordings.py --config config.json --max-age 7
    
    --max-age: Maximum age in days for continuous recordings (default: 7)
"""

import os
import json
import argparse
import time
from datetime import datetime, timedelta
from loguru import logger


def load_config(config_path):
    """Load configuration file"""
    with open(config_path, 'r') as f:
        return json.load(f)


def get_recording_age_days(metadata):
    """Get the age of a recording in days"""
    end_time = metadata.get('end_time')
    if end_time:
        age_seconds = time.time() - end_time
        return age_seconds / (24 * 3600)
    return 0


def should_delete(metadata, max_age_days):
    """
    Determine if a recording should be deleted.
    
    Rules:
    - Never delete if 'keep' is True
    - Never delete if type starts with 'event'
    - Delete continuous recordings older than max_age_days
    """
    # Never delete if explicitly marked to keep
    if metadata.get('keep', False):
        return False
    
    # Never delete event recordings
    rec_type = metadata.get('type', '')
    if rec_type.startswith('event'):
        return False
    
    # Check age for continuous recordings
    age_days = get_recording_age_days(metadata)
    return age_days > max_age_days


def cleanup_recordings(base_dir, max_age_days=7, dry_run=False):
    """
    Clean up old continuous recordings.
    
    Args:
        base_dir: Base recordings directory
        max_age_days: Maximum age in days for continuous recordings
        dry_run: If True, only report what would be deleted
    """
    deleted_count = 0
    deleted_size = 0
    kept_count = 0
    
    logger.info(f"Starting cleanup of recordings in {base_dir}")
    logger.info(f"Max age for continuous recordings: {max_age_days} days")
    logger.info(f"Dry run: {dry_run}")
    
    if not os.path.exists(base_dir):
        logger.warning(f"Base directory does not exist: {base_dir}")
        return
    
    # Walk through all recordings
    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            if not filename.endswith('.json'):
                continue
                
            metadata_path = os.path.join(root, filename)
            video_path = metadata_path.replace('.json', '.mp4')
            
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                if should_delete(metadata, max_age_days):
                    # Calculate size
                    size = 0
                    if os.path.exists(video_path):
                        size = os.path.getsize(video_path)
                    
                    age_days = get_recording_age_days(metadata)
                    
                    if dry_run:
                        logger.info(f"Would delete: {video_path} "
                                   f"(type={metadata.get('type')}, "
                                   f"age={age_days:.1f} days, "
                                   f"size={size/1024/1024:.1f} MB)")
                    else:
                        # Delete video file
                        if os.path.exists(video_path):
                            os.remove(video_path)
                        # Delete metadata file
                        os.remove(metadata_path)
                        logger.info(f"Deleted: {video_path}")
                    
                    deleted_count += 1
                    deleted_size += size
                else:
                    kept_count += 1
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in {metadata_path}: {e}")
            except Exception as e:
                logger.error(f"Error processing {metadata_path}: {e}")
    
    # Clean up empty directories
    if not dry_run:
        for root, dirs, files in os.walk(base_dir, topdown=False):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        logger.debug(f"Removed empty directory: {dir_path}")
                except OSError:
                    pass
    
    logger.info(f"Cleanup complete:")
    logger.info(f"  Deleted: {deleted_count} recordings ({deleted_size/1024/1024:.1f} MB)")
    logger.info(f"  Kept: {kept_count} recordings")


def main():
    parser = argparse.ArgumentParser(description='Clean up old recordings')
    parser.add_argument('--config', default='config.json',
                       help='Path to config file')
    parser.add_argument('--max-age', type=int, default=7,
                       help='Maximum age in days for continuous recordings')
    parser.add_argument('--dry-run', action='store_true',
                       help='Only report what would be deleted')
    parser.add_argument('--base-dir', default=None,
                       help='Override base directory from config')
    
    args = parser.parse_args()
    
    # Set up logging
    logger.add("cleanup.log", rotation="1 week", retention="4 weeks")
    
    # Load config
    if args.base_dir:
        base_dir = args.base_dir
    else:
        config = load_config(args.config)
        base_dir = config['recording'].get('base_dir', './recordings')
    
    cleanup_recordings(base_dir, args.max_age, args.dry_run)


if __name__ == "__main__":
    main()