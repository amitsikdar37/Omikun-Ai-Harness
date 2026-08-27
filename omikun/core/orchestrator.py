import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from omikun.config import OmikunConfig, get_default_config
from omikun.core.flight_recorder import FlightRecorder, StepRecord
from omikun.core.snapshot_manager import SnapshotManager
from omikun.llm.client import OllamaClient
from omikun.llm.parser import ToolCallParser, ParsedToolCall
from omikun.llm.prompts import (
    get_planner_prompt,
    get_step_context_prompt,
    get_system_prompt,
)
from omikun.tools import BaseTool, get_default_tools

logger = logging.getLogger("omikun.core.orchestrator")


class SubTask(BaseModel):
    id: int
    title: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed


class OrchestratorEvent(BaseModel):
    event_type: str  # plan_created | step_start | tool_executing | tool_result | rollback | complete | error
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)


class OmikunOrchestrator:
    """The central state machine and coordinator for Omikun agentic coding harness."""

    def __init__(
        self,
        config: Optional[OmikunConfig] = None,
        event_callback: Optional[Callable[[OrchestratorEvent], None]] = None,
    ):
        self.config = config or get_default_config()
        self.event_callback = event_callback
        self.workspace_path = self.config.workspace_path

        # Components (Zero Git commands used; all snapshots managed safely in memory/disk)
        self.llm = OllamaClient(self.config)
        self.snapshot_mgr = SnapshotManager(self.workspace_path)
        self.flight_recorder = FlightRecorder(self.config)
        self.tools: Dict[str, BaseTool] = get_default_tools(self.workspace_path)

        # Runtime State
        self.plan: List[SubTask] = []
        self.completed_tasks: List[str] = []
        self.current_step_index: int = 0
        self.step_counter: int = 1

    def _emit(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit real-time events to terminal or web UI."""
        if self.event_callback:
            event = OrchestratorEvent(event_type=event_type, message=message, data=data or {})
            self.event_callback(event)

    async def _get_workspace_file_tree(self) -> str:
        """Fetch current files in workspace using list_dir tool."""
        res = await self.tools["list_dir"].execute(sub_path=".", max_depth=3)
        return res.output or "(Empty directory)"

    async def generate_plan(self, goal: str) -> List[SubTask]:
        """Generate a structured execution plan from the local LLM."""
        self._emit("status", "📋 Generating execution plan with local model...")
        files_tree = await self._get_workspace_file_tree()
        planner_prompt = get_planner_prompt(goal, files_tree)

        messages = [
            {"role": "system", "content": "You are an expert software architect. Output JSON only."},
            {"role": "user", "content": planner_prompt},
        ]

        try:
            raw_response = await self.llm.generate(messages, temperature=0.1)
            thought, json_candidate = ToolCallParser.extract_thought_and_json(raw_response)
            repaired = ToolCallParser.repair_json_string(json_candidate)
            data = json.loads(repaired)
            plan_items = data.get("plan", [])

            subtasks = []
            for idx, item in enumerate(plan_items):
                subtasks.append(
                    SubTask(
                        id=idx + 1,
                        title=item.get("title", f"Subtask {idx + 1}"),
                        description=item.get("description", ""),
                    )
                )
            if subtasks:
                self.plan = subtasks
                self._emit("plan_created", f"Created plan with {len(subtasks)} subtasks", {"plan": [s.model_dump() for s in subtasks]})
                return self.plan
        except Exception as e:
            logger.warning(f"Plan generation failed: {e}. Falling back to default plan.")

        # Fallback plan
        self.plan = [
            SubTask(id=1, title="Scaffold project structure and dependencies", description="Create initial files"),
            SubTask(id=2, title="Implement core logic and modules", description="Write primary implementation"),
            SubTask(id=3, title="Write and execute automated test suite", description="Run verification tests"),
        ]
        self._emit("plan_created", f"Using baseline plan with {len(self.plan)} subtasks", {"plan": [s.model_dump() for s in self.plan]})
        return self.plan

    async def run(self, goal: str) -> bool:
        """Run the full autonomous engineering loop for the provided goal."""
        start_time = time.perf_counter()
        self._emit("status", f"🚀 Starting Omikun Orchestration for: '{goal}'")

        # 1. Capture initial workspace snapshot (Zero Git initialization)
        initial_snapshot = self.snapshot_mgr.capture_snapshot("Initial state before run")

        # 2. Check Ollama connectivity
        if not await self.llm.check_health():
            self._emit("error", f"❌ Cannot connect to Ollama at {self.config.ollama_base_url}. Please ensure Ollama is running.")
            return False

        # 3. Formulate Plan
        await self.generate_plan(goal)

        # 4. Prepare System Prompt & Tools Schema
        tools_schemas = [t.get_schema() for t in self.tools.values()]
        system_prompt = get_system_prompt(tools_schemas, str(self.workspace_path))

        # 5. Execute Subtasks Sequentially
        last_tool_result_str = ""

        for subtask in self.plan:
            subtask.status = "in_progress"
            self._emit("step_start", f"▶️ Starting Subtask {subtask.id}: {subtask.title}", {"subtask": subtask.model_dump()})

            # Checkpoint snapshot before subtask begins
            checkpoint_snapshot = self.snapshot_mgr.capture_snapshot(f"Pre-step {subtask.id}: {subtask.title}") or initial_snapshot
            subtask_succeeded = False
            attempts = 0

            while attempts < self.config.max_step_retries and not subtask_succeeded:
                attempts += 1
                files_tree = await self._get_workspace_file_tree()
                
                reflection_prefix = ""
                if attempts > 1:
                    reflection_prefix = (
                        f"⚠️ ATTEMPT {attempts}/{self.config.max_step_retries}: Previous action failed to complete this subtask.\n"
                        f"ROOT-CAUSE REFLECTION DIRECTIVE: Analyze why the previous attempt failed from first principles. "
                        f"Do NOT repeat the same mistake. Formulate a clean, correct fix.\n\n"
                    )

                step_prompt = reflection_prefix + get_step_context_prompt(
                    goal=goal,
                    current_step=f"{subtask.title} ({subtask.description}) [Attempt {attempts}/{self.config.max_step_retries}]",
                    completed_steps=self.completed_tasks,
                    workspace_files=files_tree,
                    last_tool_result=last_tool_result_str,
                )

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": step_prompt},
                ]

                self._emit("status", f"🤔 Model is thinking for Subtask {subtask.id} (Attempt {attempts})...")

                try:
                    raw_response = await self.llm.generate(messages, temperature=0.1)
                except Exception as e:
                    self._emit("error", f"Error generating from model: {e}")
                    break

                # Parse Tool Call
                parsed_call = ToolCallParser.parse(raw_response)
                if not parsed_call:
                    self._emit("error", f"⚠️ Model failed to output a valid tool call. Prompting for retry.")
                    last_tool_result_str = f"ERROR: Your previous response was not a valid tool call JSON. Please respond with a valid tool call JSON object."
                    continue

                if parsed_call.thought:
                    self._emit("thought", f"💡 Thought: {parsed_call.thought}", {"thought": parsed_call.thought})

                tool_name = parsed_call.tool_name
                tool_args = parsed_call.arguments

                if tool_name not in self.tools:
                    last_tool_result_str = f"ERROR: Tool '{tool_name}' does not exist. Available tools: {list(self.tools.keys())}"
                    self._emit("error", last_tool_result_str)
                    continue

                # Execute Tool
                self._emit("tool_executing", f"⚡ Calling tool `{tool_name}`", {"tool": tool_name, "args": tool_args})
                target_tool = self.tools[tool_name]
                
                try:
                    tool_result = await target_tool.execute(**tool_args)
                except Exception as e:
                    tool_result = BaseTool.ToolResult(success=False, output="", error=f"Tool crash: {str(e)}", exit_code=-1)

                snapshot_after = None
                if tool_result.success:
                    snapshot_after = self.snapshot_mgr.capture_snapshot(f"Step {subtask.id}: Completed {tool_name}")

                # Record in Flight Recorder
                record = StepRecord(
                    step_id=self.step_counter,
                    subtask_title=subtask.title,
                    prompt=step_prompt,
                    raw_response=raw_response,
                    thought=parsed_call.thought,
                    tool_name=tool_name,
                    tool_arguments=tool_args,
                    tool_success=tool_result.success,
                    tool_output=tool_result.output,
                    tool_error=tool_result.error,
                    tool_exit_code=tool_result.exit_code,
                    duration_ms=tool_result.duration_ms,
                    snapshot_before=checkpoint_snapshot,
                    snapshot_after=snapshot_after,
                )
                self.flight_recorder.record_step(record)
                self.step_counter += 1

                self._emit(
                    "tool_result",
                    f"Result of `{tool_name}`: {'✅ OK' if tool_result.success else '❌ Failed'}",
                    {"result": tool_result.model_dump()},
                )

                if tool_result.success:
                    last_tool_result_str = f"TOOL '{tool_name}' SUCCESS:\n{tool_result.output}"
                    # Informational tools (read_file, list_dir) do not complete a creation/modification subtask
                    if tool_name not in {"read_file", "list_dir"}:
                        subtask_succeeded = True
                else:
                    last_tool_result_str = f"TOOL '{tool_name}' FAILED (Exit {tool_result.exit_code}):\n{tool_result.error or tool_result.output}"
                    # If action failed, restore workspace to pre-step clean snapshot so bad partial edits don't corrupt the project
                    if self.config.auto_rollback and checkpoint_snapshot:
                        self._emit("rollback", f"⏪ Restoring workspace to clean snapshot before retry...")
                        self.snapshot_mgr.restore_snapshot(checkpoint_snapshot)

            if subtask_succeeded:
                subtask.status = "completed"
                self.completed_tasks.append(subtask.title)
                self._emit("step_complete", f"✅ Completed Subtask {subtask.id}: {subtask.title}")
            else:
                subtask.status = "failed"
                self._emit("error", f"❌ Subtask {subtask.id} failed after {self.config.max_step_retries} attempts.")
                if self.config.auto_rollback and checkpoint_snapshot:
                    self._emit("rollback", f"⏪ Reverting failed subtask to clean snapshot [{checkpoint_snapshot}]")
                    self.snapshot_mgr.restore_snapshot(checkpoint_snapshot)
                    record.rollback_occurred = True

        total_time = time.perf_counter() - start_time
        all_passed = all(s.status == "completed" for s in self.plan)
        final_status = "SUCCESS" if all_passed else "PARTIAL_FAILURE"

        summary_path = self.flight_recorder.finalize(goal, final_status, total_time)
        self._emit(
            "complete",
            f"🏁 Run finished with status {final_status} in {total_time:.2f}s. Report: {summary_path}",
            {"status": final_status, "duration_sec": total_time, "summary_file": str(summary_path)},
        )
        return all_passed
