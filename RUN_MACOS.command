#!/usr/bin/env bash
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 2
bash "$ROOT/RUN_POC.sh" "$@"
RESULT=$?
if [ "$RESULT" -ne 0 ]; then read -r -p 'Setup stopped. Press Enter to close this window. ' _; fi
exit "$RESULT"
