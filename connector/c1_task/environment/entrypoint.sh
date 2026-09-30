#!/bin/sh
set -eu

# This is the root lifecycle manager. It is the only process that may create
# per-run credentials or start trusted services. The command supplied by
# Harbor always runs as rlgymagent.
if [ "$(id -u)" -ne 0 ]; then
    echo "Harbor connector entrypoint must start as root" >&2
    exit 70
fi
if ! command -v runuser >/dev/null 2>&1; then
    echo "Harbor connector image is missing runuser" >&2
    exit 70
fi
for user in gym harborproxy rlgymagent; do
    if ! id "${user}" >/dev/null 2>&1; then
        echo "Harbor connector image is missing required user: ${user}" >&2
        exit 70
    fi
done
if ! command -v pkill >/dev/null 2>&1 || ! command -v pgrep >/dev/null 2>&1; then
    echo "Harbor connector image is missing required agent cleanup tools" >&2
    exit 70
fi

RUN_DIR="${HARBOR_RUN_DIR:-/run/harbor}"
PROXY_DIR="${RUN_DIR}/proxy"
TASK_SOURCE_DIR="${TASK_DIR:-/app}"
PROXY_TASK_DIR="${HARBOR_PROXY_TASK_DIR:-${PROXY_DIR}/task-input}"
SERVICES_DIR="${RUN_DIR}/services"
PROXY_PYTHON="${PROXY_PYTHON:-python3}"
CONTROL_CAPABILITY_FILE="${HARBOR_CONNECTOR_CONTROL_CAPABILITY_FILE:-${PROXY_DIR}/connector-control-capability}"
PROXY_VERIFIER_CAPABILITY_FILE="${HARBOR_PROXY_VERIFIER_CAPABILITY_FILE:-${RUN_DIR}/proxy-verifier-capability}"
TRUSTED_PROXY_SOCKET="${TRUSTED_PROXY_SOCKET:-${PROXY_DIR}/trusted-proxy.sock}"
PROXY_LOG_FILE="${PROXY_LOG_FILE:-${PROXY_DIR}/harbor-mcp-proxy.log}"
SERVICES_LOG_FILE="${SERVICES_LOG_FILE:-${SERVICES_DIR}/supervisord.log}"
ENV_DUMP_FILE="${ENV_DUMP_FILE:-${RUN_DIR}/entrypoint-env.log}"

# The agent receives a writable workspace and its own logs. Do not store
# credentials, snapshots, proxy logs, or connector state below /logs because
# Harbor may expose that tree to the agent after the run.  Lock the *parent*
# first: ownership of a child alone does not prevent its rename/replacement
# when a mounted parent is writable by the agent UID.
prepare_log_root() {
    if [ -L /logs ] || { [ -e /logs ] && [ ! -d /logs ]; }; then
        echo "log root is unsafe" >&2
        return 70
    fi
    mkdir -p /logs
    chown root:root /logs
    chmod 755 /logs
    log_mode="$(stat -c '%u:%g:%a' /logs)"
    [ "${log_mode}" = "0:0:755" ] || {
        echo "log root has unsafe ownership or mode" >&2
        return 70
    }
}
prepare_log_root || exit $?
mkdir -p /logs/agent
chown rlgymagent:rlgymagent /logs/agent
chmod 700 /logs/agent
# Reserve verifier artifacts before the agent exists. A writable /logs mount
# must not let an agent pre-create this directory (or a symlink) and redirect
# root's later reward/evidence writes.
prepare_verifier_log_dir() {
    if [ -L /logs/verifier ] || { [ -e /logs/verifier ] && [ ! -d /logs/verifier ]; }; then
        echo "verifier artifact path is unsafe" >&2
        return 70
    fi
    mkdir -p /logs/verifier
    chown root:root /logs/verifier
    chmod 700 /logs/verifier
    verifier_mode="$(stat -c '%u:%g:%a' /logs/verifier)"
    [ "${verifier_mode}" = "0:0:700" ] || {
        echo "verifier artifact directory has unsafe ownership or mode" >&2
        return 70
    }
}
prepare_verifier_log_dir || exit $?
mkdir -p "${RUN_DIR}"
chown root:root "${RUN_DIR}"
chmod 711 "${RUN_DIR}"
mkdir -p "${PROXY_DIR}" "${SERVICES_DIR}"
chown root:harborproxy "${PROXY_DIR}"
chmod 730 "${PROXY_DIR}"
chown gym:gym "${SERVICES_DIR}"
chmod 700 "${SERVICES_DIR}"

# The proxy must read connector metadata, the compliance policy, and any
# declared reset seed before it can serve MCP. It must not read the whole task
# package: that includes verifier/answer-key material which is intentionally
# root-only. Build a narrow, root-created input mirror for harborproxy instead.
prepare_proxy_task_inputs() {
    [ "${PROXY_TASK_DIR}" = "${PROXY_DIR}/task-input" ] || {
        echo "proxy task input directory must remain under the protected proxy directory" >&2
        return 70
    }
    [ -f "${TASK_SOURCE_DIR}/task.toml" ] || {
        echo "task.toml is unavailable for the Harbor proxy" >&2
        return 70
    }
    rm -rf "${PROXY_TASK_DIR}"
    mkdir -p "${PROXY_TASK_DIR}/tests"
    chown root:harborproxy "${PROXY_TASK_DIR}" "${PROXY_TASK_DIR}/tests"
    chmod 750 "${PROXY_TASK_DIR}" "${PROXY_TASK_DIR}/tests"
    install -o root -g harborproxy -m 640 "${TASK_SOURCE_DIR}/task.toml" "${PROXY_TASK_DIR}/task.toml"
    if [ -f "${TASK_SOURCE_DIR}/tests/manifest.json" ]; then
        install -o root -g harborproxy -m 640 \
            "${TASK_SOURCE_DIR}/tests/manifest.json" "${PROXY_TASK_DIR}/tests/manifest.json"
    fi
    "${PROXY_PYTHON}" - "${TASK_SOURCE_DIR}" "${PROXY_TASK_DIR}" <<'PY'
import os
import grp
import shutil
import sys
import tomllib
from pathlib import Path

source = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
document = tomllib.loads((source / "task.toml").read_text(encoding="utf-8"))
metadata = document.get("metadata") or {}
entries = list(metadata.get("mcp_servers_extended") or [])
entries.extend(metadata.get("cli_servers_extended") or [])
for entry in entries:
    if not isinstance(entry, dict) or not entry.get("seed_file"):
        continue
    relative = Path(str(entry["seed_file"]))
    if relative.is_absolute():
        raise SystemExit("proxy seed path must be task-relative")
    seed = (source / relative).resolve()
    destination = (target / relative).resolve()
    if source not in seed.parents or target not in destination.parents:
        raise SystemExit("proxy seed path escapes the task input mirror")
    if not seed.is_file():
        raise SystemExit(f"declared proxy seed is missing: {relative}")
    # `mkdir(parents=True)` would leave intermediate directories at the root
    # process umask. Make every declared nested component traversable by the
    # proxy, while rejecting an unexpected symlink at any boundary.
    parent = target
    for component in relative.parent.parts:
        parent = parent / component
        parent.mkdir(exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise SystemExit("proxy seed mirror contains an unsafe directory")
        os.chown(parent, 0, grp.getgrnam("harborproxy").gr_gid)
        os.chmod(parent, 0o750)
    shutil.copyfile(seed, destination)
    os.chown(destination, 0, grp.getgrnam("harborproxy").gr_gid)
    os.chmod(destination, 0o640)
PY
}
prepare_proxy_task_inputs || exit $?

# Connector processes own mutable state. The agent cannot traverse /gyms and
# cannot join the gym group, while the root verifier can still inspect it.
lock_mcp_connector_state() {
    if [ -d /gyms ]; then
        chown root:gym /gyms
        chmod 710 /gyms
    fi
    for state_dir in /gyms/*/mcp_databases /gyms/*/app/data; do
        [ -d "${state_dir}" ] || continue
        chown -R gym:gym "${state_dir}"
        chmod -R go-rwx "${state_dir}"
    done
}

lock_mcp_connector_state

# Connector control calls need a capability even after socket ownership has
# separated the proxy from the agent. The connector supervisor inherits it;
# the proxy reads its root-owned file and no agent process receives either.
export GYM_CLIENT_MODE=1
export HARBOR_CONNECTOR_CONTROL_CAPABILITY="$(
    "${PROXY_PYTHON}" -c 'import secrets; print(secrets.token_urlsafe(32))'
)"
if [ -z "${HARBOR_CONNECTOR_CONTROL_CAPABILITY}" ]; then
    echo "failed to create Harbor connector control capability" >&2
    exit 70
fi
umask 077
printf '%s' "${HARBOR_CONNECTOR_CONTROL_CAPABILITY}" > "${CONTROL_CAPABILITY_FILE}"
chown root:harborproxy "${CONTROL_CAPABILITY_FILE}"
chmod 040 "${CONTROL_CAPABILITY_FILE}"

# Trusted raw operations have two checks: this root-only file and a Unix
# socket whose mode is set after the proxy binds it.
PROXY_VERIFIER_CAPABILITY="$(
    "${PROXY_PYTHON}" -c 'import secrets; print(secrets.token_urlsafe(32))'
)"
if [ -z "${PROXY_VERIFIER_CAPABILITY}" ]; then
    echo "failed to create Harbor verifier capability" >&2
    exit 70
fi
printf '%s' "${PROXY_VERIFIER_CAPABILITY}" > "${PROXY_VERIFIER_CAPABILITY_FILE}"
chown root:harborproxy "${PROXY_VERIFIER_CAPABILITY_FILE}"
chmod 040 "${PROXY_VERIFIER_CAPABILITY_FILE}"
rm -f "${TRUSTED_PROXY_SOCKET}"
mkdir -p "${PROXY_DIR}/snapshots"
chown harborproxy:harborproxy "${PROXY_DIR}/snapshots"
chmod 700 "${PROXY_DIR}/snapshots"
: > "${PROXY_DIR}/proxy-tool-calls.jsonl"
chown harborproxy:harborproxy "${PROXY_DIR}/proxy-tool-calls.jsonl"
chmod 600 "${PROXY_DIR}/proxy-tool-calls.jsonl"
: > "${PROXY_LOG_FILE}"
chown harborproxy:harborproxy "${PROXY_LOG_FILE}"
chmod 600 "${PROXY_LOG_FILE}"
: > "${SERVICES_LOG_FILE}"
chown gym:gym "${SERVICES_LOG_FILE}"
chmod 600 "${SERVICES_LOG_FILE}"

# Keep a minimal, root-only diagnostic. URLs, connector details, and the
# complete environment are not useful to an agent and must not enter its logs.
{
    echo "=== entrypoint ==="
    echo "agent_user=rlgymagent"
    echo "connector_user=gym"
    echo "proxy_user=harborproxy"
} > "${ENV_DUMP_FILE}"
chown root:root "${ENV_DUMP_FILE}"
chmod 600 "${ENV_DUMP_FILE}"

runuser -u gym --preserve-environment -- /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf \
    >>"${SERVICES_LOG_FILE}" 2>&1 &
SUPERVISORD_PID=$!

# Do not pass capabilities as command arguments or proxy environment values.
# The supervisor has already inherited its control capability. The proxy reads
# both protected files after this unset.
unset HARBOR_CONNECTOR_CONTROL_CAPABILITY
unset PROXY_VERIFIER_CAPABILITY
runuser -u harborproxy --preserve-environment -- \
    env TASK_DIR="${PROXY_TASK_DIR}" "${PROXY_PYTHON}" /opt/proxy/server.py >>"${PROXY_LOG_FILE}" 2>&1 &
PROXY_PID=$!

# Do not hand the container to the agent until both listeners are live. The
# public readiness probe reveals no connector names or control-plane details.
# The wait is 240 one-second attempts, not 40: under the task's own limits
# (cpus = 2, memory_mb = 4096) all twelve gyms boot at once and the proxy is
# not ready within 40 s, so the entrypoint exited 70 and harbor reported a
# HealthcheckError before the agent started. 240 s covers the proxy's own
# upstream wait (60 attempts, 2 s apart); a proxy that dies is still caught by
# the kill -0 check below, so a broken start fails as fast as before.
PROXY_READY=0
PROXY_ATTEMPT=0
while [ "${PROXY_ATTEMPT}" -lt 240 ]; do
    if [ -S "${TRUSTED_PROXY_SOCKET}" ] \
        && curl -fsS http://127.0.0.1:7000/health >/dev/null 2>&1; then
        PROXY_READY=1
        break
    fi
    if ! kill -0 "${PROXY_PID}" 2>/dev/null; then
        echo "Harbor MCP proxy stopped during startup" >&2
        kill -TERM "${SUPERVISORD_PID}" 2>/dev/null || true
        wait "${SUPERVISORD_PID}" 2>/dev/null || true
        rm -f "${CONTROL_CAPABILITY_FILE}" "${PROXY_VERIFIER_CAPABILITY_FILE}" "${TRUSTED_PROXY_SOCKET}"
        exit 70
    fi
    PROXY_ATTEMPT=$((PROXY_ATTEMPT + 1))
    sleep 1
done
if [ "${PROXY_READY}" -ne 1 ]; then
    echo "Harbor MCP proxy did not become ready" >&2
    kill -TERM "${PROXY_PID}" "${SUPERVISORD_PID}" 2>/dev/null || true
    wait "${PROXY_PID}" 2>/dev/null || true
    wait "${SUPERVISORD_PID}" 2>/dev/null || true
    rm -f "${CONTROL_CAPABILITY_FILE}" "${PROXY_VERIFIER_CAPABILITY_FILE}" "${TRUSTED_PROXY_SOCKET}"
    exit 70
fi

stop_agent_processes() {
    # A completed agent may have detached children. Stop every process for the
    # untrusted UID before control returns to Harbor for verification.
    pkill -TERM -u rlgymagent 2>/dev/null || true
    cleanup_attempt=0
    while pgrep -u rlgymagent >/dev/null 2>&1 && [ "${cleanup_attempt}" -lt 2 ]; do
        sleep 1
        cleanup_attempt=$((cleanup_attempt + 1))
    done
    pkill -KILL -u rlgymagent 2>/dev/null || true
    cleanup_attempt=0
    while pgrep -u rlgymagent >/dev/null 2>&1 && [ "${cleanup_attempt}" -lt 2 ]; do
        sleep 1
        cleanup_attempt=$((cleanup_attempt + 1))
    done
    if pgrep -u rlgymagent >/dev/null 2>&1; then
        echo "failed to terminate all rlgymagent descendants" >&2
        return 70
    fi
}

cleanup() {
    stop_agent_processes || return $?
    kill -TERM "${PROXY_PID}" 2>/dev/null || true
    kill -TERM "${SUPERVISORD_PID}" 2>/dev/null || true
    wait "${PROXY_PID}" 2>/dev/null || true
    wait "${SUPERVISORD_PID}" 2>/dev/null || true
    rm -f "${CONTROL_CAPABILITY_FILE}" "${PROXY_VERIFIER_CAPABILITY_FILE}" "${TRUSTED_PROXY_SOCKET}"
}
trap 'cleanup; exit 143' TERM INT

# Harbor's Docker environment attaches the agent with ``docker exec -u
# rlgymagent``. Keep its default container command root-owned, so verifier
# cleanup can terminate every rlgymagent descendant without also terminating
# the lifecycle manager and its trusted proxy.
if [ "$#" -eq 0 ]; then
    set -- sleep infinity
fi
if [ "$#" -eq 2 ] && [ "$1" = "sleep" ] && [ "$2" = "infinity" ]; then
    while :; do
        sleep 2147483647 &
        wait "$!" || true
    done
fi

# This fallback is only used when the container command itself is the agent.
# Docker-exec agents have their own task environment. Never inherit root's
# environment here because it may include broker/provider credentials.
runuser -u rlgymagent -- env -i \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/rlgymagent \
    USER=rlgymagent \
    LOGNAME=rlgymagent \
    TASK_DIR=/app \
    "$@" &
AGENT_PID=$!
if wait "${AGENT_PID}"; then
    AGENT_STATUS=0
else
    AGENT_STATUS=$?
fi
cleanup
trap - TERM INT
exit "${AGENT_STATUS}"
