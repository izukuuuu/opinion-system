# Project Runtime Notes

## Environment
- Use project interpreter only: `F:\opinion-system\.venv\Scripts\python.exe`
- Do not rely on system `python` from WindowsApps.
- Package operations must use `uv pip` with explicit interpreter:
  - `uv pip install --python F:\opinion-system\.venv\Scripts\python.exe <pkg>`
  - `uv pip list --python F:\opinion-system\.venv\Scripts\python.exe`

## Command Conventions
- Run backend-local scripts from repo root with absolute `.venv` python.
- Avoid `uv run` unless explicitly needed, because it may trigger environment sync side effects.

## Hot Overview Pipeline
- Default mode is `fast`.
- API supports `mode=fast|research`.
- `fast` mode includes lightweight evidence fetch.
- `research` mode enables heavier research branch (and optional playwright fallback if installed).
