---
name: opinion-system-runtime
description: Start, verify, and troubleshoot the local OpinionSystem runtime. Use when working on repository bootstrapping, frontend/backend startup, environment checks, run scripts, database prerequisites, or deciding whether a file belongs in migratable backup config versus runtime placeholder generation.
---

# OpinionSystem Runtime

## Scope

Use this skill when the task involves local startup or runtime wiring for this repository.

Typical triggers:
- Start the frontend and backend locally
- Update `run.py`, `start_win.bat`, or `start_mac.sh`
- Check whether `uv pip`, `npm`, and the configured database are available
- Decide which local files should be exported by settings backup
- Decide which missing files or directories should be created automatically at runtime

## Runtime Facts

- Use the project interpreter only: `F:\opinion-system\.venv\Scripts\python.exe`
- Install Python packages with explicit interpreter:
  - `uv pip install --python F:\opinion-system\.venv\Scripts\python.exe <pkg>`
  - `uv pip list --python F:\opinion-system\.venv\Scripts\python.exe`
- Avoid `uv run` unless explicitly required
- Frontend dev server lives in `frontend/` and defaults to port `5173`
- Backend web server entry is `backend/server.py` and defaults to port `8000`
- `backend/main.py` is the CLI pipeline entry, not the frontend-facing web server entry
- Frontend uses `frontend/.env.local` / Vite env values for backend URL wiring
- Database connection source of truth is `backend/configs/databases.yaml`
- Local development should recommend PostgreSQL first

## Startup Workflow

1. Check the host prerequisites before starting services:
   - `uv pip`
   - `npm`
   - active database reachability from `backend/configs/databases.yaml`
2. Ensure local placeholders exist if missing:
   - `backend/.env`
   - `backend/configs/databases.yaml`
   - `frontend/.env.local`
   - `backend/logs/`
   - `backend/tmp/`
   - `backend/data/projects/`
3. Install dependencies only after the prerequisite checks pass
4. Start backend first and wait for `/api/status`
5. Start frontend second and wait for `http://127.0.0.1:5173`
6. Open browser tabs only after both services are confirmed reachable

## Backup Boundary

Treat these as migratable configuration and include them in settings backup:
- `config.yaml`
- `backend/configs/**`
- `backend/server_support/hot_overview_filters.yaml`
- `backend/.env` when it contains user-managed credentials or overrides

Treat these as runtime-generated placeholders and let startup scripts recreate them:
- `frontend/.env.local`
- empty `backend/.env`
- empty or missing `backend/configs/databases.yaml`
- runtime-only directories such as `backend/logs/` and `backend/tmp/`

Do not put `backend/data/**` into the settings backup. That is project data, cache, or generated artifacts, not portable settings.

## Preferred Commands

Use repo-root commands:

```powershell
F:\opinion-system\.venv\Scripts\python.exe run.py
```

Windows wrapper:

```bat
start_win.bat
```

macOS wrapper:

```bash
./start_mac.sh
```

## Change Rules

- Keep route pages in place if a feature is unfinished; hide the sidebar entry first if the user only wants it removed from navigation
- When changing backup behavior, update both backend backup allowlist logic and the frontend archive page copy
- When changing startup behavior, keep `README.md`, `run.py`, and wrapper scripts aligned
