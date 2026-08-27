# ⚡ Omikun: Autonomous AI Coding Harness

> **Disciplined Agentic Engineering Harness for Lightweight Local LLMs (Qwen 2.5 Coder, DeepSeek, Llama 3)**

Omikun transforms lightweight open-source models into rigorous, autonomous software engineering agents. It operates directly on your local machine with strict sandboxing, automated AST syntax & DOM contract verification, non-git in-memory snapshot rollbacks, and flight-recorder telemetry.

---

## 🌟 Key Capabilities

- **🧠 Local LLM First:** Optimized for qwen2.5-coder:7b via local Ollama inference with zero cloud dependency.
- **🛡️ Disciplined State Machine:** Breaks complex requests into test-driven subtasks with automated retries and root-cause reflection.
- **⏪ Safe Snapshot Rollbacks:** Captures in-memory and local disk snapshots to instantly revert failing steps without creating or polluting Git repositories.
- **🔍 Project Integrity & DOM Verifier:** Automatically validates JavaScript/Node syntax (
ode --check), Python bytecode (py_compile), CSS text contrast, and DOM ID contracts.
- **📊 Real-time Terminal Dashboard:** Beautiful Rich-powered live execution logs and JSONL flight-recorder trajectories.

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.10+**
- **[Ollama](https://ollama.ai)** running locally:
  `powershell
  ollama run qwen2.5-coder:7b
  `
- **Node.js** (Optional, for JavaScript syntax verification)

### 2. Installation
Clone the repository and install dependencies in a virtual environment:
`powershell
git clone https://github.com/amitsikdar37/Omikun-Ai-Harness.git
cd Omikun-Ai-Harness

python -m venv .venv
.venv\Scripts\activate
pip install -e .
`

### 3. Run Omikun
`powershell
omikun run "Build a modern interactive weather forecast web app with Tailwind CSS" --workspace ./weather-app
`

---

## 🛠️ CLI Usage

`	ext
usage: omikun [-h] [--model MODEL] [--ollama-url OLLAMA_URL] [--workspace WORKSPACE]
              [--temperature TEMP] [--max-retries RETRIES]
              goal

Arguments:
  goal                  The software engineering objective to accomplish
  --workspace, -w       Target project directory (default: current directory)
  --model, -m           Local model name in Ollama (default: qwen2.5-coder:7b)
  --ollama-url          Ollama API endpoint (default: http://localhost:11434)
  --max-retries         Max retry attempts per subtask (default: 6)
`

---

## 🧪 Running Tests

`powershell
pytest tests/ -v
`

---

## 📁 Repository Structure

`	ext
├── omikun/
│   ├── cli.py                  # CLI entry point
│   ├── config.py               # Central configuration
│   ├── core/
│   │   ├── orchestrator.py     # Central state machine & subtask runner
│   │   ├── snapshot_manager.py # In-memory snapshot rollback engine
│   │   └── flight_recorder.py  # JSONL telemetry & run summaries
│   ├── llm/
│   │   ├── client.py           # Async Ollama client
│   │   ├── parser.py           # Robust JSON repair & tool extractor
│   │   └── prompts.py          # Universal agent prompt system
│   ├── tools/
│   │   ├── filesystem.py       # read_file, write_file, patch_file, list_dir
│   │   ├── terminal.py         # PowerShell & bash sanitized execution
│   │   └── verifier.py         # Project integrity & DOM checker
│   └── ui/
│       └── dashboard.py        # Rich terminal UI
├── tests/                      # Automated test suite
└── pyproject.toml              # Build & dependency configuration
`

---

## 📄 License
MIT License. Open-source and free to use.
