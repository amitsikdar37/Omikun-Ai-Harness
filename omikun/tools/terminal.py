import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any
from omikun.tools.base import BaseTool, ToolResult


class TerminalTool(BaseTool):
    """Executes shell commands safely within the project workspace."""

    name = "run_command"
    description = (
        "Execute a shell command (e.g. pytest, python script.py, npm test, pip install) "
        "inside the workspace. Captures stdout, stderr, and exit code."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The exact shell command to execute.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum execution time in seconds before timeout (default 60).",
                "default": 60,
            },
        },
        "required": ["command"],
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, command: str, timeout_seconds: int = 60, **kwargs: Any) -> ToolResult:
        start_time = time.perf_counter()
        
        # On Windows, sanitize bash-style '&&' chaining and wrap in powershell.exe
        is_windows = sys.platform == "win32"
        if is_windows:
            # Replace '&&' with ';' so chained commands work seamlessly in Windows PowerShell 5.1
            sanitized_command = command.replace("&&", ";")
            shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", sanitized_command]
        else:
            shell_cmd = command

        # Prepare execution environment with Python virtualenv Scripts in PATH
        env = os.environ.copy()
        venv_scripts = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
        ws_venv_scripts = self.workspace_path / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")

        paths_to_prepend = []
        if ws_venv_scripts.exists():
            paths_to_prepend.append(str(ws_venv_scripts))
        if venv_scripts.exists():
            paths_to_prepend.append(str(venv_scripts))

        if paths_to_prepend:
            env["PATH"] = f"{os.pathsep.join(paths_to_prepend)}{os.pathsep}{env.get('PATH', '')}"

        try:
            if is_windows:
                process = await asyncio.create_subprocess_exec(
                    *shell_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace_path),
                    env=env,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    shell_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace_path),
                    env=env,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=float(timeout_seconds)
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                duration_ms = (time.perf_counter() - start_time) * 1000
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout_seconds} seconds.",
                    exit_code=-1,
                    duration_ms=duration_ms,
                    metadata={"command": command, "timed_out": True},
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Decode output safely
            stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
            exit_code = process.returncode if process.returncode is not None else 0

            combined_output = stdout_str
            if stderr_str:
                combined_output = f"{stdout_str}\nSTDERR:\n{stderr_str}".strip() if stdout_str else f"STDERR:\n{stderr_str}"

            success = exit_code == 0
            return ToolResult(
                success=success,
                output=combined_output,
                error=stderr_str if not success else None,
                exit_code=exit_code,
                duration_ms=duration_ms,
                metadata={"command": command, "exit_code": exit_code},
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute command '{command}': {str(e)}",
                exit_code=-1,
                duration_ms=duration_ms,
                metadata={"command": command},
            )
