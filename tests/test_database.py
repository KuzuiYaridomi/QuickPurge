import os
from quickpurge import database
import config

def test_database_operations(tmp_path, monkeypatch):
    tmp_db = tmp_path / "db.sqlite"
    # Ensure database module uses this test DB
    monkeypatch.setattr(config, "DB_PATH", str(tmp_db))
    database.init_db()

    # Start a scan entry
    scan_id = database.start_scan()
    assert isinstance(scan_id, int)

    # Insert a duplicate record
    file_path = str(tmp_path / "f1.txt")
    file_path2 = str(tmp_path / "f2.txt")
    database.insert_duplicate(scan_id, file_path, "h1", 123)
    database.insert_duplicate(scan_id, file_path2, "h1", 123)

    # Query duplicates for that scan
    rows = database.get_all_duplicates(scan_id)
    assert len(rows) >= 1

    # Finish scan
    database.finish_scan(scan_id, total_files=2, total_duplicates=1, total_size_saved=123)
    scans = database.get_scan_history(limit=10)
    assert len(scans) >= 1
    # Confirm the last scan entry has totals set (id, timestamp, total_files, total_duplicates, total_size_saved)
    last = scans[0]
    assert last[2] == 2
    assert last[3] == 1
    assert last[4] == 123
