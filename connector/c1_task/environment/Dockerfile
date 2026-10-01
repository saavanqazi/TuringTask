FROM us-central1-docker.pkg.dev/delivery-g-obi/connectors-rl-gym/connectors-harness@sha256:b1374cd8a392ea66f9a649e700a1498e8fcb03ee35776362db7cc15dc3049b89

# E2B portability rule 4 (TASK_GEN section 1): without an explicit USER root E2B
# forces uid 1000 and entrypoint's mkdir /logs/agent fails. Inert under Docker/Modal.
USER root

# Own venv so these pins can't shift a version out from under the gym servers,
# which run on this image's system python3.
RUN python3 -m venv /opt/proxy-venv && \
    /opt/proxy-venv/bin/pip install --no-cache-dir \
        pytest \
        mcp==1.26.0 \
        httpx==0.28.1 \
        "uvicorn[standard]==0.41.0" \
        starlette==0.52.1 \
        litellm==1.82.0

WORKDIR /app

# Build context is environment/ (some remote builders upload only that), so
# these come from the _app/ mirror — keep in sync via sync_app_mirror.sh.
COPY _app/task.toml _app/instruction.md /app/
COPY _app/tests/ /app/tests/

COPY mcp/proxy/ /opt/proxy/

# Build-time seed (Handbook 8.1): fourteen inbox messages for the acting user, the moves of two
# of his meetings, answer times on his five meetings and one cancelled meeting, written into
# the outlook gym's synthetic snapshot that every /reset copies. The script asserts the
# snapshot it patches and fails the build on drift or collision; its directory is removed
# afterwards.
COPY seed/ /tmp/task-seed/
RUN set -eu; \
    python3 /tmp/task-seed/seed_outlook_task.py /gyms/outlook/app/data/Synthetic_db.db; \
    rm -rf /tmp/task-seed
# E2B portability rule 2: E2B boots under systemd, which starts supervisor.service
# with an EMPTY environment, so GYM_DATASET never reaches the gyms. Must precede the
# entrypoint COPY. Inert under Docker/Modal, where the unit file is not present.
RUN rm -f /etc/systemd/system/multi-user.target.wants/supervisor.service

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# The lifecycle manager is root.  Connector processes, the proxy, and the
# model agent have separate identities so Unix permissions remain meaningful
# even though this is a single container.
RUN id rlgymagent >/dev/null 2>&1 || useradd --create-home --shell /bin/bash rlgymagent; \
    id gym >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin gym; \
    id harborproxy >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin harborproxy; \
    sed -i \
        -e 's/^user=root$/user=gym/' \
        -e 's#^logfile=/app/logs/#logfile=/run/harbor/services/#' \
        -e 's#^pidfile=/var/run/#pidfile=/run/harbor/services/#' \
        -e 's#^childlogdir=/app/logs$#childlogdir=/run/harbor/services#' \
        -e 's#^file=/var/run/#file=/run/harbor/services/#' \
        -e 's#^serverurl=unix:///var/run/#serverurl=unix:///run/harbor/services/#' \
        -e 's#=/app/logs/#=/run/harbor/services/#' \
        /etc/supervisor/conf.d/supervisord.conf; \
    command -v pkill >/dev/null 2>&1 && command -v pgrep >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends procps && rm -rf /var/lib/apt/lists/*); \
    chmod -R go-rwx /app; \
    if [ -d /gyms ]; then chmod 700 /gyms; fi; \
    mkdir -p /workspace && chown rlgymagent:rlgymagent /workspace

# /opt/proxy (the proxy source) was world-readable, so the agent user could read
# server.py. Only root and the harborproxy user that runs it need it.
RUN set -eu; \
    chown -R root:harborproxy /opt/proxy; \
    chmod 750 /opt/proxy; \
    find /opt/proxy -type f -exec chmod 640 {} +; \
    test "$(stat -c '%U:%G:%a' /opt/proxy)" = "root:harborproxy:750"

# E2B portability rule 3: one ENV k=v per line. E2B's parser keeps the continuation
# whitespace inside the value, so a folded block launches a python that does not exist.
ENV TASK_DIR=/app
ENV HARBOR_MCP_MODE=docker
ENV PROXY_HOST=127.0.0.1
ENV PROXY_PORT=7000
ENV HARBOR_RUN_DIR=/run/harbor
ENV TRUSTED_PROXY_SOCKET=/run/harbor/proxy/trusted-proxy.sock
ENV SNAPSHOT_DIR=/run/harbor/proxy/snapshots
ENV TRUSTED_TOOL_TRACE_FILE=/run/harbor/proxy/proxy-tool-calls.jsonl
ENV HARBOR_CONNECTOR_CONTROL_CAPABILITY_FILE=/run/harbor/proxy/connector-control-capability
ENV HARBOR_PROXY_VERIFIER_CAPABILITY_FILE=/run/harbor/proxy-verifier-capability
ENV PROXY_PYTHON=/opt/proxy-venv/bin/python3
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# The batch-2 image ships /etc/supervisor/conf.d/supervisord.conf as 0640 root:root
# (it was 0644 on the batch-1 image). entrypoint.sh runs supervisord as the
# unprivileged `gym` user, which then cannot read its own config: supervisord dies
# with "could not read config file", NO gym starts, and the failure surfaces as
# "Harbor MCP proxy stopped during startup" / "health unavailable after 60 attempts"
# - which reads as a proxy fault and is not one. Make it group-readable by gym.
RUN chown root:gym /etc/supervisor/conf.d/supervisord.conf \
 && chmod 0640 /etc/supervisor/conf.d/supervisord.conf
# Do NOT add `USER gym` here. entrypoint.sh:7 refuses to start unless uid 0
# ("Harbor connector entrypoint must start as root", exit 70), and dropping the
# user also breaks E2B portability rule 4. The image already ends as root.

WORKDIR /workspace

# E2B portability rule 5: E2B does not concatenate CMD and ENTRYPOINT, it takes the
# last one. Docker appends CMD to ENTRYPOINT whatever the order, so this is inert here.
CMD ["sleep", "infinity"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
