#!/usr/bin/env bash
set -euo pipefail
# /solution is docker-cp'd owned by the uploading uid, so --write-back can't
# rewrite golden_trajectory.json in place. Work from a private copy.
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp -R /solution "$WORK/solution"
python3 "$WORK/solution/solve.py" --task-dir "$WORK" --write-back "$@"
# Writes /logs/agent/trajectory.json so trajectory verifiers see oracle's replay.
SOLUTION_DIR="$WORK/solution" python3 "$WORK/solution/emit_oracle_trajectory.py"

# Stage the ORACLE's own deliverables into /workspace. The golden trajectory is
# gym tool calls only, so nothing in the replay puts a file on disk, and
# file_check grades files under /workspace.
SOLUTION_DIR="$WORK/solution" WORKSPACE="${TH_WORKSPACE_DIR:-/workspace}" \
    python3 "$WORK/solution/write_artifacts.py"
