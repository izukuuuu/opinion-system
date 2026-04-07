---
trigger: always_on
---

Use `uv` syntax for all Python operations in this project (Python 3.11).

## Python/Dependency Command Rules

- Sync lockfile dependencies:
  - `uv sync`
- Install/repair a package into the project venv:
  - `uv pip install --python .venv\Scripts\python.exe <package>`
- Run Python scripts without re-resolving environment:
  - `uv run --no-sync python <script.py>`

Do not use bare `pip install ...` or `python ...` directly unless explicitly required by workflow docs.

## CUDA Support for BERTopic

PyTorch CUDA 11.8 installation must still use `uv pip` targeting the project venv:

```powershell
uv pip install --python .venv\Scripts\python.exe --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

After CUDA install, prefer `uv run --no-sync python ...` to avoid lockfile-driven environment mutation.

Examples:
- Backend server: `uv run --no-sync python backend/server.py`
- Other scripts: `uv run --no-sync python <your_script.py>`

See workflow: `/setup-cuda` for full instructions.
