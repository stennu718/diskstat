#!/usr/bin/env bash
# DiskStat launcher — works inside or outside venv
# If 'diskstat' is on PATH (via pip install), use it directly.
# Otherwise fall back to the venv install.
if command -v diskstat &>/dev/null; then
    exec diskstat "$@"
elif [ -f "$(dirname "$0")/.venv/bin/diskstat" ]; then
    exec "$(dirname "$0")/.venv/bin/diskstat" "$@"
else
    echo "diskstat not found. Run: uv venv .venv && uv pip install -e ." >&2
    exit 1
fi
