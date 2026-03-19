#!/usr/bin/env python3
"""Bootstrap and run the OpinionSystem frontend and backend."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"
FRONTEND_ENV_FILE = FRONTEND_DIR / ".env.local"
DATABASES_CONFIG_FILE = BACKEND_DIR / "configs" / "databases.yaml"

DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173


@dataclass(frozen=True)
class Runtime:
    system: str
    repo_python: Path
    npm_executable: str
    uv_executable: str


def log(message: str) -> None:
    print(f"[run.py] {message}", flush=True)


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    log(f"Running: {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd) if cwd else None, env=env, check=True)


def find_command(*names: str) -> str | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def find_uv() -> str | None:
    direct = find_command("uv")
    if direct:
        return direct

    candidates = [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def ensure_python_version() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("run.py requires Python 3.11 or newer.")


def ensure_repo_venv(system: str) -> Path:
    repo_python = ROOT / ".venv" / ("Scripts/python.exe" if system == "windows" else "bin/python")
    if repo_python.exists():
        return repo_python

    ensure_python_version()
    log("Creating project virtual environment in .venv")
    run_command([sys.executable, "-m", "venv", str(ROOT / ".venv")], cwd=ROOT)

    if not repo_python.exists():
        raise SystemExit(f"Virtual environment was created, but {repo_python} was not found.")
    return repo_python


def require_uv(system: str) -> str:
    uv_executable = find_uv()
    if uv_executable:
        result = subprocess.run(
            [uv_executable, "pip", "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return uv_executable

        raise SystemExit(
            "uv is installed but `uv pip` is not available.\n"
            "Please reinstall uv and try again."
        )

    if system == "windows":
        raise SystemExit(
            "uv was not found.\n"
            "Please install it first, for example:\n"
            "powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""
        )

    raise SystemExit(
        "uv was not found.\n"
        "Please install it first, for example:\n"
        "curl -LsSf https://astral.sh/uv/install.sh | sh"
    )


def detect_runtime() -> Runtime:
    system = platform.system().lower()
    if system not in {"windows", "darwin", "linux"}:
        raise SystemExit(f"Unsupported operating system: {platform.system()}")

    repo_python = ensure_repo_venv(system)
    uv_executable = require_uv(system)

    npm_executable = find_command("npm.cmd", "npm") if system == "windows" else find_command("npm")
    if not npm_executable:
        if system == "windows":
            raise SystemExit(
                "npm was not found.\n"
                "Please install Node.js 18+ first, for example:\n"
                "winget install OpenJS.NodeJS.LTS"
            )
        raise SystemExit(
            "npm was not found.\n"
            "Please install Node.js 18+ first, for example:\n"
            "brew install node"
        )

    return Runtime(
        system=system,
        repo_python=repo_python,
        npm_executable=npm_executable,
        uv_executable=uv_executable,
    )


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def ensure_runtime_placeholders(backend_port: int) -> None:
    for path in (
        BACKEND_DIR / "configs",
        BACKEND_DIR / "logs",
        BACKEND_DIR / "tmp",
        BACKEND_DIR / "data",
        BACKEND_DIR / "data" / "projects",
    ):
        path.mkdir(parents=True, exist_ok=True)

    if not DATABASES_CONFIG_FILE.exists():
        DATABASES_CONFIG_FILE.write_text("", encoding="utf-8")
        log("Created empty backend/configs/databases.yaml placeholder.")

    if not BACKEND_ENV_FILE.exists():
        BACKEND_ENV_FILE.write_text(
            "# Optional local credentials for backend tasks.\n"
            "DASHSCOPE_API_KEY=\n"
            "OPENAI_API_KEY=\n"
            "OPENAI_BASE_URL=\n",
            encoding="utf-8",
        )
        log("Created backend/.env placeholder.")

    if not FRONTEND_ENV_FILE.exists():
        FRONTEND_ENV_FILE.write_text(
            f"VITE_API_BASE_URL=http://127.0.0.1:{backend_port}/api\n",
            encoding="utf-8",
        )
        log("Created frontend/.env.local with default API endpoint.")


def _clean_yaml_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    return value


def load_active_database_url() -> str | None:
    if not DATABASES_CONFIG_FILE.exists():
        return None

    active_connection: str | None = None
    fallback_url: str | None = None
    current_connection_id: str | None = None
    connection_urls: dict[str, str] = {}

    for raw_line in DATABASES_CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("active:"):
            active_connection = _clean_yaml_value(stripped.split(":", 1)[1])
            continue

        if stripped.startswith("db_url:"):
            fallback_url = _clean_yaml_value(stripped.split(":", 1)[1])
            continue

        if stripped.startswith("- id:"):
            current_connection_id = _clean_yaml_value(stripped.split(":", 1)[1])
            continue

        if current_connection_id and stripped.startswith("url:"):
            connection_urls[current_connection_id] = _clean_yaml_value(stripped.split(":", 1)[1])

    if active_connection and active_connection in connection_urls:
        return connection_urls[active_connection]
    if fallback_url:
        return fallback_url
    if connection_urls:
        return next(iter(connection_urls.values()))
    return None


def parse_database_target(database_url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(database_url)
    engine = parsed.scheme.split("+", 1)[0].lower()
    host = parsed.hostname or "localhost"
    if parsed.port:
        port = parsed.port
    elif engine == "postgresql":
        port = 5432
    elif engine == "mysql":
        port = 3306
    else:
        raise SystemExit(f"Unsupported database engine in config: {engine}")
    return engine, host, port


def require_database() -> None:
    database_url = load_active_database_url()
    if not database_url:
        raise SystemExit(
            "No database connection was found in backend/configs/databases.yaml.\n"
            "Please configure the active database before starting the backend."
        )

    engine, host, port = parse_database_target(database_url)
    try:
        with socket.create_connection((host, port), timeout=3):
            log(f"Database is reachable: {engine}://{host}:{port}")
    except OSError:
        if engine == "postgresql":
            install_tip = (
                "Please install or start PostgreSQL, then confirm backend/configs/databases.yaml "
                f"points to a reachable service ({host}:{port})."
            )
        elif engine == "mysql":
            install_tip = (
                "Please install or start MySQL, then confirm backend/configs/databases.yaml "
                f"points to a reachable service ({host}:{port})."
            )
        else:
            install_tip = f"Please make sure the database service at {host}:{port} is running."

        raise SystemExit(
            f"Database is not reachable: {engine}://{host}:{port}\n"
            f"{install_tip}"
        )


def backend_dependencies_ready(repo_python: Path) -> bool:
    command = [
        str(repo_python),
        "-c",
        "import flask, flask_cors, openai, pandas, yaml; import lancedb",
    ]
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    return result.returncode == 0


def frontend_dependencies_ready() -> bool:
    node_modules = FRONTEND_DIR / "node_modules"
    package_lock = FRONTEND_DIR / "package-lock.json"
    if not node_modules.exists():
        return False
    if package_lock.exists() and node_modules.stat().st_mtime < package_lock.stat().st_mtime:
        return False
    return True


def install_backend_dependencies(runtime: Runtime, force: bool) -> None:
    if not force and backend_dependencies_ready(runtime.repo_python):
        log("Backend dependencies already look ready.")
        return

    log("Installing backend dependencies with uv pip.")
    run_command(
        [
            runtime.uv_executable,
            "pip",
            "install",
            "--python",
            str(runtime.repo_python),
            "-r",
            str(BACKEND_DIR / "requirements.txt"),
        ],
        cwd=ROOT,
    )


def install_frontend_dependencies(runtime: Runtime, force: bool) -> None:
    if not force and frontend_dependencies_ready():
        log("Frontend dependencies already look ready.")
        return

    log("Installing frontend dependencies with npm.")
    run_command([runtime.npm_executable, "install"], cwd=FRONTEND_DIR)


def stream_output(name: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen[str]:
    log(f"Starting {name}: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    threading.Thread(target=stream_output, args=(name, process), daemon=True).start()
    return process


def wait_for_url(url: str, *, name: str, process: subprocess.Popen[str], timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"{name} exited before it became ready.")
        try:
            with urllib.request.urlopen(url, timeout=2):
                log(f"{name} is ready at {url}")
                return
        except Exception:
            time.sleep(1)
    raise SystemExit(f"Timed out while waiting for {name} at {url}")


def open_browser(urls: list[str]) -> None:
    for url in urls:
        log(f"Opening browser: {url}")
        webbrowser.open_new_tab(url)
        time.sleep(0.3)


def terminate_process(name: str, process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    log(f"Stopping {name}.")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def monitor_processes(processes: dict[str, subprocess.Popen[str]]) -> None:
    while True:
        for name, process in processes.items():
            code = process.poll()
            if code is not None:
                raise SystemExit(f"{name} exited with code {code}.")
        time.sleep(1)


def build_backend_env(backend_port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(parse_env_file(BACKEND_ENV_FILE))
    env["OPINION_BACKEND_PORT"] = str(backend_port)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def build_frontend_env(backend_port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}/api"
    env["VITE_BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
    env["BROWSER"] = "none"
    return env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start OpinionSystem frontend and backend.")
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation checks.")
    parser.add_argument("--force-install", action="store_true", help="Force reinstall backend and frontend dependencies.")
    parser.add_argument("--backend-only", action="store_true", help="Start only the backend service.")
    parser.add_argument("--frontend-only", action="store_true", help="Start only the frontend service.")
    parser.add_argument(
        "--browser",
        choices=("both", "frontend", "backend", "none"),
        default="both",
        help="Choose which service URLs to open after startup.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.backend_only and args.frontend_only:
        raise SystemExit("Cannot use --backend-only and --frontend-only together.")
    if args.backend_port <= 0 or args.frontend_port <= 0:
        raise SystemExit("Ports must be positive integers.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    runtime = detect_runtime()
    ensure_runtime_placeholders(args.backend_port)

    if not args.frontend_only:
        require_database()

    if not args.skip_install:
        if not args.frontend_only:
            install_backend_dependencies(runtime, args.force_install)
        if not args.backend_only:
            install_frontend_dependencies(runtime, args.force_install)

    processes: dict[str, subprocess.Popen[str]] = {}
    browser_urls: list[str] = []

    try:
        if not args.frontend_only:
            backend_process = start_process(
                "backend",
                [str(runtime.repo_python), str(BACKEND_DIR / "server.py")],
                cwd=ROOT,
                env=build_backend_env(args.backend_port),
            )
            processes["backend"] = backend_process
            wait_for_url(
                f"http://127.0.0.1:{args.backend_port}/api/status",
                name="backend",
                process=backend_process,
            )

        if not args.backend_only:
            frontend_process = start_process(
                "frontend",
                [
                    runtime.npm_executable,
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(args.frontend_port),
                ],
                cwd=FRONTEND_DIR,
                env=build_frontend_env(args.backend_port),
            )
            processes["frontend"] = frontend_process
            wait_for_url(
                f"http://127.0.0.1:{args.frontend_port}",
                name="frontend",
                process=frontend_process,
            )

        if args.browser != "none":
            if args.browser in {"both", "frontend"} and "frontend" in processes:
                browser_urls.append(f"http://127.0.0.1:{args.frontend_port}")
            if args.browser in {"both", "backend"} and "backend" in processes:
                browser_urls.append(f"http://127.0.0.1:{args.backend_port}/api/status")
            if browser_urls:
                open_browser(browser_urls)

        log("Services are running. Press Ctrl+C to stop them.")
        monitor_processes(processes)
    except KeyboardInterrupt:
        log("Received Ctrl+C, shutting down.")
    finally:
        for name, process in reversed(list(processes.items())):
            terminate_process(name, process)


if __name__ == "__main__":
    main()
