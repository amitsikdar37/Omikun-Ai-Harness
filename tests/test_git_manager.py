import pytest
from pathlib import Path
from omikun.core.git_manager import GitManager


def test_git_manager_init_and_checkpoints(tmp_path: Path):
    git_mgr = GitManager(tmp_path)
    repo = git_mgr.initialize_repo()
    assert repo is not None
    assert (tmp_path / ".git").exists()
    assert (tmp_path / ".gitignore").exists()

    # Create a test file
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    # Checkpoint 1
    c1 = git_mgr.create_checkpoint("Added hello.py")
    assert c1 is not None

    # Modify file
    test_file.write_text("print('broken code')", encoding="utf-8")
    c2 = git_mgr.create_checkpoint("Broken change")
    assert c2 is not None
    assert c1 != c2

    # Verify rollback to checkpoint 1
    rolled_back = git_mgr.rollback_to(c1)
    assert rolled_back is True
    assert test_file.read_text(encoding="utf-8") == "print('hello')"
