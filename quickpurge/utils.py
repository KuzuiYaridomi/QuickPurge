import os
import datetime
from plyer import notification

def format_size(num_bytes):
    """Convert bytes to human-readable format (KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0

def format_time(timestamp):
    """Convert a UNIX timestamp to a readable string."""
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

def get_file_extension(file_path):
    """Return lowercase file extension without the dot."""
    return os.path.splitext(file_path)[1][1:].lower()

def is_hidden(filepath):
    """
    Check if a file or folder is hidden.
    Works on Windows and Unix-based systems.
    """
    name = os.path.basename(os.path.abspath(filepath))
    if name.startswith('.'):
        return True
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
        return attrs != -1 and (attrs & 2)  # FILE_ATTRIBUTE_HIDDEN
    except (AttributeError, ImportError):
        return False

def file_chunks(f, chunk_size):
    """Yield fixed-size chunks from an open binary file handle."""
    while True:
        data = f.read(chunk_size)
        if not data:
            break
        yield data

def log(message):
    """Print a log message with timestamp."""
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{time_str}] {message}")


def notify(title, message):
    """Send a desktop notification."""
    try:
        notification.notify(title=title, message=message, timeout=5)
    except Exception as e:
        print(f"[Notify Error] {e}")


