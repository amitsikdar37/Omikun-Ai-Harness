from pathlib import Path
from typing import Dict
from omikun.tools.base import BaseTool, ToolResult
from omikun.tools.terminal import TerminalTool
from omikun.tools.filesystem import ReadFileTool, WriteFileTool, PatchFileTool, ListDirTool
from omikun.tools.verifier import ProjectVerifierTool


def get_default_tools(workspace_path: Path) -> Dict[str, BaseTool]:
    """Instantiate and return the standard Omikun tool registry."""
    tools = [
        TerminalTool(workspace_path),
        ReadFileTool(workspace_path),
        WriteFileTool(workspace_path),
        PatchFileTool(workspace_path),
        ListDirTool(workspace_path),
        ProjectVerifierTool(workspace_path),
    ]
    return {t.name: t for t in tools}


__all__ = [
    "BaseTool",
    "ToolResult",
    "TerminalTool",
    "ReadFileTool",
    "WriteFileTool",
    "PatchFileTool",
    "ListDirTool",
    "ProjectVerifierTool",
    "get_default_tools",
]
