import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from omikun.config import OmikunConfig


class StepRecord(BaseModel):
    step_id: int
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    subtask_title: str
    prompt: str
    raw_response: str
    thought: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    tool_success: bool = False
    tool_output: str = ""
    tool_error: Optional[str] = None
    tool_exit_code: int = 0
    duration_ms: float = 0.0
    snapshot_before: Optional[str] = None
    snapshot_after: Optional[str] = None
    rollback_occurred: bool = False


class FlightRecorder:
    """Records full trajectory logs and telemetry for every Omikun execution run."""

    def __init__(self, config: OmikunConfig, run_id: Optional[str] = None):
        self.config = config
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.config.runs_dir / self.run_id
        self.trajectory_file = self.run_dir / "trajectory.jsonl"
        self.summary_file = self.run_dir / "summary.md"
        self.records: List[StepRecord] = []
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def record_step(self, step: StepRecord) -> None:
        """Append a step record to memory and write to JSONL file."""
        self.records.append(step)
        with open(self.trajectory_file, "a", encoding="utf-8") as f:
            f.write(step.model_dump_json() + "\n")

    def finalize(self, goal: str, total_status: str, total_time_sec: float) -> Path:
        """Generate a human-readable summary report in Markdown format."""
        passed_steps = sum(1 for r in self.records if r.tool_success)
        failed_steps = sum(1 for r in self.records if not r.tool_success)
        rollbacks = sum(1 for r in self.records if r.rollback_occurred)

        md = f"""# Omikun Run Summary: `{self.run_id}`

- **Goal:** {goal}
- **Status:** {total_status}
- **Duration:** {total_time_sec:.2f}s
- **Total Steps:** {len(self.records)} (Passed: {passed_steps}, Failed: {failed_steps}, Rollbacks: {rollbacks})
- **Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Step Execution Timeline

| Step | Subtask | Tool | Status | Duration |
| :--- | :--- | :--- | :--- | :--- |
"""
        for r in self.records:
            status_icon = "✅" if r.tool_success else "❌"
            md += f"| {r.step_id} | {r.subtask_title[:30]} | `{r.tool_name}` | {status_icon} | {r.duration_ms:.0f}ms |\n"

        md += "\n---\n\n## Detailed Trajectory Log\n\n"
        for r in self.records:
            md += f"### Step {r.step_id}: {r.subtask_title}\n\n"
            if r.thought:
                md += f"> **Thought:** {r.thought}\n\n"
            md += f"- **Tool Called:** `{r.tool_name}` with arguments `{json.dumps(r.tool_arguments)}`\n"
            md += f"- **Success:** {r.tool_success} (Exit code: {r.tool_exit_code})\n"
            if r.tool_error:
                md += f"- **Error:**\n```text\n{r.tool_error}\n```\n"
            if r.tool_output:
                md += f"- **Output:**\n```text\n{r.tool_output[:500]}\n```\n"
            if r.rollback_occurred:
                md += f"- ⚠️ **Rollback Triggered**\n"
            md += "\n"

        self.summary_file.write_text(md, encoding="utf-8")
        return self.summary_file
