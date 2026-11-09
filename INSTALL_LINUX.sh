#!/usr/bin/env bash
# Execute as a child process; do not source this file.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 2
"${PYTHON_BIN:-python3}" "$ROOT/install_linux.py" "$@"
