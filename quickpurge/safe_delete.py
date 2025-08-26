import os
import shutil
import time
import json
from .utils import log
from .exclusion_rules import should_exclude


# Archive folder in the user's home directory
ARCHIVE_DIR = os.path.join(os.path.expanduser("~"), "QuickPurge_Archive")


def ensure_archive_folder():
    """Creates the archive folder if it doesn't exist."""
    try:
        if not os.path.exists(ARCHIVE_DIR):
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            log(f"Archive folder created at: {ARCHIVE_DIR}")
    except Exception as e:
        log(f"Failed to create archive folder: {e}")


def safe_delete(file_path):
    """
    Moves the file to the archive folder instead of deleting it permanently.
    Saves metadata so it can be restored later.
    Returns True if successful, False otherwise.
    """
    try:
        ensure_archive_folder()

        if should_exclude(file_path):
            log(f"Refused to archive protected file: {file_path}")
            return False

        if not os.path.exists(file_path):
            log(f"File not found for archiving: {file_path}")
            return False

        if not os.path.exists(file_path):
            log(f"File not found for archiving: {file_path}")
            return False

        # Unique archive filename to prevent overwriting
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        millis = int(time.time() * 1000) % 1000
        base_name = os.path.basename(file_path)
        archive_name = f"{timestamp}-{millis}_{base_name}"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)

        # Move file to archive
        shutil.move(file_path, archive_path)
        log(f"File moved to archive: {file_path} -> {archive_path}")

        # Save original path metadata
        meta_path = archive_path + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump({"original_path": file_path}, mf)

        return True

    except Exception as e:
        log(f"Failed to archive {file_path}: {e}")
        return False


def permanent_delete(file_path):
    """
    Permanently deletes a file in archive (use with caution).
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            # Remove metadata too if exists
            meta_path = file_path + ".meta.json"
            if os.path.exists(meta_path):
                os.remove(meta_path)
            log(f"File permanently deleted: {file_path}")
            return True
        else:
            log(f"File not found for permanent deletion: {file_path}")
            return False
    except Exception as e:
        log(f"Failed to permanently delete {file_path}: {e}")
        return False


def restore_file(archive_file):
    """
    Restores a file from archive back to its original path.
    Returns True if successful, False otherwise.
    """
    try:
        meta_path = archive_file + ".meta.json"
        if not os.path.exists(meta_path):
            log(f"No metadata found for restoring: {archive_file}")
            return False

        with open(meta_path, "r", encoding="utf-8") as mf:
            metadata = json.load(mf)
        original_path = metadata.get("original_path")

        if not original_path:
            log(f"No original path in metadata for {archive_file}")
            return False

        # Ensure target directory exists
        os.makedirs(os.path.dirname(original_path), exist_ok=True)

        shutil.move(archive_file, original_path)
        os.remove(meta_path)  # remove metadata after restore
        log(f"Restored file: {archive_file} -> {original_path}")
        return True

    except Exception as e:
        log(f"Failed to restore {archive_file}: {e}")
        return False

