import os
import sqlite3
from quickpurge import database, scanner
import config

def test_scan_finds_duplicates(tmp_path, monkeypatch):
    # Use a temp DB
    tmp_db = tmp_path / "test_quickpurge.db"
    monkeypatch.setattr(config, "DB_PATH", str(tmp_db))
    # Re-init DB to use the test DB path
    database.init_db()

    # Prepare files: create two identical files and one unique file
    d = tmp_path / "folder"
    d.mkdir()
    f1 = d / "a.txt"
    f2 = d / "b.txt"
    f3 = d / "c.txt"
    f1.write_bytes(b"duplicate content")
    f2.write_bytes(b"duplicate content")  # identical to f1
    f3.write_bytes(b"different")

    # Run scan (scanner.scan_folder should return scan_id)
    scan_id = scanner.scan_folder(str(d))

    # Fetch duplicates recorded in DB for this scan
    rows = database.get_all_duplicates(scan_id)
    # Expect at least one duplicate group (hash) with two files
    assert len(rows) >= 1
    # One of the returned rows should contain both file paths
    found = False
    for row in rows:
        # row example: (file_hash, 'path1,path2', file_size) depending on implementation
        # if your get_all_duplicates returns rows differently, adapt the check
        # We'll check the concatenated paths string (or tuple) contains both paths
        joined = ",".join(row[1].split(",")) if isinstance(row[1], str) else row[1]
        if str(f1) in joined and str(f2) in joined:
            found = True
    assert found, "Scanner did not record the identical files as duplicates"
