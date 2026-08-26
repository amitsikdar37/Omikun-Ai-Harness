import pytest
from omikun.llm.parser import ToolCallParser


def test_parse_clean_json():
    raw = '{"tool": "run_command", "arguments": {"command": "pytest -v"}}'
    parsed = ToolCallParser.parse(raw)
    assert parsed is not None
    assert parsed.tool_name == "run_command"
    assert parsed.arguments == {"command": "pytest -v"}
    assert parsed.thought is None


def test_parse_with_thought_and_code_fence():
    raw = """I need to create the main application file with a FastAPI server.

```json
{
  "thought": "Writing FastAPI entry point",
  "tool": "write_file",
  "arguments": {
    "file_path": "app/main.py",
    "content": "from fastapi import FastAPI\napp = FastAPI()"
  }
}
```
"""
    parsed = ToolCallParser.parse(raw)
    assert parsed is not None
    assert parsed.tool_name == "write_file"
    assert parsed.arguments["file_path"] == "app/main.py"
    assert "FastAPI" in parsed.arguments["content"]
    assert "FastAPI entry point" in (parsed.thought or "")


def test_parse_think_tags_deepseek():
    raw = """<think>
We need to check the test results first.
Let's run pytest.
</think>
```json
{
  "name": "run_command",
  "parameters": {
    "command": "pytest"
  }
}
```"""
    parsed = ToolCallParser.parse(raw)
    assert parsed is not None
    assert parsed.tool_name == "run_command"
    assert parsed.arguments == {"command": "pytest"}
    assert "check the test results" in (parsed.thought or "")


def test_parse_malformed_trailing_commas():
    raw = '{"tool": "list_dir", "arguments": {"sub_path": "src",},}'
    parsed = ToolCallParser.parse(raw)
    assert parsed is not None
    assert parsed.tool_name == "list_dir"
    assert parsed.arguments == {"sub_path": "src"}


def test_parse_flat_json():
    raw = '{"tool": "read_file", "file_path": "README.md", "line_numbers": true}'
    parsed = ToolCallParser.parse(raw)
    assert parsed is not None
    assert parsed.tool_name == "read_file"
    assert parsed.arguments == {"file_path": "README.md", "line_numbers": True}
