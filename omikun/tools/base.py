from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Result returned by tool execution."""

    success: bool
    output: str
    error: str | None = None
    exit_code: int = 0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> str:
        if self.success:
            return f"✅ SUCCESS: {self.output[:300]}" + ("..." if len(self.output) > 300 else "")
        return f"❌ FAILED (Exit Code {self.exit_code}): {self.error or self.output}"


class BaseTool(ABC):
    """Abstract base class for all Omikun tools."""

    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool asynchronously with given arguments."""
        pass

    def get_schema(self) -> dict[str, Any]:
        """Returns tool schema in JSON schema format for the LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
