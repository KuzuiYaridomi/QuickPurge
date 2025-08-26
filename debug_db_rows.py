from quickpurge import database
from quickpurge.database import DB_PATH, get_all_duplicates
import sqlite3, pprint

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
print("--- raw duplicates table sample ---")
for r in cur.execute("SELECT id, scan_id, file_path, file_hash, file_size FROM duplicates LIMIT 20"):
    pprint.pprint(r)
print("\n--- get_all_duplicates() output sample ---")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("No scans found in DB")
else:
    latest_scan_id = row[0]
    rows = get_all_duplicates(latest_scan_id)
    print("Using scan_id =", latest_scan_id)
    import pprint; pprint.pprint(rows)
conn.close()

pprint.pprint(rows)
conn.close()
