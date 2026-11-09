#!/usr/bin/env bash
# Rebuild the shipped Linux x86_64 TkDnD repair from pinned 2.9.5 source.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  printf '%s\n' 'Linux x86_64 is required for this artifact.' >&2; exit 2
fi
build="${1:-$root/.build-linux-x64}"
cmake -S "$root/tkdnd-2.9.5" -B "$build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build" --target tkdnd2.9.5 -j2
cp "$build/libtkdnd2.9.5.so" "$root/linux-x64/libtkdnd2.9.5.so"
sha256sum "$root/linux-x64/libtkdnd2.9.5.so"
