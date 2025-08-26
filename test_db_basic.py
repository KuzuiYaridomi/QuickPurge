# test_db_basic.py
# quick script to validate DB init / insert_duplicate / get_all_duplicates
import os, sys, pprint, time

# Make sure project root is on sys.path if needed
# (adjust if you run from another folder)
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from quickpurge import database
from quickpurge.database import DB_PATH

print("DB_PATH:", DB_PATH)
print("Removing DB (if exists) to test fresh creation...")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print("Removed old DB.")

print("Calling init_db() to create schema...")
database.init_db()

print("Starting a test scan entry...")
scan_id = database.start_scan()
print("scan_id:", scan_id)

# Insert artificial duplicate group: two files with same hash & size
fake_hash = "deadbeef1234"
size = 12345
p1 = os.path.join(os.getcwd(), "testfile_a.txt")
p2 = os.path.join(os.getcwd(), "testfile_b.txt")

# create dummy files so os.stat() in UI code finds them (not required by DB itself)
with open(p1, "wb") as f:
    f.write(b"x" * 10)
with open(p2, "wb") as f:
    f.write(b"x" * 10)

print("Inserting duplicates via insert_duplicate()")
database.insert_duplicate(scan_id, p1, fake_hash, size)
database.insert_duplicate(scan_id, p2, fake_hash, size)

print("Finish scan metadata")
database.finish_scan(scan_id, total_files=2, total_duplicates=1, total_size_saved=size)

print("Querying get_all_duplicates(scan_id)... (expected shape: [(joined_paths, size), ...])")
rows = database.get_all_duplicates(scan_id)
pprint.pprint(rows)

print("Calling safe_get_all_duplicates(scan_id):")
safe_rows = database.safe_get_all_duplicates(scan_id)
pprint.pprint(safe_rows)

print("Test complete. Cleaning up test files.")
try:
    os.remove(p1)
    os.remove(p2)
except Exception:
    pass
