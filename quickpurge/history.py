from . import database
from .utils import log
import datetime

def get_scan_history(limit=20):
    """
    Retrieve recent scan history from the database.
    :param limit: Max number of scans to return
    :return: List of scan history dicts
    """
    rows = database.get_scan_history(limit)
    history = []
    for row in rows:
        history.append({
            "scan_id": row[0],
            "timestamp": datetime.datetime.fromtimestamp(row[1]).strftime("%Y-%m-%d %H:%M:%S"),
            "total_files": row[2],
            "total_duplicates": row[3],
            "total_size_saved": row[4]
        })
    return history

def display_scan_history():
    """
    Prints the scan history to the console.
    (In the UI, this will be displayed in the History tab)
    """
    history = get_scan_history()
    if not history:
        log("No scan history found.")
        return

    log("=== Scan History ===")
    for record in history:
        log(f"ID: {record['scan_id']}, Date: {record['timestamp']}, "
            f"Files: {record['total_files']}, Duplicates: {record['total_duplicates']}, "
            f"Space Saved: {record['total_size_saved']} bytes")

