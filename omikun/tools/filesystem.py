import os
from pathlib import Path
from typing import Any
from omikun.tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file within the project workspace, optionally with line numbers."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path to the file from the workspace root.",
            },
            "line_numbers": {
                "type": "boolean",
                "description": "Whether to prefix output with line numbers (default true).",
                "default": True,
            },
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, file_path: str, line_numbers: bool = True, **kwargs: Any) -> ToolResult:
        full_path = (self.workspace_path / file_path).resolve()
        if not full_path.is_relative_to(self.workspace_path.resolve()):
            return ToolResult(success=False, output="", error=f"Access denied: path {file_path} is outside workspace.")

        if not full_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {file_path}")

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            if line_numbers:
                lines = content.splitlines()
                formatted = [f"{idx+1:4d} | {line}" for idx, line in enumerate(lines)]
                output = "\n".join(formatted)
            else:
                output = content
            return ToolResult(success=True, output=output, metadata={"file_path": file_path, "size": len(content)})
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error reading {file_path}: {str(e)}")


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Create a new file or completely overwrite an existing file with the provided content."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path to the file from the workspace root.",
            },
            "content": {
                "type": "string",
                "description": "The exact full text content to write into the file.",
            },
        },
        "required": ["file_path", "content"],
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, file_path: str, content: str, **kwargs: Any) -> ToolResult:
        full_path = (self.workspace_path / file_path).resolve()
        if not full_path.is_relative_to(self.workspace_path.resolve()):
            return ToolResult(success=False, output="", error=f"Access denied: path {file_path} is outside workspace.")

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Successfully written {len(content)} characters to {file_path}",
                metadata={"file_path": file_path, "size": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error writing {file_path}: {str(e)}")


class PatchFileTool(BaseTool):
    name = "patch_file"
    description = (
        "Surgically replace a specific block of text within an existing file. "
        "The target_content must match exactly character-for-character."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path to the file from the workspace root.",
            },
            "target_content": {
                "type": "string",
                "description": "The exact existing block of text to be replaced.",
            },
            "replacement_content": {
                "type": "string",
                "description": "The new replacement text.",
            },
        },
        "required": ["file_path", "target_content", "replacement_content"],
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, file_path: str, target_content: str, replacement_content: str, **kwargs: Any) -> ToolResult:
        full_path = (self.workspace_path / file_path).resolve()
        if not full_path.is_relative_to(self.workspace_path.resolve()):
            return ToolResult(success=False, output="", error=f"Access denied: path {file_path} is outside workspace.")

        if not full_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {file_path}")

        try:
            content = full_path.read_text(encoding="utf-8")
            norm_content = content.replace("\r\n", "\n")
            norm_target = target_content.replace("\r\n", "\n")
            norm_replacement = replacement_content.replace("\r\n", "\n")

            if not norm_target:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"target_content cannot be empty. Specify the exact block of text to replace, or use write_file to overwrite {file_path}.",
                )

            count = norm_content.count(norm_target)
            if count == 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Target content not found in {file_path}. Make sure whitespace and line indentation match exactly.",
                )
            if count > 1:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Target content found {count} times in {file_path}. Please provide a larger unique surrounding block.",
                )

            new_content = norm_content.replace(norm_target, norm_replacement, 1)
            full_path.write_text(new_content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Successfully patched {file_path}.",
                metadata={"file_path": file_path},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error patching {file_path}: {str(e)}")


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and directories recursively within the workspace, ignoring hidden directories like .git and .omikun."
    parameters = {
        "type": "object",
        "properties": {
            "sub_path": {
                "type": "string",
                "description": "Optional subdirectory to list (defaults to workspace root).",
                "default": ".",
            },
            "max_depth": {
                "type": "integer",
                "description": "Max recursion depth (default 4).",
                "default": 4,
            },
        },
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, sub_path: str = ".", max_depth: int = 4, **kwargs: Any) -> ToolResult:
        target_dir = (self.workspace_path / sub_path).resolve()
        if not target_dir.is_relative_to(self.workspace_path.resolve()):
            return ToolResult(success=False, output="", error="Access denied: path outside workspace.")

        if not target_dir.exists() or not target_dir.is_dir():
            return ToolResult(success=False, output="", error=f"Directory not found: {sub_path}")

        ignore_dirs = {".git", ".omikun", "__pycache__", ".venv", "node_modules", ".pytest_cache"}
        result_lines = []

        try:
            for root, dirs, files in os.walk(target_dir):
                # Filter out ignored directories
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                
                rel_root = Path(root).relative_to(self.workspace_path)
                depth = len(rel_root.parts)
                if depth > max_depth:
                    continue

                indent = "  " * (depth - 1 if depth > 0 else 0)
                if str(rel_root) != ".":
                    result_lines.append(f"{indent}📁 {rel_root.name}/")
                    indent += "  "

                for f in sorted(files):
                    result_lines.append(f"{indent}📄 {f}")

            output = "\n".join(result_lines) if result_lines else "(Empty directory)"
            return ToolResult(success=True, output=output, metadata={"path": sub_path})
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error listing directory: {str(e)}")
