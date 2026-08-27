import argparse
import asyncio
import sys
from pathlib import Path
from omikun.config import OmikunConfig, get_default_config
from omikun.core.orchestrator import OmikunOrchestrator
from omikun.llm.client import OllamaClient
from omikun.ui.dashboard import TerminalDashboard, console


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="omikun",
        description="Omikun: Autonomous Agentic Coding Harness for Lightweight Local LLMs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'run' command
    run_parser = subparsers.add_parser("run", help="Run an autonomous coding task")
    run_parser.add_argument("goal", type=str, help="The software engineering goal or instruction")
    run_parser.add_argument("--model", type=str, default="qwen2.5-coder:7b", help="Ollama model name to use")
    run_parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama API base URL")
    run_parser.add_argument("--workspace", type=str, default=".", help="Target workspace path")

    # 'models' command
    subparsers.add_parser("models", help="List available models in local Ollama")

    # 'summary' command
    summary_parser = subparsers.add_parser("summary", help="View summary of a past run")
    summary_parser.add_argument("run_id", type=str, help="The run ID to inspect")

    return parser.parse_args()


async def async_run(args: argparse.Namespace) -> int:
    ws_path = Path(args.workspace).resolve()
    config = OmikunConfig(
        workspace_path=ws_path,
        omikun_dir=ws_path / ".omikun",
        model_name=args.model,
        ollama_base_url=args.ollama_url,
    )

    dashboard = TerminalDashboard()
    dashboard.render_banner(
        goal=args.goal,
        model_name=config.model_name,
        workspace_path=str(ws_path),
    )

    orchestrator = OmikunOrchestrator(
        config=config,
        event_callback=dashboard.handle_event,
    )

    success = await orchestrator.run(args.goal)
    return 0 if success else 1


async def async_list_models(args: argparse.Namespace) -> int:
    config = get_default_config()
    client = OllamaClient(config)
    
    if not await client.check_health():
        console.print(f"[error]❌ Cannot connect to Ollama at {config.ollama_base_url}.[/error]")
        return 1

    models = await client.list_models()
    console.print("[bold cyan]Available Local Models in Ollama:[/bold cyan]")
    for m in models:
        prefix = "⭐ " if "qwen" in m.lower() else "  "
        console.print(f"{prefix}[white]{m}[/white]")
from rich.prompt import Prompt
from rich.panel import Panel


async def async_interactive() -> int:
    """Run Omikun in interactive TUI prompt mode."""
    config = get_default_config()
    client = OllamaClient(config)

    console.print(
        Panel(
            "[bold white]Autonomous Agentic Coding Studio for Lightweight Local LLMs[/bold white]\n"
            "[dim]Direct on-device engineering • Zero Git pollution • Root-cause reflection[/dim]",
            title="[bold yellow]⚡ OMIKUN INTERACTIVE STUDIO[/bold yellow]",
            border_style="cyan",
            expand=False,
        )
    )

    # Health check
    if not await client.check_health():
        console.print(f"[bold red]❌ Cannot connect to Ollama at {config.ollama_base_url}.[/bold red]")
        console.print("[yellow]Please make sure Ollama is running (`ollama serve` or start Ollama app).[/yellow]")
        return 1

    models = await client.list_models()
    selected_model = config.model_name
    if selected_model not in models and models:
        # Prefer qwen2.5-coder if available
        qwen_models = [m for m in models if "qwen" in m.lower()]
        selected_model = qwen_models[0] if qwen_models else models[0]

    console.print(f"[dim]Connected to Ollama • Active Model: [bold cyan]{selected_model}[/bold cyan][/dim]")

    while True:
        try:
            goal = Prompt.ask("\n[bold cyan]🎯 What would you like Omikun to build?[/bold cyan] (or 'q' to quit)").strip()
            if not goal or goal.lower() in {"q", "quit", "exit"}:
                console.print("[dim]👋 Exiting Omikun Studio. Happy hacking![/dim]")
                break

            # Suggest folder name based on goal words
            clean_name = "-".join([w.lower() for w in goal.split() if w.isalnum()][:3]) or "workspace"
            default_ws = f"./{clean_name}"

            ws_input = Prompt.ask("[bold green]📁 Target workspace folder[/bold green]", default=default_ws).strip()
            ws_path = Path(ws_input).resolve()
            ws_path.mkdir(parents=True, exist_ok=True)

            run_config = OmikunConfig(
                workspace_path=ws_path,
                omikun_dir=ws_path / ".omikun",
                model_name=selected_model,
                ollama_base_url=config.ollama_base_url,
            )

            dashboard = TerminalDashboard()
            dashboard.render_banner(
                goal=goal,
                model_name=run_config.model_name,
                workspace_path=str(ws_path),
            )

            orchestrator = OmikunOrchestrator(
                config=run_config,
                event_callback=dashboard.handle_event,
            )

            await orchestrator.run(goal)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]👋 Session ended.[/dim]")
            break

    return 0


def main() -> None:
    args = parse_args()

    # If no subcommand provided, default to Interactive Studio Mode
    if not args.command:
        exit_code = asyncio.run(async_interactive())
        sys.exit(exit_code)

    if args.command == "run":
        exit_code = asyncio.run(async_run(args))
        sys.exit(exit_code)

    elif args.command == "models":
        exit_code = asyncio.run(async_list_models(args))
        sys.exit(exit_code)

    elif args.command == "summary":
        runs_dir = Path.cwd() / ".omikun" / "runs" / args.run_id
        summary_file = runs_dir / "summary.md"
        if not summary_file.exists():
            console.print(f"[error]No summary found for run ID '{args.run_id}' at {summary_file}[/error]")
            sys.exit(1)
        console.print(summary_file.read_text(encoding="utf-8"))
        sys.exit(0)


if __name__ == "__main__":
    main()
