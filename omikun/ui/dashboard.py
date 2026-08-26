import sys
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.markdown import Markdown

from omikun.core.orchestrator import OrchestratorEvent, SubTask

# Reconfigure Windows stdout/stderr to UTF-8
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "thought": "italic magenta",
    "tool": "bold blue",
})

console = Console(theme=custom_theme, legacy_windows=False)


class TerminalDashboard:
    """Renders real-time execution events cleanly to the terminal."""

    def __init__(self):
        self.console = console
        self.plan: List[Dict[str, Any]] = []

    def render_banner(self, goal: str, model_name: str, workspace_path: str) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold cyan", justify="right")
        table.add_column(style="white")

        table.add_row("🎯 Goal:", goal)
        table.add_row("🧠 Model:", model_name)
        table.add_row("📁 Workspace:", workspace_path)

        panel = Panel(
            table,
            title="[bold yellow]⚡ OMIKUN AUTONOMOUS HARNESS[/bold yellow]",
            subtitle="[dim]Disciplined Agentic Engineering for Local LLMs[/dim]",
            border_style="cyan",
            expand=False,
        )
        self.console.print(panel)
        self.console.print()

    def handle_event(self, event: OrchestratorEvent) -> None:
        """Handle incoming orchestrator event and render appropriate UI element."""
        etype = event.event_type
        msg = event.message
        data = event.data

        if etype == "status":
            self.console.print(f"[info]{msg}[/info]")

        elif etype == "plan_created":
            self.plan = data.get("plan", [])
            table = Table(title="📋 Subtask Execution Graph", border_style="dim", expand=False)
            table.add_column("ID", style="cyan", justify="center")
            table.add_column("Subtask", style="bold white")
            table.add_column("Description", style="dim")

            for item in self.plan:
                table.add_row(str(item.get("id")), item.get("title", ""), item.get("description", ""))

            self.console.print(table)
            self.console.print()

        elif etype == "step_start":
            self.console.print(Panel(f"[bold cyan]{msg}[/bold cyan]", border_style="blue"))

        elif etype == "thought":
            thought_text = data.get("thought", msg)
            self.console.print(f"[thought]💡 Thought: {thought_text}[/thought]")

        elif etype == "tool_executing":
            tool_name = data.get("tool", "")
            args = data.get("args", {})
            self.console.print(f"[tool]⚡ Invoking Tool: `{tool_name}`[/tool]")
            if tool_name == "run_command":
                self.console.print(f"   [dim]$ {args.get('command')}[/dim]")
            elif tool_name in {"write_file", "patch_file", "read_file"}:
                self.console.print(f"   [dim]File: {args.get('file_path')}[/dim]")

        elif etype == "tool_result":
            res = data.get("result", {})
            success = res.get("success", False)
            duration = res.get("duration_ms", 0.0)
            
            if success:
                self.console.print(f"[success]   ✅ Tool Success ({duration:.0f}ms)[/success]")
                out = res.get("output", "")
                if out:
                    # Truncate output preview for cleanliness
                    preview = out[:250] + ("..." if len(out) > 250 else "")
                    self.console.print(Panel(preview, title="[dim]Output[/dim]", border_style="dim"))
            else:
                err = res.get("error", "") or res.get("output", "")
                self.console.print(f"[error]   ❌ Tool Failed ({duration:.0f}ms): {err[:300]}[/error]")

        elif etype == "step_complete":
            self.console.print(f"[success]{msg}[/success]\n")

        elif etype == "rollback":
            self.console.print(Panel(f"[warning]{msg}[/warning]", title="[bold red]⏪ ROLLBACK[/bold red]", border_style="red"))

        elif etype == "error":
            self.console.print(f"[error]{msg}[/error]")

        elif etype == "complete":
            self.console.print()
            self.console.print(
                Panel(
                    f"[bold green]{msg}[/bold green]",
                    title="[bold green]🏆 TASK FINISHED[/bold green]",
                    border_style="green",
                )
            )
