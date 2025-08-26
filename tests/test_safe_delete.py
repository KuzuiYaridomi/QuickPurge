import os
from quickpurge import safe_delete

def test_safe_delete_and_permanent(tmp_path, monkeypatch):
    # Point archive to temp folder for the test
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(safe_delete, "ARCHIVE_DIR", str(archive_dir))

    # Create a test file
    f = tmp_path / "to_archive.txt"
    f.write_text("please archive me")

    # Ensure the file exists initially
    assert f.exists()

    # Call safe_delete
    ok = safe_delete.safe_delete(str(f))
    assert ok is True
    # Original should be gone
    assert not f.exists()
    # Archived file exists in archive_dir (one file)
    archived_files = list(archive_dir.iterdir())
    assert len(archived_files) == 1

    # Test permanent_delete: create another file and delete permanently
    f2 = tmp_path / "to_delete.txt"
    f2.write_text("delete me permanently")
    assert f2.exists()
    ok2 = safe_delete.permanent_delete(str(f2))
    assert ok2 is True
    assert not f2.exists()
