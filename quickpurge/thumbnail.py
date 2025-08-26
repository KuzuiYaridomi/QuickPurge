import os
from PIL import Image
import io

# Thumbnail cache (size-limited)
_thumbnail_cache = {}
MAX_CACHE_ITEMS = 50  # Keep memory low

THUMBNAIL_SIZE = (128, 128)  # Small for UI preview

# --- App Icon Paths ---
ASSETS_DIR = os.path.join("assets", "thumbnails")
ICON_PNG = os.path.join(ASSETS_DIR, "quickpurge logo.png")
ICON_ICO = os.path.join(ASSETS_DIR, "quickpurgelogo.ico")  # recommended for packaged .exe


def get_thumbnail(file_path):
    """
    Returns a thumbnail (in bytes) for the given image file.
    Uses caching to avoid reloading the same file repeatedly.
    """
    if not os.path.exists(file_path):
        return None

    # Check cache
    if file_path in _thumbnail_cache:
        return _thumbnail_cache[file_path]

    try:
        # Load image in memory-efficient way
        with Image.open(file_path) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            byte_arr = io.BytesIO()
            img.save(byte_arr, format="PNG")
            thumbnail_bytes = byte_arr.getvalue()

            # Add to cache (with size limit)
            if len(_thumbnail_cache) >= MAX_CACHE_ITEMS:
                _thumbnail_cache.pop(next(iter(_thumbnail_cache)))  # Remove oldest

            _thumbnail_cache[file_path] = thumbnail_bytes
            return thumbnail_bytes

    except (OSError, IOError):
        return None


def clear_cache():
    """Manually clears the thumbnail cache."""
    _thumbnail_cache.clear()


def get_app_icon():
    """
    Returns the best available app icon path.
    Use PNG for PySimpleGUI window, ICO for PyInstaller executables.
    """
    if os.path.exists(ICON_ICO):
        return ICON_ICO
    elif os.path.exists(ICON_PNG):
        return ICON_PNG
    else:
        return None


