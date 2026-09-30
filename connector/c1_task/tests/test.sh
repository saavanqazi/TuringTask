#!/bin/sh
# Harbor task — verifier entrypoint. NOT frozen; tests/test_gvs.sh is, and this
# runs it unchanged. All scoring still happens in the frozen verifier.
#
# Afterwards this reconciles the reward file with what stock Harbor can read.
# Harbor takes /logs/verifier/reward.json whenever it exists and requires
# dict[str, float | int]. The frozen verifier writes a 21-key diagnostic
# payload there — lists, nested dicts, a null — so VerifierResult fails
# validation with 16 type errors and a fully graded run is recorded as an
# exception with Mean 0.000. Gym-verification-service's own runner reads
# reward.txt first and so never sees this; stock Harbor does.
#
# This is not caused by the conversion: an unconverted GVS bundle fails stock
# Harbor the same way. See NEEDED-FROM-AUTHORS.md, which carries the
# reproduction and asks for the upstream fix.
#
# Nothing is lost by rewriting it — the frozen verifier writes that same
# payload to verifier_summary.json under "reward", which this leaves alone.
set -eu

HERE=$(dirname "$0")

status=0
sh "$HERE/test_gvs.sh" || status=$?

python - <<'PY' || echo "warning: could not reconcile reward.json for Harbor" >&2
import json
from pathlib import Path

log = Path("/logs/verifier")
reward_json = log / "reward.json"
reward_txt = log / "reward.txt"

if reward_json.exists():
    payload = json.loads(reward_json.read_text())
    # A no-op once every value is a number, so if upstream starts emitting a
    # Harbor-readable reward.json this stops touching it.
    if any(not isinstance(value, (int, float)) for value in payload.values()):
        total = (
            float(reward_txt.read_text())
            if reward_txt.exists()
            else float(payload["total"])
        )
        # {"reward": <total>} is exactly what Harbor derives from reward.txt,
        # and the shape gym-verification-service's own runs record.
        reward_json.write_text(json.dumps({"reward": total}) + "\n")
PY

exit "$status"
