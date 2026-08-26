from pathlib import Path
from pydantic import BaseModel, Field


class OmikunConfig(BaseModel):
    """Configuration settings for Omikun agentic harness."""

    # LLM Settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for local Ollama instance",
    )
    model_name: str = Field(
        default="qwen2.5-coder:7b",
        description="Local model name to invoke via Ollama",
    )
    temperature: float = Field(
        default=0.1,
        description="Sampling temperature for code generation",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens per completion turn",
    )
    context_window: int = Field(
        default=8192,
        description="Max context tokens window",
    )

    # Execution & Safety Settings
    command_timeout: int = Field(
        default=120,
        description="Maximum seconds a shell command is allowed to run before timeout",
    )
    max_step_retries: int = Field(
        default=6,
        description="Number of attempts before triggering a Git rollback on dead end",
    )
    auto_git_checkpoints: bool = Field(
        default=True,
        description="Whether to automatically create git commits before and after subtasks",
    )
    auto_rollback: bool = Field(
        default=True,
        description="Whether to rollback git state when a dead end is reached",
    )

    # Storage Paths
    workspace_path: Path = Field(
        default_factory=lambda: Path.cwd(),
        description="Root path of the target workspace",
    )
    omikun_dir: Path = Field(
        default_factory=lambda: Path.cwd() / ".omikun",
        description="Directory for trajectory logs and metadata",
    )

    @property
    def runs_dir(self) -> Path:
        return self.omikun_dir / "runs"


def get_default_config(workspace_path: Path | None = None) -> OmikunConfig:
    ws = workspace_path or Path.cwd()
    return OmikunConfig(
        workspace_path=ws,
        omikun_dir=ws / ".omikun",
    )
