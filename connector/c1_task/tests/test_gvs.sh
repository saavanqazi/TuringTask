#!/bin/sh
# Harbor task — verifier entrypoint. Calls the frozen Python verifier.
set -eu

# Answer-key decryption (verifier phase only). For a live agent run the grading
# key (manifest.json / expected_diff.json / rubric.toml) was encrypted to *.enc
# at dispatch so the AGENT could not read the answer off disk. We are now PAST
# the agent and have HARBOR_ANSWER_KEY (injected via task.toml [verifier.env],
# which harbor does not expose to the agent), so restore plaintext here before
# the verifier runs. No-op for plaintext tasks (script absent / no *.enc). The
# `set -e` above intentionally aborts verification if decryption is required but
# fails, rather than scoring against a missing/garbled key.
if [ -f "${TASK_DIR:-/app}/tests/decrypt_answer_key.py" ]; then
  python "${TASK_DIR:-/app}/tests/decrypt_answer_key.py"
fi

exec python /app/tests/test_outputs.py
