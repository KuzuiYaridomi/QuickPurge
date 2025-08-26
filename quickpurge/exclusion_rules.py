# quickpurge/exclusion_rules.py
import os
import sys
import logging
from .utils import log
from . import database

# --- Default protected folders & filetypes (adjust if you want) ---
# --- Default protected folders & filetypes (adjust if you want) ---
DEFAULT_PROTECTED_FOLDERS = []

if os.name == "nt":  # Windows
    DEFAULT_PROTECTED_FOLDERS.extend([
        os.path.expandvars(r"%SystemRoot%"),              # C:\Windows
        os.path.expandvars(r"%ProgramFiles%"),            # C:\Program Files
        os.environ.get("ProgramFiles(x86)"),              # C:\Program Files (x86)
        os.path.expanduser(r"~\AppData"),                 # AppData (Local + Roaming)
        os.path.expanduser(r"~\NTUSER.DAT"),              # User registry hive
        os.path.expanduser(r"~\NTUSER.DAT.LOG*"),         # Registry log files
    ])
else:  # Linux/macOS
    DEFAULT_PROTECTED_FOLDERS.extend([
        "/",                  # Root
        "/usr",               # System programs
        "/var",               # System data
        os.path.expanduser("~/.cache"),   # User cache
        os.path.expanduser("~/.config"),  # Configs
        os.path.expanduser("~/.local"),   # Local share
    ])

# Add common dev/build folders (always skipped)
DEV_PROTECTED = ["node_modules", ".git", "__pycache__", "build", "dist", "venv"]

# Normalize and drop Nones
DEFAULT_PROTECTED_FOLDERS = [p for p in DEFAULT_PROTECTED_FOLDERS if p]

# On Windows, also avoid Program Files (x86)
if os.name == "nt":
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        DEFAULT_PROTECTED_FOLDERS.append(pf86)

PROTECTED_EXTENSIONS = {
    ".exe", ".dll", ".sys", ".drv", ".lnk", ".com", ".msi", ".bat", ".cmd", ".ps1"
}

def insert_exclusion(pattern, is_folder=True):
    """Compatibility wrapper for existing DB functions."""
    database.add_exclusion(pattern, is_folder)

def delete_exclusion(pattern):
    database.remove_exclusion(pattern)

def list_exclusions():
    """Return DB rows — keep original shape used elsewhere."""
    # DB may store (pattern,) or (pattern,is_folder). Adapt if needed.
    rows = database.get_exclusions()
    # If DB get_exclusions returns just patterns, convert to (pattern, True)
    return [(r, True) if not isinstance(r, (list, tuple)) else r for r in rows]

# Windows attribute check
def _is_system_or_hidden_windows(path):
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_SYSTEM = 0x4
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        return False

def _is_hardlink_or_special(path):
    try:
        st = os.stat(path)
        return getattr(st, "st_nlink", 1) > 1
    except Exception:
        return False

def should_exclude(path):
    """
    Return True if file/folder should be excluded from scanning.
    Combines:
      - user-defined DB exclusions
      - default protected folders
      - protected file extensions
      - windows system/hidden attributes
      - hard-links and other special files
    """
    if not path:
        return True

    # Normalize
    try:
        path_norm = os.path.abspath(os.path.normpath(path))
    except Exception:
        path_norm = path

    # 1) DB exclusions
    try:
        exclusions = list_exclusions()  # list of (pattern, is_folder)
    except Exception:
        exclusions = []

    path_lower = path_norm.lower()

    for pattern, is_folder in exclusions:
        if not pattern:
            continue
        try:
            pat = os.path.abspath(os.path.normpath(pattern))
            if is_folder:
                # commonpath can raise if on different drives; handle safely
                try:
                    if os.path.commonpath([path_lower, pat.lower()]) == pat.lower():
                        return True
                except Exception:
                    if path_lower.startswith(pat.lower()):
                        return True
            else:
                if path_lower.endswith(pattern.lower()):
                    return True
        except Exception:
            # fallback string checks
            if is_folder and path_lower.startswith(pattern.lower()):
                return True
            if not is_folder and path_lower.endswith(pattern.lower()):
                return True

    # 2) Default protected folders
    for prot in DEFAULT_PROTECTED_FOLDERS:
        if not prot:
            continue
        try:
            prot_norm = os.path.abspath(os.path.normpath(prot)).lower()
            try:
                if os.path.commonpath([path_lower, prot_norm]) == prot_norm:
                    return True
            except Exception:
                if path_lower.startswith(prot_norm):
                    return True
        except Exception:
            continue

    # 3) Protected extensions
    _, ext = os.path.splitext(path_lower)
    if ext in PROTECTED_EXTENSIONS:
        return True

    # 4) Windows attributes
    if os.name == "nt":
        if _is_system_or_hidden_windows(path_norm):
            return True

    # 5) Hardlinks or special file types
    try:
        if _is_hardlink_or_special(path_norm):
            return True
    except Exception:
        pass

    return False

