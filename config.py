import os

# ------------------------
# App Information
# ------------------------
APP_NAME = "QuickPurge"
APP_VERSION = "1.0.0"
DEVELOPER = "KuzuiYaridomi"

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "quickpurge.db")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
THUMBNAIL_CACHE = os.path.join(BASE_DIR, "assets", "thumbnails")

# Ensure required folders exist
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_CACHE, exist_ok=True)

# ------------------------
# Hashing Settings
# ------------------------
HASH_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks to save memory

# ------------------------
# AMD Adrenalin Theme Colors
# ------------------------
THEME_BG = "#0D0D0D"       # Very dark background
THEME_PANEL = "#1A1A1A"    # Slightly lighter for panels
THEME_ACCENT = "#E50914"   # AMD Red
THEME_TEXT = "#FFFFFF"     # White text
THEME_SUBTEXT = "#AAAAAA"  # Gray for secondary info

# ------------------------
# UI Settings
# ------------------------
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 11
WINDOW_SIZE = (1000, 700)
TRANSPARENCY = 0.92  # Slightly see-through
