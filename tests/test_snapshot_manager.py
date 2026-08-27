import pytest
from pathlib import Path
from omikun.core.snapshot_manager import SnapshotManager


def test_snapshot_manager_capture_and_rollback(tmp_path: Path):
    snap_mgr = SnapshotManager(tmp_path)
    
    # 1. Create a clean file
    test_file = tmp_path / "main.py"
    test_file.write_text("def hello(): return 'world'", encoding="utf-8")

    # 2. Capture initial snapshot
    s1 = snap_mgr.capture_snapshot("initial working state")
    assert s1 in snap_mgr.list_snapshots()
    # Confirm NO .git folder was created
    assert not (tmp_path / ".git").exists()

    # 3. Modify file with broken code and add a new temporary junk file
    test_file.write_text("def hello(): return broken_syntax(", encoding="utf-8")
    junk_file = tmp_path / "temp_junk.txt"
    junk_file.write_text("junk", encoding="utf-8")

    # 4. Rollback to snapshot 1
    restored = snap_mgr.restore_snapshot(s1)
    assert restored is True
    assert test_file.read_text(encoding="utf-8") == "def hello(): return 'world'"
    assert not junk_file.exists()
