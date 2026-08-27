import pytest
from pathlib import Path
from omikun.tools.filesystem import ReadFileTool, WriteFileTool, PatchFileTool, ListDirTool
from omikun.tools.terminal import TerminalTool


@pytest.mark.asyncio
async def test_filesystem_tools(tmp_path: Path):
    write_tool = WriteFileTool(tmp_path)
    read_tool = ReadFileTool(tmp_path)
    patch_tool = PatchFileTool(tmp_path)
    list_tool = ListDirTool(tmp_path)

    # 1. Write file
    res = await write_tool.execute(file_path="src/calc.py", content="def add(a, b):\n    return a - b\n")
    assert res.success is True
    assert (tmp_path / "src/calc.py").exists()

    # 2. Read file
    res = await read_tool.execute(file_path="src/calc.py", line_numbers=True)
    assert res.success is True
    assert "def add(a, b):" in res.output
    assert "   1 |" in res.output

    # 3. Patch file (fix subtract to add)
    res = await patch_tool.execute(
        file_path="src/calc.py",
        target_content="return a - b",
        replacement_content="return a + b",
    )
    assert res.success is True

    # Verify patched content
    res = await read_tool.execute(file_path="src/calc.py", line_numbers=False)
    assert "return a + b" in res.output

    # 4. List directory
    res = await list_tool.execute(sub_path=".")
    assert res.success is True
    assert "calc.py" in res.output


@pytest.mark.asyncio
async def test_terminal_tool(tmp_path: Path):
    term = TerminalTool(tmp_path)
    res = await term.execute(command="python -c \"print('OMIKUN_OK')\"")
    assert res.success is True
    assert "OMIKUN_OK" in res.output
    assert res.exit_code == 0


@pytest.mark.asyncio
async def test_project_verifier_tool(tmp_path: Path):
    from omikun.tools.verifier import ProjectVerifierTool

    verifier = ProjectVerifierTool(tmp_path)

    # Create HTML referencing missing CSS and JS
    html_file = tmp_path / "index.html"
    html_file.write_text('<!DOCTYPE html><html><body><link rel="stylesheet" href="styles.css"><input id="search" class="text-slate-900 bg-white"><button>Search</button><script src="app.js"></script></body></html>', encoding="utf-8")

    # Verification should fail
    res = await verifier.execute()
    assert res.success is False
    assert "Missing Script" in (res.error or "")
    assert "Missing Stylesheet" in (res.error or "")

    # Now create the assets
    (tmp_path / "styles.css").write_text("body { background: #000; }", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log('weather ready');", encoding="utf-8")

    # Verification should now pass
    res = await verifier.execute()
    assert res.success is True
