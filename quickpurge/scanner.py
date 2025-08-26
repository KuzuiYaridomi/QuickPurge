import os
import hashlib
from config import HASH_CHUNK_SIZE
from .utils import log, file_chunks, notify
from . import database
from .exclusion_rules import should_exclude
from .safe_delete import safe_delete

SAFE_DELETE_DURING_SCAN = False  # True to auto-archive duplicates as found
CHUNK_SIZE = HASH_CHUNK_SIZE


# ---- Helper: progress emitter ----
def _emit(on_progress, **info):
    """Safely emit progress info back to UI."""
    if on_progress:
        try:
            on_progress(info)
        except Exception:
            pass


def _is_cancelled(cancel_flag):
    """Support both dict-style and callable cancel flags."""
    try:
        if cancel_flag is None:
            return False
        if callable(cancel_flag):
            return cancel_flag()
        if isinstance(cancel_flag, dict):
            return cancel_flag.get("cancel", False)
    except Exception:
        return False
    return False


def calculate_hash(file_path):
    """Calculate SHA256 hash in chunks to save memory (works for any file type)."""
    sha256 = hashlib.sha256()
    try:
        # Normalize path (handles mixed slashes, relative paths)
        file_path = os.path.abspath(os.path.normpath(file_path))

        # Try opening in binary mode (works for images, videos, any type)
        with open(file_path, "rb") as f:
            for chunk in file_chunks(f, CHUNK_SIZE):
                sha256.update(chunk)

        return sha256.hexdigest()

    except PermissionError:
        log(f"Skipping (no permission): {file_path}")
        return None

    except FileNotFoundError:
        log(f"Skipping (not found): {file_path}")
        return None

    except OSError as e:
        # Special handling for locked/in-use files (common with videos/photos in editors)
        if e.errno == 22:  # Invalid argument (often bad path/locked file)
            log(f"Skipping (invalid/locked): {file_path}")
        else:
            log(f"Skipping (OS error {e.errno}): {file_path} -> {e}")
        return None

    except Exception as e:
        # Catch-all safety (shouldn't happen often)
        log(f"Unexpected error hashing {file_path}: {e}")
        return None


def scan_folder(folder_path, on_progress=None, cancel_flag=None):
    """
    Scan one or more folders and log duplicates with history support.
    - folder_path: str or list of str
    - on_progress: callback(info: dict)
    - cancel_flag: dict or callable -> bool (if True, abort scan)
    """
    # Normalize folder list
    if isinstance(folder_path, str):
        folders = [folder_path]
    elif isinstance(folder_path, (list, tuple)):
        folders = list(folder_path)
    else:
        raise ValueError("folder_path must be a string or list of strings")

    scan_id = database.start_scan()
    database.clear_duplicates()
    total_files = 0
    files_by_size = {}

    # ---- Phase 1: group by file size ----
    for folder in folders:
        log(f"Scanning folder: {folder}")
        _emit(on_progress, stage="start", folder=folder)

        for root, dirs, files in os.walk(folder):
            for file in files:
                if _is_cancelled(cancel_flag):
                    log("Scan cancelled during grouping.")
                    _emit(on_progress, stage="done", scan_id=None,
                          files_scanned=total_files, total_files=total_files)
                    return None

                file_path = os.path.join(root, file)
                if should_exclude(file_path):
                    continue
                try:
                    size = os.path.getsize(file_path)
                    files_by_size.setdefault(size, []).append(file_path)
                    total_files += 1

                    if total_files % 200 == 0:
                        _emit(on_progress, stage="grouping",
                              files_scanned=total_files, total_files=total_files, path=file_path)
                except (PermissionError, FileNotFoundError):
                    continue

    # ---- Phase 2: hash and detect duplicates ----
    total_duplicates = 0
    total_size_saved = 0
    processed_files = 0

    for size, paths in files_by_size.items():
        if len(paths) < 2:
            continue

        hashes = {}
        for file_path in paths:
            if _is_cancelled(cancel_flag):
                log("Scan cancelled during hashing.")
                _emit(on_progress, stage="done", scan_id=None,
                      files_scanned=processed_files, total_files=total_files)
                return None

            processed_files += 1
            _emit(
                on_progress,
                stage="hashing",
                path=file_path,
                files_scanned=processed_files,
                total_files=total_files,
                progress=int(processed_files / total_files * 100) if total_files else 0,
            )

            file_hash = calculate_hash(file_path)
            if not file_hash:
                continue

            if file_hash in hashes:
                # ✅ Always insert in consistent format: (scan_id, file_hash, joined_paths, size)
                original_path = hashes[file_hash]
                dup_path = file_path
                # Insert both rows (original + duplicate) in the DB in correct API order
                database.insert_duplicate(scan_id, original_path, file_hash, size)
                database.insert_duplicate(scan_id, dup_path, file_hash, size)

                total_duplicates += 1
                total_size_saved += size
    
            else:
                hashes[file_hash] = file_path

    # ---- Finish ----
    database.finish_scan(scan_id, total_files, total_duplicates, total_size_saved)
    log(f"Scan complete: {total_files} files, {total_duplicates} duplicates, {total_size_saved} bytes saved.")
    try:
        notify(
            "QuickPurge - Scan Complete",
            f"Scanned {total_files} files, found {total_duplicates} duplicates",
        )
    except Exception:
        pass

    _emit(
        on_progress,
        stage="done",
        scan_id=scan_id,
        files_scanned=total_files,
        total_files=total_files,
        total_duplicates=total_duplicates,
        total_size_saved=total_size_saved,
    )
    return scan_id


def scan_entire_system(on_progress=None, cancel_flag=None):
    """Scan all drives or root directories for duplicates, skipping exclusions.
       Returns last scan_id or None if cancelled."""
    drives = []
    if os.name == "nt":  # Windows
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:/")
            bitmask >>= 1
    else:  # macOS/Linux
        drives = ["/"]

    last_id = None
    for drive in drives:
        if should_exclude(drive):
            continue
        if _is_cancelled(cancel_flag):
            log("Scan cancelled before drive scan.")
            _emit(on_progress, stage="done", scan_id=None, files_scanned=0, total_files=0)
            return None

        log(f"Scanning drive: {drive}")
        _emit(on_progress, stage="drive", drive=drive)
        sid = scan_folder(drive, on_progress=on_progress, cancel_flag=cancel_flag)
        if sid:
            last_id = sid
    return last_id










