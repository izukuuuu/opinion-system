---
trigger: always_on
---

For real python environment testing, please use `uv` with Python 3.11.

- Install dependencies: `uv sync`
- Run scripts with dependency management: `uv run python <script.py>`

## CUDA Support for BERTopic

PyTorch with CUDA 11.8 must be installed **manually** after `uv sync`:

```powershell
uv pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

⚠️ **Important**: After installing CUDA version, **do NOT use `uv run python`** as it will reinstall the CPU version from lockfile.

Instead, run scripts directly:
- **Backend server**: `.venv\Scripts\python.exe backend/server.py`
- **Other scripts**: `.venv\Scripts\python.exe <your_script.py>`
- **Or activate venv**: `.venv\Scripts\Activate.ps1` then `python <script.py>`

See workflow: `/setup-cuda` for full instructions.