import logging, traceback
import sqlite3
import os
import time

from config import DB_PATH

def get_connection():
    # allow cross-thread use + wait for lock release
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # better concurrency
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # --- Duplicates table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS duplicates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER,
            file_path TEXT,
            file_hash TEXT,
            file_size INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hash ON duplicates(file_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scan ON duplicates(scan_id)")

    # --- Scans (history) table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            total_files INTEGER,
            total_duplicates INTEGER,
            total_size_saved INTEGER
        )
    """)

    # add a small meta table to track schema version
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # set a schema version if not exists
    cur.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')")

    # --- Exclusions table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            is_folder INTEGER NOT NULL CHECK(is_folder IN (0,1))
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_excl_folder ON exclusions(is_folder)")

    conn.commit()
    conn.close()


def start_scan():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO scans (timestamp, total_files, total_duplicates, total_size_saved) VALUES (?, ?, ?, ?)",
                (int(time.time()), 0, 0, 0))
    scan_id = cur.lastrowid
    conn.commit()
    conn.close()
    return scan_id

def finish_scan(scan_id, total_files, total_duplicates, total_size_saved):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE scans
        SET total_files=?, total_duplicates=?, total_size_saved=?
        WHERE id=?
    """, (total_files, total_duplicates, total_size_saved, scan_id))
    conn.commit()
    conn.close()

# --- Exclusion rules ---
def add_exclusion(pattern, is_folder=True):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO exclusions (pattern, is_folder) VALUES (?, ?)",
        (pattern, 1 if is_folder else 0)
    )
    conn.commit()
    conn.close()

def remove_exclusion(pattern):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM exclusions WHERE pattern = ?",
        (pattern,)
    )
    conn.commit()
    conn.close()

def get_exclusions():
    """Return a list of all exclusion patterns."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT pattern FROM exclusions")
    rows = [row[0] for row in cur.fetchall()]
    conn.close()
    return rows

# --- Duplicates ---
def insert_duplicate(scan_id, file_path, file_hash, file_size):
    """Insert one duplicate file record into DB."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO duplicates (scan_id, file_path, file_hash, file_size) VALUES (?, ?, ?, ?)",
        (scan_id, file_path, file_hash, file_size),
    )
    conn.commit()
    conn.close()


def get_all_duplicates(scan_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            GROUP_CONCAT(file_path, CHAR(31)) AS joined_paths,
            file_size
        FROM duplicates
        WHERE scan_id = ?
        GROUP BY file_hash, file_size
        HAVING COUNT(*) > 1
    """, (scan_id,))
    rows = cur.fetchall()
    conn.close()
    return rows




def safe_get_all_duplicates(scan_id):
    """Return list of (joined_paths, size). Guaranteed to return list even on error."""
    try:
        if not scan_id:
            logging.debug("safe_get_all_duplicates called with no scan_id -> returning [].")
            return []
        rows = get_all_duplicates(scan_id)
        logging.debug("safe_get_all_duplicates returned %d rows for scan_id=%s", len(rows), scan_id)

        normalized = []
        for row in rows:
            try:
                # Expect (joined_paths, size) exactly
                if not row:
                    continue
                # if row has >2 columns use the last two
                if len(row) >= 2:
                    joined_paths = row[-2]
                    size = row[-1]
                else:
                    # malformed, skip
                    logging.debug("Dropping malformed row (too few cols): %r", row)
                    continue

                if joined_paths is None or size is None:
                    logging.debug("Dropping row with missing parts: %r", row)
                    continue

                # ensure it's a string and number
                joined_paths = str(joined_paths)
                size = int(size)
                normalized.append((joined_paths, size))
            except Exception as inner:
                logging.debug("Failed to normalize row %r: %s", row, inner)
                continue

        return normalized

    except Exception as e:
        logging.error("get_all_duplicates(scan_id=%s) failed: %s", scan_id, e)
        traceback.print_exc()
        return []




def delete_duplicate_group(file_hash, scan_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM duplicates WHERE file_hash=? AND scan_id=?", (file_hash, scan_id))
    conn.commit()
    conn.close()

def clear_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM duplicates")
    cur.execute("DELETE FROM scans")
    conn.commit()
    conn.close()

def clear_duplicates():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM duplicates")
    conn.commit()
    conn.close()



# --- Scan history ---
def get_scan_history(limit=None):
    conn = get_connection()
    cur = conn.cursor()
    if limit:
        cur.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))
    else:
        cur.execute("SELECT * FROM scans ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def remove_duplicate_by_path(scan_id, file_path):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM duplicates WHERE scan_id=? AND file_path LIKE ?",
        (scan_id, f"%{file_path}%")
    )
    conn.commit()
    conn.close()

