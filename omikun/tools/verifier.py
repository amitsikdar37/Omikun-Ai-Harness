import os
import re
from pathlib import Path
from typing import Any, List
from omikun.tools.base import BaseTool, ToolResult


class ProjectVerifierTool(BaseTool):
    """Verifies project integrity, checks for missing referenced assets, empty files, and broken links."""

    name = "verify_project"
    description = (
        "Scan the project workspace for missing files, empty files, broken HTML asset links "
        "(<script src>, <link href>), and basic project completeness."
    )
    parameters = {
        "type": "object",
        "properties": {
            "entry_file": {
                "type": "string",
                "description": "Optional entry point to verify (e.g. 'index.html', 'src/index.html', 'main.py').",
                "default": "",
            }
        },
    }

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    async def execute(self, entry_file: str = "", **kwargs: Any) -> ToolResult:
        issues: List[str] = []
        verified_items: List[str] = []

        ignore_dirs = {".git", ".omikun", "__pycache__", ".venv", "node_modules"}

        # 1. Scan all HTML files for missing CSS/JS asset references
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for f in files:
                full_path = Path(root) / f
                rel_path = full_path.relative_to(self.workspace_path)

                # Check for empty files
                if full_path.stat().st_size == 0 and f != "__init__.py":
                    issues.append(f"⚠️ Empty file: '{rel_path}' has 0 bytes. Implement its contents.")

                if f.endswith(".html"):
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    
                    # Check for modern UI styling (Tailwind, modern CSS, or design framework)
                    has_tailwind = "tailwindcss.com" in content or "cdn.jsdelivr.net" in content or "styles.css" in content
                    has_interactive_elements = "<button" in content.lower() or "input" in content.lower()
                    has_script = "<script" in content.lower()

                    if not has_interactive_elements:
                        issues.append(f"❌ Poor UI: '{rel_path}' lacks interactive elements (<button>, search input, etc.). Add complete UI controls.")

                    # Verify that all local .js files in the same directory are linked in index.html
                    for js_file in full_path.parent.glob("*.js"):
                        js_name = js_file.name
                        if not re.search(rf'<script[^>]+src=["\'](\./)?{re.escape(js_name)}["\']', content, re.IGNORECASE):
                            issues.append(f"❌ Missing Script Link: '{rel_path}' does not include '<script src=\"{js_name}\"></script>'. Add the script tag before </body> so your JavaScript executes.")

                    # Check input contrast (prevent white text on white input)
                    if "<input" in content.lower():
                        if "text-slate-" not in content and "text-black" not in content and "text-gray-9" not in content and "bg-white/10" not in content and "bg-slate-" not in content and "bg-transparent" not in content:
                            issues.append(f"⚠️ Input Contrast Warning: '{rel_path}' input might have invisible text. Ensure <input> has readable styling like `class=\"bg-white/10 text-white placeholder-slate-400 p-3 rounded-xl border border-white/20\"` or `class=\"text-slate-900 bg-white p-3 rounded-xl\"`.")

                    # Find all linked scripts: <script src="...">
                    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
                    for src in script_srcs:
                        if src.startswith("http://") or src.startswith("https://") or src.startswith("//"):
                            continue
                        target_asset = (full_path.parent / src).resolve()
                        if not target_asset.exists():
                            issues.append(f"❌ Missing Script: '{rel_path}' references '<script src=\"{src}\">', but '{src}' does not exist on disk!")
                        else:
                            verified_items.append(f"Linked script found: {src}")

                    # Find all linked stylesheets: <link href="...">
                    css_hrefs = re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', content, re.IGNORECASE)
                    for href in css_hrefs:
                        if href.startswith("http://") or href.startswith("https://") or href.startswith("//"):
                            continue
                        target_css = (full_path.parent / href).resolve()
                        if not target_css.exists():
                            issues.append(f"❌ Missing Stylesheet: '{rel_path}' references '<link href=\"{href}\">', but '{href}' does not exist on disk!")
                        else:
                            verified_items.append(f"Linked stylesheet found: {href}")

                # 2. Check JavaScript syntax and implementation completeness
                if f.endswith(".js"):
                    import subprocess
                    js_content = full_path.read_text(encoding="utf-8", errors="replace")

                    # Check for stub comments
                    stub_patterns = [r"//\s*(?:todo|handle|implement|add logic|fill in)", r"/\*\s*(?:todo|handle|implement)\s*\*/"]
                    for pat in stub_patterns:
                        if re.search(pat, js_content, re.IGNORECASE):
                            issues.append(f"❌ Incomplete JS: '{rel_path}' contains stub/placeholder comments. Write the complete, working code instead of placeholders.")
                            break

                    # Check for hallucinated Open-Meteo API properties (e.g. current_weather.temperature_2m)
                    if "current_weather.temperature_2m" in js_content or "current_weather.relativehumidity" in js_content:
                        issues.append(f"❌ Hallucinated API Property: '{rel_path}' accesses 'current_weather.temperature_2m' or 'current_weather.relativehumidity'. In Open-Meteo API v1 forecast with `current=temperature_2m,relative_humidity_2m,wind_speed_10m`, access `data.current.temperature_2m`, `data.current.relative_humidity_2m`, and `data.current.wind_speed_10m`.")

                    # Check for node syntax validity
                    try:
                        proc = subprocess.run(["node", "--check", str(full_path)], capture_output=True, text=True, timeout=5)
                        if proc.returncode != 0:
                            err_msg = proc.stderr.strip() or "Syntax error in JavaScript file."
                            issues.append(f"❌ JavaScript Syntax Error in '{rel_path}':\n{err_msg}\nFile appears incomplete or broken. Write the full valid JavaScript code.")
                        else:
                            verified_items.append(f"JS syntax verified: {rel_path}")
                    except Exception:
                        pass

                    # Check DOM ID consistency between index.html and app.js
                    html_path = full_path.parent / "index.html"
                    if html_path.exists():
                        html_text = html_path.read_text(encoding="utf-8", errors="replace")
                        referenced_ids = re.findall(r'document\.getElementById\(["\']([^"\']+)["\']\)', js_content)
                        for dom_id in referenced_ids:
                            if f'id="{dom_id}"' not in html_text and f"id='{dom_id}'" not in html_text:
                                issues.append(f"❌ DOM ID Mismatch: '{rel_path}' references 'document.getElementById(\"{dom_id}\")', but no element with id=\"{dom_id}\" exists in 'index.html'!")

                # 3. Check Python syntax using py_compile
                if f.endswith(".py") and f != "__init__.py":
                    import py_compile
                    try:
                        py_compile.compile(str(full_path), doraise=True)
                        verified_items.append(f"Python syntax verified: {rel_path}")
                    except Exception as e:
                        issues.append(f"❌ Python Syntax Error in '{rel_path}': {str(e)}")

        if issues:
            error_report = "\n".join(issues)
            return ToolResult(
                success=False,
                output="",
                error=f"Project integrity check failed with {len(issues)} issue(s):\n{error_report}\nPlease create or fix the missing files.",
                exit_code=1,
                metadata={"issues_count": len(issues)},
            )

        output_msg = "✅ Project integrity check passed! All referenced assets and files exist."
        if verified_items:
            output_msg += "\n" + "\n".join([f"  - {v}" for v in verified_items])

        return ToolResult(success=True, output=output_msg, metadata={"issues_count": 0})
