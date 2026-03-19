#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/run.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT_DIR/run.py" "$@"
fi

echo "python3 not found. Please install Python 3.11+ first."
exit 1
