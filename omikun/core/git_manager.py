import logging
import os
from pathlib import Path
from typing import Optional
import git

logger = logging.getLogger("omikun.core.git")


class GitManager:
    """Manages Git checkpoints, commits, and rollbacks for the Omikun workspace."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self._repo: Optional[git.Repo] = None

    def initialize_repo(self) -> git.Repo:
        """Ensure git repository is initialized and .omikun is ignored."""
        try:
            self._repo = git.Repo(self.workspace_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            logger.info(f"Initializing new Git repository in {self.workspace_path}")
            self._repo = git.Repo.init(self.workspace_path)

        # Ensure .gitignore has .omikun and common cache dirs
        gitignore_path = self.workspace_path / ".gitignore"
        ignore_entries = {".omikun", ".omikun/", "__pycache__", ".venv", ".pytest_cache"}
        
        existing_ignores = set()
        if gitignore_path.exists():
            existing_ignores = set(gitignore_path.read_text(encoding="utf-8").splitlines())

        missing = ignore_entries - existing_ignores
        if missing:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(missing) + "\n")

        # Initial commit if empty
        if not self._repo.heads:
            try:
                self._repo.git.add(all=True)
                # Check if there are staged changes
                if self._repo.index.diff("HEAD"):
                    self._repo.index.commit("omikun: initial repository state")
            except Exception:
                try:
                    self._repo.index.commit("omikun: initial repository state")
                except Exception:
                    pass

        return self._repo

    @property
    def repo(self) -> git.Repo:
        if self._repo is None:
            return self.initialize_repo()
        return self._repo

    def create_checkpoint(self, message: str) -> Optional[str]:
        """Stage all current changes and create a commit checkpoint."""
        try:
            repo = self.repo
            repo.git.add(all=True)
            # Only commit if there are changes
            if repo.is_dirty(untracked_files=True) or len(repo.index.diff("HEAD")) > 0:
                commit = repo.index.commit(f"omikun: {message}")
                logger.info(f"Created Git checkpoint [{commit.hexsha[:7]}]: {message}")
                return commit.hexsha
            elif repo.heads:
                return repo.head.commit.hexsha
        except Exception as e:
            logger.warning(f"Failed to create Git checkpoint: {e}")
        return None

    def rollback_to(self, commit_hash: str) -> bool:
        """Hard reset workspace to the specified commit and clean untracked files."""
        try:
            repo = self.repo
            logger.warning(f"Rolling back workspace to commit [{commit_hash[:7]}]")
            repo.git.reset("--hard", commit_hash)
            repo.git.clean("-fd")
            return True
        except Exception as e:
            logger.error(f"Error rolling back to {commit_hash}: {e}")
            return False

    def get_diff(self) -> str:
        """Get diff of uncommitted changes."""
        try:
            repo = self.repo
            return repo.git.diff()
        except Exception:
            return ""

    def get_head_hash(self) -> Optional[str]:
        """Get current HEAD commit hash."""
        try:
            repo = self.repo
            if repo.heads:
                return repo.head.commit.hexsha
        except Exception:
            pass
        return None
