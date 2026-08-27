import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import time

logger = logging.getLogger("omikun.core.snapshot")


class SnapshotManager:
    """Manages lightweight, non-git workspace snapshots for safe rollback and rethinking.
    
    Zero git commands are used. Operates entirely via in-memory and local disk snapshots.
    """

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.snapshots: Dict[str, Dict[str, str]] = {}
        self.ignore_dirs = {".git", ".omikun", "__pycache__", ".venv", "node_modules"}

    def capture_snapshot(self, label: str) -> str:
        """Capture the text state of all files in workspace without using Git."""
        snapshot_id = f"snap_{int(time.time() * 1000)}"
        file_map: Dict[str, str] = {}

        try:
            for root, dirs, files in os.walk(self.workspace_path):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
                for f in files:
                    full_p = Path(root) / f
                    rel_p = str(full_p.relative_to(self.workspace_path)).replace("\\", "/")
                    try:
                        file_map[rel_p] = full_p.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass
            self.snapshots[snapshot_id] = file_map
            logger.info(f"Captured snapshot [{snapshot_id}] '{label}' with {len(file_map)} files")
        except Exception as e:
            logger.warning(f"Failed to capture snapshot: {e}")

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore workspace files to a previous snapshot state without touching Git."""
        if snapshot_id not in self.snapshots:
            logger.warning(f"Snapshot [{snapshot_id}] not found for restore.")
            return False

        target_files = self.snapshots[snapshot_id]
        logger.warning(f"Reverting workspace files to snapshot [{snapshot_id}]")

        try:
            # 1. Remove files created after snapshot
            for root, dirs, files in os.walk(self.workspace_path):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
                for f in files:
                    full_p = Path(root) / f
                    rel_p = str(full_p.relative_to(self.workspace_path)).replace("\\", "/")
                    if rel_p not in target_files:
                        try:
                            full_p.unlink()
                        except Exception:
                            pass

            # 2. Restore file contents
            for rel_p, content in target_files.items():
                dest = self.workspace_path / rel_p
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            return True
        except Exception as e:
            logger.error(f"Error restoring snapshot {snapshot_id}: {e}")
            return False

    def list_snapshots(self) -> List[str]:
        return list(self.snapshots.keys())
