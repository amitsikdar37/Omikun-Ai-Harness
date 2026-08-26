import json
import re
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel


class ParsedToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    thought: Optional[str] = None
    raw_response: str


class ToolCallParser:
    """Robust parser for extracting tool calls from local model outputs with auto-repair."""

    @staticmethod
    def extract_thought_and_json(text: str) -> Tuple[Optional[str], str]:
        """Separate chain-of-thought or reasoning text from JSON payload."""
        text = text.strip()
        thought: Optional[str] = None

        # Check for <think>...</think> tags (e.g. DeepSeek-R1 / Qwen-R1)
        think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        if think_match:
            thought = think_match.group(1).strip()
            text = text.replace(think_match.group(0), "").strip()

        # Check for markdown code blocks ```json ... ``` or ``` ... ```
        code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if code_block_match:
            block_content = code_block_match.group(1).strip()
            start_idx = block_content.find("{")
            end_idx = block_content.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                json_str = block_content[start_idx : end_idx + 1].strip()
                if not thought:
                    pre_text = text[:code_block_match.start()].strip()
                    if pre_text:
                        thought = pre_text
                return thought, json_str

        # Find first '{' and last '}'
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = text[start_idx : end_idx + 1].strip()
            if not thought and start_idx > 0:
                thought = text[:start_idx].strip()
            return thought, json_str

        return thought, text

    @classmethod
    def repair_json_string(cls, json_str: str) -> str:
        """Fix common malformed JSON errors from local models."""
        s = json_str.strip()
        # Remove trailing commas before closing braces/brackets
        s = re.sub(r",\s*([\}\]])", r"\1", s)
        # Fix unescaped backslashes in Windows paths (e.g. C:\path -> C:\\path)
        # (Be careful not to escape already escaped ones)
        s = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r"\\\\", s)
        return s

    @classmethod
    def parse(cls, raw_output: str) -> Optional[ParsedToolCall]:
        """Attempt to parse a tool call from LLM generation."""
        thought, json_candidate = cls.extract_thought_and_json(raw_output)
        
        parsed_dict: Optional[Dict[str, Any]] = None
        
        # 1. Try direct json.loads (strict=False allows control characters like unescaped newlines)
        try:
            parsed_dict = json.loads(json_candidate, strict=False)
        except Exception:
            # 2. Try repaired json
            repaired = cls.repair_json_string(json_candidate)
            try:
                parsed_dict = json.loads(repaired, strict=False)
            except Exception:
                pass

        if not parsed_dict or not isinstance(parsed_dict, dict):
            return None

        # Normalize tool name key
        tool_name = (
            parsed_dict.get("tool")
            or parsed_dict.get("tool_name")
            or parsed_dict.get("name")
            or parsed_dict.get("action")
            or parsed_dict.get("function")
        )

        # Normalize arguments key
        arguments = (
            parsed_dict.get("arguments")
            or parsed_dict.get("parameters")
            or parsed_dict.get("args")
            or parsed_dict.get("inputs")
        )

        # If model returned keys flatly: {"tool": "write_file", "file_path": "...", "content": "..."}
        if tool_name and arguments is None:
            arguments = {k: v for k, v in parsed_dict.items() if k not in {"tool", "tool_name", "name", "action", "function", "thought", "reasoning"}}

        if not tool_name or not isinstance(tool_name, str):
            return None

        if arguments is None or not isinstance(arguments, dict):
            arguments = {}

        # Combine or set thought from JSON if available
        json_thought = parsed_dict.get("thought") or parsed_dict.get("reasoning")
        if json_thought and isinstance(json_thought, str):
            if thought and thought != json_thought:
                thought = f"{thought}\n{json_thought}"
            else:
                thought = json_thought

        return ParsedToolCall(
            tool_name=tool_name,
            arguments=arguments,
            thought=thought,
            raw_response=raw_output,
        )
