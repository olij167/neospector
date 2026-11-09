#!/usr/bin/env bash
# Run this file as a child process. Do not source it into your shell.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 2
PYTHON="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf '%s\n' 'SAFE STOP: Python 3.10+ is required. No files were changed.' >&2
  exit 2
fi
"$PYTHON" "$ROOT/bootstrap.py" "$@"
