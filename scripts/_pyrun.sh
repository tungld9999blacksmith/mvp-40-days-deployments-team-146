#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Prefers the repository virtual environment, then usable PATH interpreters.
# Probe execution: Windows Store aliases can exist without a working Python.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Returns a visible error if no Python works; pre-push handles that separately.
set -u

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1
cd -- "$REPO_ROOT" || exit 1

for cand in "$REPO_ROOT/.venv/Scripts/python.exe" "$REPO_ROOT/.venv/bin/python" python python3; do
  if "$cand" -c 'import sys' </dev/null >/dev/null 2>&1; then
    exec "$cand" "$@"
  fi
done

if py -3 -c 'import sys' </dev/null >/dev/null 2>&1; then
  exec py -3 "$@"
fi

shopt -s nullglob
for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
  if "$cand" -c 'import sys' </dev/null >/dev/null 2>&1; then
    exec "$cand" "$@"
  fi
done

echo '[ai-log] No working Python found. Create the repository .venv or install Python.' >&2
exit 1
