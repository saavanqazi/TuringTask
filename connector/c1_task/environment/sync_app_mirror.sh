#!/bin/sh
# Refreshes environment/_app/, the build-context mirror of the task root.
# Run after editing ANY task-root file.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")

rm -rf "$HERE/_app"
mkdir -p "$HERE/_app"
cp "$ROOT/task.toml" "$ROOT/instruction.md" "$HERE/_app/"
cp -R "$ROOT/tests" "$HERE/_app/"
find "$HERE/_app" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$HERE/_app" -name '*.pyc' -delete 2>/dev/null || true
echo "_app mirror refreshed from $ROOT"
