import asyncio
import json
import logging
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from omikun.config import OmikunConfig, get_default_config
from omikun.core.orchestrator import OmikunOrchestrator, OrchestratorEvent
from omikun.llm.client import OllamaClient

logger = logging.getLogger("omikun.server")

STATIC_DIR = Path(__file__).parent / "static"


class OmikunWebServer:
    """Zero-dependency asynchronous Web Cockpit and SSE streaming server for Omikun."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        default_workspace: Optional[Path] = None,
    ):
        self.host = host
        self.port = port
        self.default_workspace = (default_workspace or Path.cwd()).resolve()
        self.active_workspace = self.default_workspace
        self.is_running_task = False
        self.active_task: Optional[asyncio.Task] = None
        self.recent_events: List[Dict[str, Any]] = []
        self.sse_subscribers: Set[asyncio.Queue] = set()
        self.server: Optional[asyncio.Server] = None
        self.last_goal = ""
        self.current_plan: List[Dict[str, Any]] = []
        self.task_status = "idle"  # idle | running | completed | failed

    def broadcast_event(self, event: OrchestratorEvent) -> None:
        """Store event and push to all connected SSE clients."""
        event_dict = {
            "type": event.event_type,
            "message": event.message,
            "data": event.data,
            "timestamp": asyncio.get_event_loop().time(),
        }
        self.recent_events.append(event_dict)
        if len(self.recent_events) > 500:
            self.recent_events.pop(0)

        if event.event_type == "plan_created":
            self.current_plan = event.data.get("plan", [])
        elif event.event_type == "complete":
            self.task_status = "completed"
            self.is_running_task = False
        elif event.event_type == "error" and not self.is_running_task:
            self.task_status = "failed"

        # Broadcast to SSE queues
        dead_queues = set()
        for q in self.sse_subscribers:
            try:
                q.put_nowait(event_dict)
            except Exception:
                dead_queues.add(q)
        self.sse_subscribers.difference_update(dead_queues)

    async def run_orchestration(self, goal: str, model_name: str, workspace_path: str) -> None:
        """Run orchestration in the background and pipe telemetry to SSE."""
        self.is_running_task = True
        self.task_status = "running"
        self.last_goal = goal
        ws_path = Path(workspace_path).resolve()
        ws_path.mkdir(parents=True, exist_ok=True)
        self.active_workspace = ws_path

        config = OmikunConfig(
            workspace_path=ws_path,
            omikun_dir=ws_path / ".omikun",
            model_name=model_name or "qwen2.5-coder:7b",
            ollama_base_url="http://localhost:11434",
        )

        orchestrator = OmikunOrchestrator(
            config=config,
            event_callback=self.broadcast_event,
        )

        try:
            success = await orchestrator.run(goal)
            self.task_status = "completed" if success else "failed"
        except Exception as e:
            logger.error(f"Orchestration error: {e}", exc_info=True)
            self.broadcast_event(OrchestratorEvent(event_type="error", message=f"Server error: {str(e)}"))
            self.task_status = "failed"
        finally:
            self.is_running_task = False

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming HTTP requests and SSE streams."""
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            words = request_line.decode("utf-8", errors="replace").strip().split()
            if len(words) < 2:
                writer.close()
                return

            method, raw_path = words[0], words[1]
            parsed_url = urllib.parse.urlparse(raw_path)
            path = urllib.parse.unquote(parsed_url.path)
            query = urllib.parse.parse_qs(parsed_url.query)

            # Read headers
            headers = {}
            content_length = 0
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                header_str = line.decode("utf-8", errors="replace").strip()
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        content_length = int(v.strip())

            # Read body for POST
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # Handle CORS preflight
            if method == "OPTIONS":
                self._send_cors_response(writer)
                return

            # Route Dispatch
            if path == "/" or path == "/index.html":
                await self._serve_static_file(writer, STATIC_DIR / "index.html", "text/html")
            elif path == "/api/events":
                await self._handle_sse(writer)
            elif path == "/api/models" and method == "GET":
                await self._handle_get_models(writer)
            elif path == "/api/status" and method == "GET":
                await self._handle_get_status(writer)
            elif path == "/api/files" and method == "GET":
                await self._handle_get_files(writer, query)
            elif path == "/api/run" and method == "POST":
                await self._handle_post_run(writer, body)
            elif path.startswith("/preview/"):
                await self._handle_preview(writer, path[len("/preview/"):])
            elif (STATIC_DIR / path.lstrip("/")).exists() and not (STATIC_DIR / path.lstrip("/")).is_dir():
                file_to_serve = (STATIC_DIR / path.lstrip("/")).resolve()
                if file_to_serve.is_relative_to(STATIC_DIR.resolve()):
                    mime_type, _ = mimetypes.guess_type(str(file_to_serve))
                    await self._serve_static_file(writer, file_to_serve, mime_type or "text/plain")
                else:
                    self._send_error(writer, 403, "Forbidden")
            else:
                self._send_error(writer, 404, "Not Found")

        except Exception as e:
            logger.debug(f"HTTP handler error: {e}")
        finally:
            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception:
                pass

    def _send_cors_response(self, writer: asyncio.StreamWriter) -> None:
        res = (
            "HTTP/1.1 204 No Content\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "\r\n"
        )
        writer.write(res.encode("utf-8"))

    def _send_error(self, writer: asyncio.StreamWriter, status_code: int, msg: str) -> None:
        body = json.dumps({"error": msg})
        res = (
            f"HTTP/1.1 {status_code} {msg}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{body}"
        )
        writer.write(res.encode("utf-8"))

    async def _serve_static_file(self, writer: asyncio.StreamWriter, file_path: Path, content_type: str) -> None:
        if not file_path.exists():
            self._send_error(writer, 404, f"File not found: {file_path.name}")
            return
        data = file_path.read_bytes()
        headers = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}; charset=utf-8\r\n"
            f"Content-Length: {len(data)}\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        writer.write(headers.encode("utf-8") + data)

    async def _handle_get_models(self, writer: asyncio.StreamWriter) -> None:
        config = get_default_config()
        client = OllamaClient(config)
        is_healthy = await client.check_health()
        models = []
        if is_healthy:
            models = await client.list_models()
        payload = json.dumps({"healthy": is_healthy, "models": models, "active_workspace": str(self.active_workspace)})
        res = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{payload}"
        )
        writer.write(res.encode("utf-8"))

    async def _handle_get_status(self, writer: asyncio.StreamWriter) -> None:
        payload = json.dumps({
            "is_running": self.is_running_task,
            "status": self.task_status,
            "goal": self.last_goal,
            "plan": self.current_plan,
            "workspace": str(self.active_workspace),
            "recent_events_count": len(self.recent_events),
        })
        res = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{payload}"
        )
        writer.write(res.encode("utf-8"))

    async def _handle_get_files(self, writer: asyncio.StreamWriter, query: Dict[str, List[str]]) -> None:
        ws = self.active_workspace
        if "workspace" in query and query["workspace"]:
            custom_ws = Path(query["workspace"][0]).resolve()
            if custom_ws.exists():
                ws = custom_ws

        file_list = []
        ignore_dirs = {".git", ".omikun", "__pycache__", ".venv", "node_modules"}
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for f in files:
                p = Path(root) / f
                rel = p.relative_to(ws).as_posix()
                try:
                    content = p.read_text(encoding="utf-8", errors="replace") if p.stat().st_size < 100000 else "(File too large)"
                except Exception:
                    content = "(Binary file)"
                file_list.append({
                    "name": f,
                    "path": rel,
                    "size": p.stat().st_size,
                    "content": content,
                })

        payload = json.dumps({"workspace": str(ws), "files": file_list})
        res = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{payload}"
        )
        writer.write(res.encode("utf-8"))

    async def _handle_post_run(self, writer: asyncio.StreamWriter, body: bytes) -> None:
        if self.is_running_task:
            self._send_error(writer, 409, "A task is already running.")
            return

        try:
            req_data = json.loads(body.decode("utf-8"))
            goal = req_data.get("goal", "").strip()
            model = req_data.get("model", "qwen2.5-coder:7b").strip()
            workspace = req_data.get("workspace", "./workspace").strip()

            if not goal:
                self._send_error(writer, 400, "Goal cannot be empty.")
                return

            self.recent_events.clear()
            self.current_plan = []
            self.active_task = asyncio.create_task(self.run_orchestration(goal, model, workspace))

            payload = json.dumps({"status": "started", "goal": goal, "workspace": workspace, "model": model})
            res = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n"
                "\r\n"
                f"{payload}"
            )
            writer.write(res.encode("utf-8"))
        except Exception as e:
            self._send_error(writer, 400, f"Invalid JSON payload: {str(e)}")

    async def _handle_preview(self, writer: asyncio.StreamWriter, subpath: str) -> None:
        """Serve files from the active workspace for real-time live preview iframe."""
        target_file = (self.active_workspace / (subpath or "index.html")).resolve()
        if not target_file.is_relative_to(self.active_workspace.resolve()):
            self._send_error(writer, 403, "Access denied")
            return

        if target_file.is_dir():
            target_file = target_file / "index.html"

        if not target_file.exists():
            # Return placeholder if index.html is not created yet
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Preview</title>"
                "<script src='https://cdn.tailwindcss.com'></script></head>"
                "<body class='bg-slate-900 text-slate-400 flex flex-col items-center justify-center min-h-screen p-8 text-center'>"
                "<div class='p-6 bg-slate-800/80 rounded-2xl border border-slate-700 max-w-sm'>"
                "<div class='text-4xl mb-3'>⏳</div>"
                "<h2 class='text-lg font-bold text-white mb-1'>Waiting for App Generation</h2>"
                "<p class='text-xs text-slate-400'>Once Omikun writes index.html, your live interactive app will automatically render here!</p>"
                "</div></body></html>"
            )
            res = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(html)}\r\n"
                "Cache-Control: no-cache\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "\r\n"
                f"{html}"
            )
            writer.write(res.encode("utf-8"))
            return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        await self._serve_static_file(writer, target_file, mime_type or "text/html")

    async def _handle_sse(self, writer: asyncio.StreamWriter) -> None:
        """Handle persistent Server-Sent Events (SSE) stream."""
        queue: asyncio.Queue = asyncio.Queue()
        self.sse_subscribers.add(queue)

        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream; charset=utf-8\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        )
        writer.write(headers.encode("utf-8"))
        await writer.drain()

        # Send past recent events to fast-catchup
        for ev in self.recent_events:
            data_str = json.dumps(ev)
            writer.write(f"data: {data_str}\n\n".encode("utf-8"))
        await writer.drain()

        try:
            while True:
                try:
                    # Wait for next event or send heartbeat every 15s
                    event_dict = await asyncio.wait_for(queue.get(), timeout=15.0)
                    data_str = json.dumps(event_dict)
                    writer.write(f"data: {data_str}\n\n".encode("utf-8"))
                    await writer.drain()
                except asyncio.TimeoutError:
                    # Heartbeat
                    writer.write(b": heartbeat\n\n")
                    await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            self.sse_subscribers.discard(queue)

    async def start(self) -> None:
        """Start listening on the specified host and port."""
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info(f"Omikun Web Cockpit running at http://{self.host}:{self.port}")

    async def serve_forever(self) -> None:
        """Start and run server indefinitely."""
        await self.start()
        async with self.server:
            await self.server.serve_forever()


async def start_web_cockpit(host: str = "127.0.0.1", port: int = 5000, workspace: Optional[Path] = None) -> None:
    server = OmikunWebServer(host=host, port=port, default_workspace=workspace)
    await server.serve_forever()
