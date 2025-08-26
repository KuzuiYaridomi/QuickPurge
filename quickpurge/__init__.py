"""
QuickPurge package initializer.
Expose main modules for convenient imports in tests and other code.
"""

__version__ = "1.0.0"
__author__ = "KuzuiYaridomi"

# Re-export package submodules but DO NOT import UI at package import time
from . import scanner, database, safe_delete, utils, exclusion_rules, thumbnail, history
# Note: ui is intentionally NOT imported here to avoid GUI dependency during tests

__all__ = [
    "scanner",
    "database",
    "safe_delete",
    "utils",
    "exclusion_rules",
    "thumbnail",
    "history",
]

