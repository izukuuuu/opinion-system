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

## Frontend Writing Guardrails
- Frontend copy must not expose backend implementation details such as config file paths, YAML filenames, storage keys, internal field names, or server-side directory structure.
- When frontend needs to describe shared configuration, use user-facing language like “共享配置” or “项目排除词设置”, not backend terms like `settings.project_stopwords` or `backend/configs/...`.
- If a page needs technical traceability for debugging, keep it in logs or developer tools, not primary user-facing UI copy.
