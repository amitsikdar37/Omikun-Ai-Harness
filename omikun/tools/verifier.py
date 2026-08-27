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
                    import collections
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    
                    # Check for complete HTML structure
                    if "<html" not in content.lower() or "<body" not in content.lower():
                        issues.append(f"❌ Incomplete HTML in '{rel_path}': Missing <html> or <body> tags. Write the full valid HTML document starting with <!DOCTYPE html>.")

                    # Check for duplicate IDs in HTML
                    all_ids = re.findall(r'id=["\']([^"\']+)["\']', content)
                    id_counts = collections.Counter(all_ids)
                    for dom_id, count in id_counts.items():
                        if count > 1:
                            issues.append(f"❌ Duplicate DOM ID in '{rel_path}': Found {count} elements with id=\"{dom_id}\". Each ID in index.html must be unique.")

                    # Check for duplicate search inputs
                    search_inputs = re.findall(r'<input[^>]+(?:type=["\']text["\']|id=["\'][^"\']*(?:search|country|city)[^"\']*["\'])[^>]*>', content, re.IGNORECASE)
                    if len(search_inputs) > 1:
                        issues.append(f"❌ Duplicate Input Cards in '{rel_path}': Found {len(search_inputs)} text/search input boxes. Keep a single unified card/form.")

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

                    # Check input contrast (prevent invisible text)
                    if "<input" in content.lower():
                        # Detect light background containers (e.g. bg-white, bg-gray-100, bg-slate-100)
                        is_light_bg = "bg-white" in content or "bg-gray-1" in content or "bg-slate-1" in content or "bg-zinc-1" in content
                        input_classes = re.findall(r'<input[^>]+class=["\']([^"\']+)["\']', content, re.IGNORECASE)
                        for inp_class in input_classes:
                            if is_light_bg and ("text-white" in inp_class or "text-slate-100" in inp_class):
                                issues.append(
                                    f"❌ Input Contrast Bug in '{rel_path}': <input> has 'text-white' inside a light background ('bg-white'/'bg-gray-100'). "
                                    f"Text will be invisible when typing! Use dark text styling like `class=\"text-slate-900 bg-slate-100 p-3 rounded-xl border border-slate-300\"`."
                                )

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

                    # Check for Open-Meteo property bugs
                    if "current_weather.temperature_2m" in js_content:
                        issues.append(f"❌ Open-Meteo Property Bug in '{rel_path}': In Open-Meteo current_weather object, the property is `current_weather.temperature` (not temperature_2m). Access `weatherData.current_weather.temperature`.")

                    # Check for hardcoded static coordinates in dynamic search apps
                    if "latitude=51.5" in js_content and ("country" in js_content.lower() or "city" in js_content.lower()) and "geocoding" not in js_content.lower():
                        issues.append(
                            f"❌ Static Coordinates in '{rel_path}': Fetching fixed London coordinates (51.5, -0.12) ignores user input. "
                            f"Use Open-Meteo Geocoding to lookup coordinates dynamically: `https://geocoding-api.open-meteo.com/v1/search?name=${{encodeURIComponent(query)}}&count=1`."
                        )

                    # Check for placeholder API keys (e.g. YOUR_API_KEY)
                    if re.search(r'YOUR_[A-Z_]*KEY', js_content, re.IGNORECASE) or ("api.openweathermap.org" in js_content and "appid=" in js_content):
                        issues.append(
                            f"❌ Unusable API Key in '{rel_path}': Found placeholder 'YOUR_API_KEY' or OpenWeatherMap requiring a private key. "
                            f"Use a zero-key public API like Open-Meteo (`https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true`) or local mock data so the app works immediately without API keys."
                        )

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
                        referenced_ids = set(re.findall(r'document\.getElementById\(["\']([^"\']+)["\']\)', js_content))
                        referenced_ids.update(re.findall(r'document\.querySelector\(["\']#([^"\'\s,>+~]+)["\']\)', js_content))
                        for dom_id in referenced_ids:
                            if f'id="{dom_id}"' not in html_text and f"id='{dom_id}'" not in html_text and f'id=`{dom_id}`' not in html_text:
                                issues.append(f"❌ DOM ID Mismatch: '{rel_path}' queries '#{dom_id}' (`document.getElementById(\"{dom_id}\")`), but no element with id=\"{dom_id}\" exists in 'index.html'!")

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
