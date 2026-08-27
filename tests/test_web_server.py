import asyncio
import json
import pytest
import httpx
from pathlib import Path
from omikun.server.web_server import OmikunWebServer
from omikun.core.orchestrator import OrchestratorEvent


@pytest.mark.asyncio
async def test_web_server_endpoints(tmp_path: Path):
    # Setup test workspace with a sample index.html
    sample_html = "<!DOCTYPE html><html><body><h1>Test App</h1></body></html>"
    (tmp_path / "index.html").write_text(sample_html, encoding="utf-8")

    server = OmikunWebServer(host="127.0.0.1", port=58231, default_workspace=tmp_path)
    await server.start()

    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:58231") as client:
            # 1. Test Static Index SPA
            r_index = await client.get("/")
            assert r_index.status_code == 200
            assert "Omikun Web Cockpit" in r_index.text

            # 2. Test API Status
            r_status = await client.get("/api/status")
            assert r_status.status_code == 200
            status_data = r_status.json()
            assert "is_running" in status_data
            assert status_data["is_running"] is False

            # 3. Test API Files
            r_files = await client.get(f"/api/files?workspace={tmp_path}")
            assert r_files.status_code == 200
            files_data = r_files.json()
            assert any(f["name"] == "index.html" for f in files_data["files"])

            # 4. Test Preview Endpoint
            r_preview = await client.get("/preview/index.html")
            assert r_preview.status_code == 200
            assert "Test App" in r_preview.text

            # 5. Test Event Broadcasting
            event = OrchestratorEvent(event_type="thought", message="Thinking about code...")
            server.broadcast_event(event)
            assert len(server.recent_events) == 1
            assert server.recent_events[0]["type"] == "thought"

    finally:
        if server.server:
            server.server.close()
            await server.server.wait_closed()
