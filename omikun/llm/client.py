import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
import httpx
from omikun.config import OmikunConfig

logger = logging.getLogger("omikun.llm.client")


class OllamaClient:
    """Async client for local Ollama inference."""

    def __init__(self, config: OmikunConfig):
        self.config = config
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model_name = config.model_name

    async def check_health(self) -> bool:
        """Verify that Ollama server is running and accessible."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Fetch available models in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Error fetching Ollama models: {e}")
        return []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Send a multi-turn message history to Ollama and return completed response."""
        temp = temperature if temperature is not None else self.config.temperature
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temp,
                "num_ctx": self.config.context_window,
            },
        }

        timeout = httpx.Timeout(240.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama error ({res.status_code}): {res.text}")
            data = res.json()
            content = data.get("message", {}).get("content", "")
            return content
