# ATTRIBUTION: lifted from rl-harbor-platform/harbor-task-template/environment/mcp/proxy/server.py
# (FROZEN — do not edit; mirror upstream).
#
# HARBOR-LOCAL DIVERGENCES (intentional, narrow):
#   * Tool allowlist enforcement. Each ``mcp_servers_extended`` entry may
#     carry an ``allowed_tools`` list (configured via the Tool Config tab
#     on a HarborBatch). When present, ``list_tools()`` returns only the
#     named tools and ``call_tool()`` raises before issuing the upstream
#     /step ToolCallAction for anything outside the allowlist.
#   * Explicit default-seed requests for reset_on_run entries without custom
#     SQL, plus semantic reset validation. Legacy gyms may ignore the standard
#     seed header and can report a failed reset inside HTTP 200.
# Look for `# HARBOR-LOCAL` and `# HARBOR-DEFAULT-SEED` markers below. Every
# divergence is at most a handful of lines, so re-syncing stays mechanical.
"""
Harbor task template — MCP proxy (FROZEN).

Presents a native MCP (streamable-http) interface to the agent, and translates
every call into the upstream OpenEnv HTTP API (POST /step, POST /reset).

Responsibilities:
  * Read task.toml at startup from $TASK_DIR (default: /app).
  * For every [[metadata.mcp_servers_extended]] entry:
      - Pick upstream URL based on $HARBOR_MCP_MODE (docker | daytona).
      - Generate a unique x-database-id per trial.
      - Read the configured seed .sql and POST /reset with sql_content, or
        request the gym's built-in default seed when none is set.
      - Require the response metadata to confirm the database reset succeeded.
      - Fetch the tool catalog via POST /step {action_type: ListToolsAction}.
  * Serve native MCP at /mcp/<server_name>.
  * Inject the configured auth header when present, plus x-database-id on every upstream call.

Fail-loud policy: any missing/invalid config or failed /reset exits non-zero,
which makes Harbor's healthcheck fail and the trial abort cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import socket
import stat
import sys
import threading
import time
import tomllib
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

logger = logging.getLogger("harbor-mcp-proxy")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

TASK_DIR = Path(os.environ.get("TASK_DIR", "/app"))
MODE = os.environ.get("HARBOR_MCP_MODE", "docker").lower()
PROXY_HOST = os.environ.get("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "7000"))
HTTP_TIMEOUT = float(os.environ.get("PROXY_HTTP_TIMEOUT", "180.0"))
HARBOR_RUN_DIR = Path(os.environ.get("HARBOR_RUN_DIR", "/run/harbor"))
TRUSTED_PROXY_SOCKET = Path(
    os.environ.get(
        "TRUSTED_PROXY_SOCKET", str(HARBOR_RUN_DIR / "proxy" / "trusted-proxy.sock")
    )
)
SNAPSHOT_DIR = Path(
    os.environ.get("SNAPSHOT_DIR", str(HARBOR_RUN_DIR / "proxy" / "snapshots"))
)
SNAPSHOT_EXCLUDE = {"sqlite_sequence", "sqlite_stat1"}
CONTROL_CAPABILITY_ENV = "HARBOR_CONNECTOR_CONTROL_CAPABILITY"
CONTROL_CAPABILITY_HEADER = "x-connector-internal-capability"
CONTROL_CAPABILITY_FILE = Path(
    os.environ.get(
        "HARBOR_CONNECTOR_CONTROL_CAPABILITY_FILE",
        str(HARBOR_RUN_DIR / "proxy" / "connector-control-capability"),
    )
)
VERIFIER_CAPABILITY_ENV = "HARBOR_PROXY_VERIFIER_CAPABILITY"
VERIFIER_CAPABILITY_FILE = Path(
    os.environ.get(
        "HARBOR_PROXY_VERIFIER_CAPABILITY_FILE",
        str(HARBOR_RUN_DIR / "proxy-verifier-capability"),
    )
)
VERIFIER_CAPABILITY_HEADER = "x-harbor-proxy-verifier-capability"
TRUSTED_TOOL_TRACE_FILE = Path(
    os.environ.get(
        "TRUSTED_TOOL_TRACE_FILE", str(HARBOR_RUN_DIR / "proxy" / "proxy-tool-calls.jsonl")
    )
)
TRACE_REQUIRED_FIELDS = frozenset({
    "schema", "event_id", "sequence", "server", "tool_name", "arguments", "accepted", "started_at_ns",
    "finished_at_ns", "latency_ms", "result_sha256", "isError",
})
TRACE_ATTEMPT_SCHEMA = "harbor.proxy_tool_attempt.v1"
TRACE_SEAL_SCHEMA = "harbor.proxy_tool_trace_seal.v1"
TRACE_ATTEMPT_REQUIRED_FIELDS = frozenset({
    "schema", "event_id", "sequence", "server", "tool_name", "arguments", "started_at_ns",
})
MAX_CLI_STDIN_BYTES = 1 << 20
TRACE_SEQUENCE = 0
TRACE_WRITE_LOCK = threading.RLock()
TRACE_RECORD_DIGEST = hashlib.sha256()
TRACE_RECORD_COUNT = 0
TRACE_OPEN_EVENT_IDS: set[str] = set()
TRACE_WRITE_FAILED = False
TRACE_SEALED = False
TRACE_SEAL: dict[str, Any] | None = None
CAPABILITY_OWNER_UID = 0

# CLI-shaped connectors use a bounded proxy command route. Their command string
# stays free-form within the connector's own grammar, but only an allowlisted
# binary can reach the connector's private /exec endpoint.
CLI_BRIDGE_DESCRIPTIONS = {
    "gws": (
        "Google Workspace command runner. Pass the complete command, including "
        "the gws prefix. Example: `gws drive files list --params "
        "'{\\\"pageSize\\\":5}'`. Use gws_discovery to list supported commands."
    ),
    "gh": (
        "GitHub command runner. Pass the complete command, including the gh "
        "prefix. Example: `gh pr list -R owner/repo --json number,title`."
    ),
    "supabase": (
        "Supabase command runner. Pass the complete command, including the "
        "supabase prefix. Example: `supabase projects list`."
    ),
}
CLI_BRIDGE_TOOL_NAMES = {
    "gws": ("gws", "gws_discovery"),
    "gh": ("gh",),
}

STATE: dict[str, dict[str, Any]] = {}
CLI_STATE: dict[str, dict[str, Any]] = {}
FORBIDDEN_TOOLS: frozenset[str] = frozenset()
READY: bool = False


class SafeToolInputError(RuntimeError):
    """A reviewed input error that can be returned to the untrusted agent."""


def _response_validation_error(response: httpx.Response) -> SafeToolInputError:
    """Convert a structured schema error into fixed, non-backend feedback.

    The connector is not trusted to compose agent-visible error text.  We use
    only a strict Pydantic-like ``loc`` plus a known machine type, never its
    free-form ``msg``/``detail`` value; those strings can contain database IDs,
    paths, or provider text.
    """
    try:
        body = response.json()
    except (TypeError, ValueError):
        return SafeToolInputError("invalid tool input")
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, list) or not detail:
        return SafeToolInputError("invalid tool input")
    item = detail[0]
    if not isinstance(item, dict):
        return SafeToolInputError("invalid tool input")
    location = item.get("loc")
    field = location[-1] if isinstance(location, list) and location else None
    if not isinstance(field, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", field):
        return SafeToolInputError("invalid tool input")
    kind = str(item.get("type") or "")
    if kind == "missing":
        return SafeToolInputError(f"missing required field {field}")
    if kind in {"string_type", "string_unicode"}:
        return SafeToolInputError(f"field {field} must be a string")
    if kind in {"int_type", "int_parsing"}:
        return SafeToolInputError(f"field {field} must be an integer")
    if kind in {"float_type", "float_parsing"}:
        return SafeToolInputError(f"field {field} must be a number")
    if kind in {"bool_type", "bool_parsing"}:
        return SafeToolInputError(f"field {field} must be a boolean")
    if kind in {"extra_forbidden", "enum", "literal_error"}:
        return SafeToolInputError(f"invalid value for field {field}")
    return SafeToolInputError("invalid tool input")


def _safe_tool_error(exc: Exception) -> str:
    """Keep useful local validation errors without leaking upstream internals."""
    if isinstance(exc, SafeToolInputError):
        return str(exc)
    return "connector tool call failed"


def _mcp_tool_result(
    text: str, event_id: str, *, is_error: bool = False
) -> types.CallToolResult:
    """Attach the opaque trusted event identity outside the visible payload."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=is_error,
        _meta={"harbor_proxy_event_id": event_id},
    )


def _read_protected_capability(path: Path, label: str) -> str:
    """Read a root-owned capability file without accepting a public secret."""
    try:
        info = path.stat()
        if (
            info.st_uid != CAPABILITY_OWNER_UID
            or not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o007
        ):
            raise RuntimeError("file ownership or mode is unsafe")
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"{label} is unavailable") from exc
    if not value:
        raise RuntimeError(f"{label} is empty")
    return value


def _control_capability() -> str:
    return _read_protected_capability(CONTROL_CAPABILITY_FILE, "connector control capability")


def _verifier_capability() -> str:
    return _read_protected_capability(VERIFIER_CAPABILITY_FILE, "verifier capability")


def _has_control_capability(request: Request) -> bool:
    """Authenticate verifier/oracle-only proxy routes in Harbor mode."""
    try:
        expected = _control_capability()
    except RuntimeError:
        return False
    supplied = request.headers.get(CONTROL_CAPABILITY_HEADER, "")
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def require_docker_control_capability() -> None:
    """Refuse a Docker-mode proxy that would silently expose direct gym routes.

    The task entrypoint mints this capability before it starts the connector
    supervisor and proxy, then removes it from the agent environment. Without
    it, a connector in the shared network namespace cannot distinguish Harbor's
    proxy from an agent curling a direct connector port.
    """
    if MODE == "docker":
        try:
            _control_capability()
        except RuntimeError as exc:
            die(f"protected connector control capability is required in docker mode: {exc}")


def _new_trace_identity() -> str:
    """Return an opaque call identity before the upstream request starts.

    Sequence numbers describe append order, not admission order. Parallel calls
    can complete in either order, so assigning a sequence here would create a
    physically reordered trace that the verifier must reject.
    """
    return secrets.token_urlsafe(18)


def _append_trace_record(record: dict[str, Any], *, include_in_digest: bool = True) -> None:
    """Append one canonical trace record while holding the evidence lock."""
    global TRACE_SEQUENCE, TRACE_RECORD_COUNT, TRACE_WRITE_FAILED
    # This function has no await point, but it can still be reached from a
    # threaded ASGI worker. Guard both sequence allocation and the write so the
    # on-disk order is the canonical monotonic order the verifier checks.
    with TRACE_WRITE_LOCK:
        if TRACE_WRITE_FAILED:
            raise RuntimeError("trusted proxy trace is unavailable after a write failure")
        if TRACE_SEALED:
            raise RuntimeError("trusted proxy trace is already sealed")
        expected_sequence = TRACE_SEQUENCE + 1
        supplied_sequence = record.get("sequence")
        if supplied_sequence is None:
            record["sequence"] = expected_sequence
        elif supplied_sequence != expected_sequence:
            raise ValueError(
                "refusing proxy trace event with non-contiguous append sequence"
            )
        if not isinstance(record["sequence"], int) or record["sequence"] < 1:
            raise ValueError("refusing proxy trace event without a positive sequence")
        line = json.dumps(record, separators=(",", ":"), default=str).encode("utf-8") + b"\n"
        try:
            TRUSTED_TOOL_TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with TRUSTED_TOOL_TRACE_FILE.open("ab") as fh:
                os.chmod(TRUSTED_TOOL_TRACE_FILE, 0o600)
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            # A failed append can leave an unknown partial record.  Never
            # continue dispatching or allow an empty/partial trace to be
            # sealed as a legitimate no-tool run.
            TRACE_WRITE_FAILED = True
            raise RuntimeError("trusted proxy trace write failed") from exc
        TRACE_SEQUENCE = expected_sequence
        TRACE_RECORD_COUNT += 1
        if include_in_digest:
            TRACE_RECORD_DIGEST.update(line)


def _begin_trusted_tool_event(event: dict[str, Any]) -> None:
    """Persist an accepted or denied call *before* connector dispatch.

    A completed-call-only log cannot distinguish "the agent made no call" from
    "a state-changing upstream call completed and the proxy died before writing
    evidence".  The start record makes that ambiguity a verifier infrastructure
    failure when the root verifier later seals the trace.
    """
    required = {"event_id", "server", "tool_name", "arguments", "started_at_ns"}
    missing = required.difference(event)
    if missing:
        raise ValueError(
            "refusing incomplete proxy trace attempt; missing: "
            + ", ".join(sorted(missing))
        )
    if not isinstance(event["event_id"], str) or not event["event_id"]:
        raise ValueError("refusing proxy trace attempt without event_id")
    if not isinstance(event["server"], str) or not isinstance(event["tool_name"], str):
        raise ValueError("refusing proxy trace attempt without a tool identity")
    if not isinstance(event["arguments"], dict):
        raise ValueError("refusing proxy trace attempt without object arguments")
    with TRACE_WRITE_LOCK:
        if event["event_id"] in TRACE_OPEN_EVENT_IDS:
            raise ValueError("refusing duplicate proxy trace event id")
        attempt = {
            "schema": TRACE_ATTEMPT_SCHEMA,
            "event_id": event["event_id"],
            "server": event["server"],
            "tool_name": event["tool_name"],
            "arguments": event["arguments"],
            "started_at_ns": event["started_at_ns"],
        }
        if event.get("redacted_argument_keys"):
            attempt["redacted_argument_keys"] = event["redacted_argument_keys"]
        _append_trace_record(attempt)
        TRACE_OPEN_EVENT_IDS.add(event["event_id"])


def _append_trusted_tool_event(event: dict[str, Any]) -> None:
    """Append the terminal result for a previously persisted proxy attempt."""
    # Sequence is assigned by the append lock, never by the request handler.
    required = (TRACE_REQUIRED_FIELDS - {"sequence"}).difference(event)
    if required:
        raise ValueError(
            "refusing incomplete proxy trace event; missing: "
            + ", ".join(sorted(required))
        )
    if event.get("schema") != "harbor.proxy_tool_call.v1":
        raise ValueError("refusing proxy trace event with an unknown schema")
    if not isinstance(event["event_id"], str) or not event["event_id"]:
        raise ValueError("refusing proxy trace event without event_id")
    if not isinstance(event["arguments"], dict):
        raise ValueError("refusing proxy trace event without object arguments")
    with TRACE_WRITE_LOCK:
        if event["event_id"] not in TRACE_OPEN_EVENT_IDS:
            raise ValueError("refusing proxy trace result without a persisted attempt")
        _append_trace_record(event)
        TRACE_OPEN_EVENT_IDS.remove(event["event_id"])


def seal_trusted_tool_trace() -> dict[str, Any]:
    """Close the evidence channel after the untrusted agent has been stopped."""
    global TRACE_SEALED, TRACE_SEAL
    with TRACE_WRITE_LOCK:
        if TRACE_WRITE_FAILED:
            raise RuntimeError("trusted proxy trace is unavailable after a write failure")
        if TRACE_SEALED:
            # Stability may run the root verifier more than once against the
            # same retained environment. The sealed bytes remain immutable;
            # returning this cached seal is safe and avoids turning a valid
            # repeat grade into a proxy failure.
            if TRACE_SEAL is None:
                raise RuntimeError("trusted proxy trace seal state is unavailable")
            return dict(TRACE_SEAL)
        if TRACE_OPEN_EVENT_IDS:
            raise RuntimeError("trusted proxy trace has incomplete tool calls")
        seal = {
            "schema": TRACE_SEAL_SCHEMA,
            "record_count": TRACE_RECORD_COUNT,
            "records_sha256": TRACE_RECORD_DIGEST.hexdigest(),
        }
        _append_trace_record(seal, include_in_digest=False)
        TRACE_SEALED = True
        TRACE_SEAL = dict(seal)
        return dict(seal)


def die(msg: str) -> None:
    logger.error("FATAL: %s", msg)
    sys.exit(1)


def load_task_config() -> dict[str, Any]:
    path = TASK_DIR / "task.toml"
    if not path.exists():
        die(f"task.toml not found at {path} (set TASK_DIR to override)")
    return tomllib.loads(path.read_text())


def load_forbidden_tools() -> frozenset[str]:
    """Load task compliance policy from the root-only verifier manifest."""
    path = TASK_DIR / "tests" / "manifest.json"
    if not path.exists():
        return frozenset()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"invalid verifier manifest at {path}: {exc}")
    values = (manifest.get("trajectory") or {}).get("forbidden_tools") or []
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        die("tests/manifest.json trajectory.forbidden_tools must be a string list")
    return frozenset(value for value in values if value)


# OpenAI's chat/completions API hard-caps the ``tools`` array at 128 entries.
OPENAI_TOOL_LIMIT = 128


def _is_openai_family(model: str) -> bool:
    """True for OpenAI-routed model names (gpt-*/o1/o3/o4/openai-*). Mirrors the
    worker's ``_is_openai_model`` — DashScope's ``openai/qwen…`` normalization is
    NOT OpenAI, so it's excluded. Used only to decide whether the 128-tool cap
    applies; on anything else we never block."""
    if not model:
        return False
    m = model.lower()
    base = m.split("/", 1)[1] if "/" in m else m
    if base.startswith("qwen"):
        return False
    if m.startswith("openai/"):
        return True
    return base.startswith(("gpt-", "gpt3", "gpt4", "o1-", "o3-", "o4-")) or base in ("o1", "o3", "o4")


def _run_model_from_cfg(cfg: dict) -> str:
    """Resolve the agent's run model from a parsed task.toml.

    Prefers ``metadata.run_model`` (the actual agent model stamped at dispatch).
    Falls back to ``metadata.verifier_judge.model`` for task.toml files
    generated before run_model existed — those pre-date the configurable judge,
    when the judge model was derived from the run model, so the fallback keeps
    legacy behavior unchanged.
    """
    meta = cfg.get("metadata") or {}
    run_model = meta.get("run_model")
    if isinstance(run_model, str) and run_model.strip():
        return run_model
    return (meta.get("verifier_judge") or {}).get("model") or ""


def new_db_id() -> str:
    return f"db_{int(time.time() * 1000)}_{secrets.token_hex(4)}"


def upstream_for(entry: dict[str, Any]) -> str:
    name = entry["name"]
    if MODE == "docker":
        local_url = entry.get("local_url")
        if local_url:
            return str(local_url).rstrip("/")
        port = entry.get("container_port")
        if not port:
            die(f"server '{name}': container_port or local_url is required in docker mode")
        return f"http://127.0.0.1:{port}"
    if MODE == "daytona":
        var = entry.get("remote_url_env")
        if not var:
            die(f"server '{name}': remote_url_env missing in task.toml")
        url = os.environ.get(var)
        if not url:
            die(f"server '{name}': env var {var} is unset (daytona mode)")
        return url.rstrip("/")
    die(f"Unknown HARBOR_MCP_MODE: {MODE!r}")


async def wait_for_upstream(client: httpx.AsyncClient, name: str, upstream: str) -> None:
    """Wait for the configured gym rather than relying on fixed entrypoint ports."""
    last_error: Exception | None = None
    for attempt in range(60):
        try:
            response = await client.get(f"{upstream}/health", timeout=5.0)
            response.raise_for_status()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 59:
                await asyncio.sleep(2)
    die(f"server '{name}': {upstream}/health unavailable after 60 attempts: {last_error}")


def build_headers(state: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    # db_id / db_id_header_name are None when reset_on_run=False — the gym
    # operates on its own built-in state and no per-run database is provisioned.
    db_id = state.get("db_id")
    db_id_header = state.get("db_id_header_name")
    if db_id and db_id_header:
        headers[db_id_header] = db_id
    if state["token"]:
        headers[state["auth_header_name"]] = state["token"]
    # HARBOR-LOCAL: per-task corpus selection. When the task.toml entry carries
    # a ``dataset`` ("real" | "synthetic"), send it as ``x-dataset`` on every
    # upstream call — the /reset that provisions this trial's database reads it
    # to clone the named corpus snapshot, and it rides on every later /step so a
    # reset between runs restores the same corpus. Absent -> no header, and the
    # gym applies its own default (synthetic). See connectors' app/dataset.py.
    dataset = state.get("dataset")
    if dataset:
        headers["x-dataset"] = dataset
    # Daytona preview URLs are token-gated by default — the worker passes
    # the token in via ``<remote_url_env>_TOKEN`` and we send it as
    # ``x-daytona-preview-token`` on every upstream request.
    preview_token = state.get("preview_token")
    if preview_token:
        headers["x-daytona-preview-token"] = preview_token
    # In Docker mode the root entrypoint creates this capability before it
    # starts both the supervisor (connector services) and this proxy.  It is
    # never inherited by the non-root agent command.  The connector gateway
    # uses it to distinguish Harbor lifecycle/verification calls from an
    # agent curling the same loopback port.
    try:
        headers[CONTROL_CAPABILITY_HEADER] = _control_capability()
    except RuntimeError:
        # Docker bootstrap rejects this case before it can serve. Daytona has
        # no shared localhost connector namespace and may use a public gym.
        if MODE == "docker":
            raise
    return headers


def verifier_request_is_authorized(request: Request) -> bool:
    """Check the second factor on the root-only trusted socket.

    Unix socket ownership blocks the agent from connecting.  The per-run
    capability also prevents an accidentally group-readable socket from
    becoming a control-plane route.
    """
    try:
        expected = _verifier_capability()
    except RuntimeError:
        return False
    supplied = request.headers.get(VERIFIER_CAPABILITY_HEADER, "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


async def preflight_connector_boundary(
    client: httpx.AsyncClient, name: str, upstream: str, headers: dict[str, str],
) -> None:
    """Prove that this connector blocks direct TCP and accepts only the proxy.

    A shared container makes localhost a convenience, not an isolation boundary.
    The selected gym must therefore reject a bare ``/step`` call and accept the
    same request with the protected gateway header. Older connectors without
    that client-mode gateway are unsafe and must not start an agent run.
    """
    probe = {"action_type": "ListToolsAction"}
    direct = await client.post(f"{upstream}/step", json=probe)
    if direct.status_code != 404:
        raise RuntimeError(
            f"server '{name}' does not enforce the trusted gateway header and client mode"
        )
    trusted = await client.post(f"{upstream}/step", headers=headers, json=probe)
    if trusted.status_code == 404:
        raise RuntimeError(
            f"server '{name}' rejected the trusted gateway probe; refusing direct-TCP exposure"
        )
    trusted.raise_for_status()


def _require_successful_reset(response: httpx.Response, context: str) -> None:
    """Require a semantic reset success, not merely an HTTP 2xx response."""
    response.raise_for_status()
    try:
        body = response.json() or {}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{context} returned invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"{context} returned a non-object response: {body!r}")

    observation = body.get("observation")
    observation = observation if isinstance(observation, dict) else {}
    metadata = observation.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    reset_result = metadata.get("database_reset_result")

    if isinstance(reset_result, dict) and "success" in reset_result:
        if reset_result.get("success") is True:
            return
        if reset_result.get("success") is False:
            raise RuntimeError(
                f"{context} reported failed seed: "
                f"{reset_result.get('message') or reset_result}"
            )
    if observation.get("success") is True or body.get("success") is True:
        return
    if observation.get("success") is False or body.get("success") is False:
        detail = observation.get("message") or body.get("message") or body
        raise RuntimeError(f"{context} reported failure: {detail}")
    raise RuntimeError(f"{context} returned no success marker: {body}")


async def do_reset(
    client: httpx.AsyncClient,
    upstream: str,
    headers: dict[str, str],
    sql: str | None,
    db_id: str,
) -> None:
    """Reset the upstream gym's database.

    When *sql* is None we POST ``/reset`` with an empty body and the standard
    ``x-use-default-seed`` header for gyms that implement it, then require the
    response metadata to confirm that the generated database exists. When
    *sql* is a string, we try the modern ``{"sql_content": ...}`` path and
    fall back to the older reset+/api/seed-database flow for compatibility.
    """
    if sql is None:
        # HARBOR-DEFAULT-SEED: request the standard built-in seed where the gym
        # supports it. Some legacy gyms ignore this header and report a failed
        # reset inside HTTP 200, so semantic validation below is authoritative.
        default_seed_headers = dict(headers)
        default_seed_headers["x-use-default-seed"] = "true"
        r = await client.post(
            f"{upstream}/reset", headers=default_seed_headers, json={})
        _require_successful_reset(r, "/reset default seed")
        return

    errors: list[str] = []

    # Newer OpenEnv runtimes can seed directly through /reset.
    try:
        r = await client.post(
            f"{upstream}/reset",
            headers=headers,
            json={"sql_content": sql},
        )
        _require_successful_reset(r, "/reset sql_content")
        return
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/reset sql_content failed: {exc}")

    # Older direct-mode gym images reset first, then seed through /api/seed-database.
    try:
        reset = await client.post(f"{upstream}/reset", headers=headers, json={})
        reset.raise_for_status()
        seed = await client.post(
            f"{upstream}/api/seed-database",
            headers=headers,
            json={"database_id": db_id, "sql_content": sql},
        )
        seed.raise_for_status()
        return
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/reset + /api/seed-database failed: {exc}")

    raise RuntimeError("; ".join(errors))


async def do_step(
    client: httpx.AsyncClient,
    upstream: str,
    headers: dict[str, str],
    action: dict[str, Any],
) -> dict[str, Any]:
    r = await client.post(
        f"{upstream}/step",
        headers=headers,
        json=action,
    )
    if r.status_code in {400, 422}:
        raise _response_validation_error(r)
    r.raise_for_status()
    return r.json() or {}


async def do_state(
    client: httpx.AsyncClient,
    upstream: str,
    headers: dict[str, str],
    verify_queries: list[str] | None = None,
) -> dict[str, Any]:
    params = [("verify_queries", q) for q in (verify_queries or [])]
    r = await client.get(f"{upstream}/state", headers=headers, params=params)
    r.raise_for_status()
    return r.json() or {}


async def snapshot_full_db(
    client: httpx.AsyncClient, upstream: str, headers: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    tables_resp = await do_state(
        client, upstream, headers,
        ["SELECT name FROM sqlite_master WHERE type='table'"],
    )
    tables = [
        row["name"]
        for row in (tables_resp.get("verification_results", [{}])[0].get("result") or [])
        if row.get("name") and row["name"] not in SNAPSHOT_EXCLUDE
    ]
    dump: dict[str, list[dict[str, Any]]] = {}
    for t in tables:
        resp = await do_state(
            client, upstream, headers,
            [f"SELECT * FROM {t} ORDER BY rowid"],
        )
        dump[t] = resp.get("verification_results", [{}])[0].get("result") or []
    return dump


async def bootstrap() -> None:
    global FORBIDDEN_TOOLS, READY
    require_docker_control_capability()
    cfg = load_task_config()
    FORBIDDEN_TOOLS = load_forbidden_tools()
    metadata = cfg.get("metadata") or {}
    entries = list(metadata.get("mcp_servers_extended") or [])
    cli_entries = metadata.get("cli_servers_extended") or []
    # HARBOR-LOCAL: a bash/CLI-only task (gws, or a connector's own CLI
    # surface used instead of its MCP layer) legitimately registers zero MCP
    # servers -- the agent never calls this proxy at all. Without the opt-in
    # flag this stays a loud failure, since an empty list is far more often a
    # forgotten --gym than a real CLI-only task.
    if not entries and not cli_entries and not bool(metadata.get("cli_only", False)):
        die(
            "task.toml: [[metadata.mcp_servers_extended]] has no entries. "
            "If this is intentionally a bash/CLI-only task, set "
            "metadata.cli_only = true."
        )

    # HARBOR-LOCAL: the before-agent full-DB snapshot (snapshot_full_db) is
    # consumed ONLY by the JSON State verifier axis. When that axis is
    # disabled for the run (metadata.state_snapshot_enabled = false, plumbed
    # from the batch's allowed_verifier_types) we skip the snapshot entirely.
    # This avoids a SELECT * over every table — essential for gyms with very
    # large tables that would otherwise OOM the gym during the dump. A
    # missing key defaults to True so legacy task.toml files are unchanged.
    state_snapshot_enabled = bool(
        (cfg.get("metadata") or {}).get("state_snapshot_enabled", True)
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for entry in entries:
            name = entry.get("name")
            binary = entry.get("binary")
            token = entry.get("access_token", "")
            seed_file = entry.get("seed_file")
            auth_header_name = entry.get("auth_header_name")
            db_id_header_name = entry.get("db_id_header_name")
            # HARBOR-LOCAL: per-task corpus ("real" | "synthetic"); absent means
            # the task said nothing and the gym uses its own default (synthetic).
            # Normalised here so a stray "  Synthetic " matches the gym's names.
            dataset_raw = entry.get("dataset")
            dataset = (
                dataset_raw.strip().lower()
                if isinstance(dataset_raw, str) and dataset_raw.strip()
                else None
            )

            # Read early so required-field validation and db_id generation
            # can both branch on it. Absent key → False so older task.toml
            # files (pre-feature) preserve the new opt-in semantics.
            reset_on_run: bool = bool(entry.get("reset_on_run", False))

            # db_id_header_name is only required when we're actually calling
            # /reset and provisioning a per-run database. When reset is
            # disabled the gym operates on its own built-in state and no
            # database-id header is sent on any request.
            # ``auth_header_name`` is only required when this gym actually
            # uses auth (a non-empty access_token). Gyms with no auth send
            # both empty — build_headers() then skips the auth header
            # entirely, so the header name is irrelevant. Requiring it only
            # when ``token`` is present keeps auth-less gyms dispatchable
            # while still catching a token-without-header misconfiguration.
            required_fields = [
                ("name", name),
                *([("auth_header_name", auth_header_name)] if token else []),
                *([("db_id_header_name", db_id_header_name)] if reset_on_run else []),
            ]
            missing = [k for k, v in required_fields if not v]
            if missing:
                die(
                    "metadata.mcp_servers_extended entry missing required "
                    f"fields {missing}: {entry!r}"
                )
            if binary is not None and (
                not isinstance(binary, str) or binary not in CLI_BRIDGE_TOOL_NAMES
            ):
                die(
                    f"metadata.mcp_servers_extended server {name!r} has unsupported "
                    f"CLI bridge binary {binary!r}"
                )

            sql: str | None
            if seed_file:
                seed_path = (TASK_DIR / seed_file).resolve()
                if not seed_path.exists():
                    die(f"server '{name}': seed file not found: {seed_path}")
                sql = seed_path.read_text()
                if not sql.strip():
                    die(f"server '{name}': seed file is empty: {seed_path}")
            else:
                sql = None

            upstream = upstream_for(entry)

            # Only mint a db_id when we're resetting — no /reset means no
            # per-run database is provisioned, so there's nothing to identify.
            db_id: str | None = new_db_id() if reset_on_run else None

            preview_token: str | None = None
            if MODE == "daytona":
                token_env = entry.get("remote_url_env")
                if token_env:
                    preview_token = os.environ.get(f"{token_env}_TOKEN") or None

            # HARBOR-LOCAL: tool allowlist (None = no restriction; empty
            # set = block all; non-empty set = only those tool names).
            # Coerce here once so list_tools / call_tool stay branch-free.
            raw_allowed = entry.get("allowed_tools")
            allowed_tools: set[str] | None
            if isinstance(raw_allowed, list):
                allowed_tools = {
                    str(t) for t in raw_allowed if isinstance(t, str)
                }
            else:
                allowed_tools = None

            state = {
                "upstream": upstream,
                # None when reset_on_run=False — build_headers skips the
                # db_id header in that case.
                "db_id": db_id,
                "token": token,
                "auth_header_name": auth_header_name,
                "db_id_header_name": db_id_header_name if reset_on_run else None,
                "preview_token": preview_token,
                # HARBOR-LOCAL: per-task corpus, sent as x-dataset by
                # build_headers on /reset and every call. None -> gym default.
                "dataset": dataset,
                "tools": [],
                # HARBOR-LOCAL: optional tool-name allowlist (batch Tool Config,
                # or the OpenAI-only golden tool-name cap resolved server-side).
                # We never carry golden *arguments* here — leaking them would let
                # the agent copy the golden solution.
                "allowed_tools": allowed_tools,
            }
            if binary is not None:
                state["binary"] = binary
                bridge_tools = set(CLI_BRIDGE_TOOL_NAMES[binary])
                if state["allowed_tools"] is None:
                    state["allowed_tools"] = bridge_tools
                elif not state["allowed_tools"].issubset(bridge_tools):
                    die(
                        f"CLI bridge server {name!r} allows tools outside "
                        f"{sorted(bridge_tools)}"
                    )
            headers = build_headers(state)

            logger.info(
                "server '%s' upstream=%s db_id=%s auth_hdr=%s db_hdr=%s seed=%s reset_on_run=%s dataset=%s",
                name, upstream, db_id or "<none>", auth_header_name,
                db_id_header_name if reset_on_run else "<none>",
                seed_file or "<gym default>", reset_on_run,
                dataset or "<gym default>",
            )
            await wait_for_upstream(client, name, upstream)
            if MODE == "docker":
                try:
                    await preflight_connector_boundary(client, name, upstream, headers)
                except Exception as exc:  # noqa: BLE001
                    die(f"server '{name}': connector boundary preflight failed: {exc}")
            if reset_on_run:
                try:
                    await do_reset(client, upstream, headers, sql, db_id)
                except Exception as exc:
                    die(f"server '{name}': /reset failed: {exc}")
            else:
                logger.info(
                    "server '%s': /reset skipped, db_id not generated (reset_on_run=False)", name
                )

            if binary is None:
                try:
                    resp = await do_step(
                        client, upstream, headers,
                        {"action_type": "ListToolsAction"},
                    )
                except Exception as exc:
                    die(f"server '{name}': initial ListToolsAction failed: {exc}")

                state["tools"] = (resp.get("observation") or {}).get("tools_list") or []
                logger.info("server '%s' ready with %d tool(s)", name, len(state["tools"]))
                state["tools"] = _sanitize_tool_catalog(name, state["tools"])
            else:
                logger.info(
                    "server '%s' ready with MCP CLI bridge for %s", name, binary
                )
            # HARBOR-LOCAL: surface allowlist size at startup so a missing
            # / wrongly-named tool is obvious in the run logs (the proxy
            # otherwise silently filters it out).
            if binary is None and state["allowed_tools"] is not None:
                visible = sum(
                    1
                    for t in state["tools"]
                    if t.get("name") in state["allowed_tools"]
                )
                logger.info(
                    "server '%s' tool allowlist active: %d/%d tools visible "
                    "(allowlist size=%d)",
                    name, visible, len(state["tools"]),
                    len(state["allowed_tools"]),
                )

            # Capture before-agent DB snapshot for the verifier.
            # HARBOR-LOCAL: only when the JSON State axis is enabled — see
            # state_snapshot_enabled above. Skipping leaves no *.before.json,
            # and the verifier (test_outputs.py) only dumps the after-state
            # for servers that have a before-snapshot, so the heavy SELECT *
            # is avoided on both sides when state checking is off.
            if state_snapshot_enabled:
                try:
                    before = await snapshot_full_db(client, upstream, headers)
                    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                    (SNAPSHOT_DIR / f"{name}.before.json").write_text(
                        json.dumps(before, indent=2, default=str)
                    )
                    logger.info(
                        "server '%s' before-snapshot saved (%d tables)",
                        name, len(before),
                    )
                except Exception as exc:
                    die(f"server '{name}': before-snapshot failed: {exc}")
            else:
                logger.info(
                    "server '%s': before-snapshot skipped (JSON State verifier disabled)",
                    name,
                )

            STATE[name] = state

        # Native CLI connectors use the same trusted lifecycle and episode
        # identity, but are intentionally omitted from MCP discovery. Their
        # installed binary is the only agent-facing command interface.
        for entry in cli_entries:
            name = entry.get("name")
            binary = entry.get("binary")
            token = entry.get("access_token", "")
            auth_header_name = entry.get("auth_header_name")
            db_id_header_name = entry.get("db_id_header_name")
            reset_on_run = bool(entry.get("reset_on_run", False))
            required_fields = [
                ("name", name),
                ("binary", binary),
                *([("auth_header_name", auth_header_name)] if token else []),
                *([("db_id_header_name", db_id_header_name)] if reset_on_run else []),
            ]
            missing = [key for key, value in required_fields if not value]
            if missing:
                die(
                    "metadata.cli_servers_extended entry missing required "
                    f"fields {missing}: {entry!r}"
                )
            if not isinstance(binary, str) or binary not in CLI_BRIDGE_DESCRIPTIONS:
                die(
                    f"metadata.cli_servers_extended server {name!r} has unsupported "
                    f"CLI binary {binary!r}"
                )

            seed_file = entry.get("seed_file")
            if seed_file:
                seed_path = (TASK_DIR / str(seed_file)).resolve()
                if not seed_path.exists():
                    die(f"CLI server '{name}': seed file not found: {seed_path}")
                sql: str | None = seed_path.read_text()
                if not sql.strip():
                    die(f"CLI server '{name}': seed file is empty: {seed_path}")
            else:
                sql = None

            dataset_raw = entry.get("dataset")
            dataset = (
                dataset_raw.strip().lower()
                if isinstance(dataset_raw, str) and dataset_raw.strip()
                else None
            )
            preview_token: str | None = None
            if MODE == "daytona":
                token_env = entry.get("remote_url_env")
                if token_env:
                    preview_token = os.environ.get(f"{token_env}_TOKEN") or None
            state = {
                "upstream": upstream_for(entry),
                "db_id": new_db_id() if reset_on_run else None,
                "token": token,
                "auth_header_name": auth_header_name,
                "db_id_header_name": db_id_header_name if reset_on_run else None,
                "preview_token": preview_token,
                "dataset": dataset,
                "binary": binary,
            }
            headers = build_headers(state)
            await wait_for_upstream(client, str(name), state["upstream"])
            if MODE == "docker":
                try:
                    await preflight_connector_boundary(
                        client, str(name), state["upstream"], headers
                    )
                except Exception as exc:  # noqa: BLE001
                    die(f"CLI server '{name}': connector boundary preflight failed: {exc}")
            if reset_on_run:
                try:
                    await do_reset(
                        client, state["upstream"], headers, sql,
                        state["db_id"],
                    )
                except Exception as exc:
                    die(f"CLI server '{name}': /reset failed: {exc}")
            if state_snapshot_enabled:
                try:
                    before = await snapshot_full_db(
                        client, state["upstream"], headers
                    )
                    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                    (SNAPSHOT_DIR / f"{name}.before.json").write_text(
                        json.dumps(before, indent=2, default=str)
                    )
                except Exception as exc:
                    die(f"CLI server '{name}': before-snapshot failed: {exc}")
            CLI_STATE[str(name)] = state
            logger.info("CLI server '%s' ready as %s", name, binary)

    # HARBOR-LOCAL: provider-aware aggregate tool-count guard. When several
    # gyms are combined, their catalogs can exceed OpenAI's 128-tool array cap,
    # and the agent then dies on its FIRST completion with an opaque
    # "Invalid 'tools': array too long" 400 — which the platform otherwise
    # records as a low-scoring "completed" run. Fail fast here with an explicit
    # message instead. Trips ONLY for OpenAI-family models AND only when the gym
    # tools ALONE already exceed the cap, so a run that could actually fit
    # (<=128) is never blocked. The run's model is read from
    # metadata.run_model (falling back to verifier_judge.model for task.toml
    # files dispatched before run_model was stamped).
    run_model = _run_model_from_cfg(cfg)
    if _is_openai_family(run_model):
        total_visible = 0
        for nm, st in STATE.items():
            allowed = st.get("allowed_tools")
            binary = st.get("binary")
            if binary:
                bridge_tools = CLI_BRIDGE_TOOL_NAMES[binary]
                total_visible += len(
                    bridge_tools if allowed is None else set(bridge_tools).intersection(allowed)
                )
                continue
            catalog = st.get("tools") or []
            total_visible += sum(
                1 for t in catalog
                if (allowed is None or t.get("name") in allowed)
                and t.get("name") not in FORBIDDEN_TOOLS
            )
        logger.info(
            "aggregate tool count across %d gym(s): %d (OpenAI limit %d)",
            len(STATE), total_visible, OPENAI_TOOL_LIMIT,
        )
        if total_visible > OPENAI_TOOL_LIMIT:
            die(
                f"HARBOR TOOL-LIMIT ABORT: this run exposes {total_visible} MCP tools "
                f"across {len(STATE)} gym(s) [{', '.join(STATE)}], but model "
                f"'{run_model}' (OpenAI-family) allows at most {OPENAI_TOOL_LIMIT} "
                f"tools per request. Reduce the number of gyms on this task, switch to "
                f"a model without the 128-tool cap (e.g. Claude), or set a batch Tool "
                f"Config allowlist to trim the toolset to <= {OPENAI_TOOL_LIMIT}."
            )

    READY = True


def _extract_tool_payload(tool_result: Any) -> str:
    """OpenEnv /step responses wrap the tool payload in one of three shapes:

    * ``tool_result.content[0].text`` — MCP-standard text block (some servers).
    * ``tool_result.data``            — flat data field (Teams).
    * ``tool_result`` itself is the payload — raw JSON object/array/scalar
      (Freshdesk). Serialize it so the agent sees real content, not "".

    The agent-facing response is always a string.
    """
    if isinstance(tool_result, dict):
        content = tool_result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text")
                if isinstance(text, str):
                    return text
        data = tool_result.get("data")
        if isinstance(data, str):
            return data
        if data is not None:
            return json.dumps(data, default=str)
        text = tool_result.get("text")
        if isinstance(text, str):
            return text
        # Freshdesk shape: the whole tool_result IS the payload.
        return json.dumps(tool_result, default=str)
    if isinstance(tool_result, str):
        return tool_result
    if tool_result is None:
        return ""
    return json.dumps(tool_result, default=str)


# Common-denominator schema keys rejected by at least one supported provider.
_SCHEMA_PROBLEM_KEYS = frozenset({
    "anyOf", "oneOf", "allOf", "not",
    "$ref",
    "additionalProperties", "title", "$defs", "definitions",
    "unevaluatedProperties", "patternProperties", "dependentSchemas",
    "if", "then", "else",
})


def _check_node(
    node: Any, depth: int = 0, *, problem_keys: frozenset[str] | None = None,
) -> list[str]:
    """Return a list of problematic keys found anywhere in the schema node."""
    keys = problem_keys if problem_keys is not None else _SCHEMA_PROBLEM_KEYS
    if depth > 32 or not isinstance(node, dict):
        return []
    found: list[str] = []
    for k, v in node.items():
        if k == "properties" and isinstance(v, dict):
            # Keys in ``properties`` are tool argument names. A tool may
            # legitimately require an argument called ``title`` or ``default``.
            # Only the schemas stored under those names need inspection.
            for property_schema in v.values():
                found.extend(
                    _check_node(property_schema, depth + 1, problem_keys=keys)
                )
        elif k in keys:
            found.append(k)
        elif isinstance(v, dict):
            found.extend(_check_node(v, depth + 1, problem_keys=keys))
        elif isinstance(v, list):
            for item in v:
                found.extend(_check_node(item, depth + 1, problem_keys=keys))
    return found


class SchemaCompatibilityError(ValueError):
    """A tool schema cannot be represented safely at the provider boundary."""


_SCHEMA_DROP_KEYS = frozenset(
    {
        "$schema",
        "additionalProperties",
        "title",
        "definitions",
        "$defs",
        "unevaluatedProperties",
        "patternProperties",
        "dependentSchemas",
        "if",
        "then",
        "else",
        "not",
    }
)


def _json_pointer(root: dict[str, Any], ref: str) -> Any:
    """Resolve a local JSON pointer without accepting external references."""
    if not ref.startswith("#/"):
        raise SchemaCompatibilityError(f"external schema reference is unsupported: {ref!r}")
    node: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaCompatibilityError(f"unresolved schema reference: {ref!r}")
        node = node[part]
    return node


def _schema_types(node: dict[str, Any]) -> set[str]:
    value = node.get("type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _merge_union(branches: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a non-narrowing schema for anyOf/oneOf branches.

    Provider tool schemas cannot consistently express unions. A type is kept
    only when every branch agrees; otherwise the type constraint is omitted so
    every canonically valid input can reach upstream validation.
    """
    if not branches:
        return {}

    type_sets = [_schema_types(branch) for branch in branches]
    agreed_type: str | None = None
    if all(len(types) == 1 for types in type_sets):
        candidates = {next(iter(types)) for types in type_sets}
        if len(candidates) == 1:
            agreed_type = candidates.pop()

    out: dict[str, Any] = {}
    if agreed_type:
        out["type"] = agreed_type

    descriptions = [
        str(branch["description"]).strip()
        for branch in branches
        if branch.get("description")
    ]
    if descriptions:
        out["description"] = " ".join(dict.fromkeys(descriptions))

    if agreed_type == "object":
        property_variants: dict[str, list[dict[str, Any]]] = {}
        for branch in branches:
            for name, schema in (branch.get("properties") or {}).items():
                if isinstance(schema, dict):
                    property_variants.setdefault(name, []).append(schema)
        if property_variants:
            out["properties"] = {
                name: variants[0]
                if all(variant == variants[0] for variant in variants)
                else _merge_union(variants)
                for name, variants in property_variants.items()
            }
        required_sets = [set(branch.get("required") or []) for branch in branches]
        if required_sets:
            required = sorted(set.intersection(*required_sets))
            if required:
                out["required"] = required
    elif agreed_type == "array":
        typed_items = [
            branch.get("items") for branch in branches
            if isinstance(branch.get("items"), dict)
        ]
        if len(typed_items) == len(branches):
            out["items"] = (
                typed_items[0]
                if all(item == typed_items[0] for item in typed_items)
                else _merge_union(typed_items)
            )

    enums = [branch.get("enum") for branch in branches]
    if all(isinstance(values, list) for values in enums):
        out["enum"] = list(dict.fromkeys(item for values in enums for item in values))
    return out


def _merge_all_of(base: dict[str, Any], branches: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge the object structure of allOf branches without inventing types."""
    out = dict(base)
    for branch in branches:
        branch_type = branch.get("type")
        if out.get("type") and branch_type and out["type"] != branch_type:
            raise SchemaCompatibilityError(
                f"incompatible allOf types: {out['type']!r} and {branch_type!r}"
            )
        if branch_type:
            out.setdefault("type", branch_type)
        if isinstance(branch.get("properties"), dict):
            properties = out.setdefault("properties", {})
            for name, schema in branch["properties"].items():
                if name not in properties:
                    properties[name] = schema
                # If two conjuncts constrain the same property, retaining the
                # first cannot reject a value valid under both. Upstream still
                # enforces the complete canonical constraint.
        required = set(out.get("required") or []) | set(branch.get("required") or [])
        if required:
            out["required"] = sorted(required)
    return out


def _sanitize_schema_node(
    node: Any,
    root: dict[str, Any],
    *,
    ref_stack: tuple[str, ...] = (),
) -> Any:
    if isinstance(node, list):
        return [_sanitize_schema_node(item, root, ref_stack=ref_stack) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or ref in ref_stack:
            raise SchemaCompatibilityError(f"cyclic or invalid schema reference: {ref!r}")
        resolved = copy.deepcopy(_json_pointer(root, ref))
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        if not isinstance(resolved, dict):
            raise SchemaCompatibilityError(f"schema reference is not an object: {ref!r}")
        resolved.update(siblings)
        return _sanitize_schema_node(resolved, root, ref_stack=(*ref_stack, ref))

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SCHEMA_DROP_KEYS or key in {"anyOf", "oneOf", "allOf"}:
            continue
        if key == "type" and isinstance(value, list):
            continue
        if key == "properties" and isinstance(value, dict):
            out["properties"] = {
                name: _sanitize_schema_node(schema, root, ref_stack=ref_stack)
                if isinstance(schema, dict)
                else schema
                for name, schema in value.items()
            }
        else:
            out[key] = _sanitize_schema_node(value, root, ref_stack=ref_stack)

    for union_key in ("anyOf", "oneOf"):
        raw_branches = node.get(union_key)
        if isinstance(raw_branches, list):
            branches = [
                _sanitize_schema_node(branch, root, ref_stack=ref_stack)
                for branch in raw_branches
                if isinstance(branch, dict)
            ]
            union = _merge_union(branches)
            out = _merge_all_of(union, [out])
            break

    raw_all_of = node.get("allOf")
    if isinstance(raw_all_of, list):
        branches = [
            _sanitize_schema_node(branch, root, ref_stack=ref_stack)
            for branch in raw_all_of
            if isinstance(branch, dict)
        ]
        out = _merge_all_of(out, branches)

    if out.get("type") == "array" and "items" not in out:
        # An unconstrained item schema accepts objects and scalars alike. Never
        # invent ``type: string`` for array items.
        out["items"] = {}
    return out


def sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a provider-safe, non-narrowing copy of an MCP input schema."""
    if not isinstance(schema, dict):
        raise SchemaCompatibilityError("tool inputSchema must be an object")
    sanitized = _sanitize_schema_node(copy.deepcopy(schema), schema)
    if not isinstance(sanitized, dict):
        raise SchemaCompatibilityError("sanitized tool inputSchema must be an object")
    if sanitized.get("type") not in (None, "object"):
        raise SchemaCompatibilityError(
            f"tool inputSchema root type must be 'object', got {sanitized.get('type')!r}"
        )
    sanitized["type"] = "object"
    sanitized.setdefault("properties", {})
    problems = _check_node(sanitized, problem_keys=_SCHEMA_PROBLEM_KEYS)
    if problems:
        raise SchemaCompatibilityError(
            "sanitizer left provider-hostile keys: " + ", ".join(sorted(set(problems)))
        )
    return sanitized


def _sanitize_tool_catalog(
    gym_name: str,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sanitize every live tool or abort before an agent trajectory starts."""
    out: list[dict[str, Any]] = []
    changed = 0
    for tool in tools:
        copied = dict(tool)
        original = copied.get("inputSchema") or {"type": "object", "properties": {}}
        try:
            copied["inputSchema"] = sanitize_tool_schema(original)
        except SchemaCompatibilityError as exc:
            raise SchemaCompatibilityError(
                f"{gym_name}/{tool.get('name', '<unknown>')}: {exc}"
            ) from exc
        changed += copied["inputSchema"] != original
        out.append(copied)
    if changed:
        logger.info("server '%s': sanitized %d/%d tool schema(s)", gym_name, changed, len(out))
    return out




def build_mcp_server(name: str) -> Server:
    state = STATE[name]
    srv = Server(name)

    @srv.list_tools()
    async def _list_tools() -> list[types.Tool]:
        # HARBOR-LOCAL: filter by allowlist when configured. None means
        # "no restriction" — preserve the upstream behavior of exposing
        # every tool the gym returned at bootstrap.
        allowed = state.get("allowed_tools")
        catalog = state["tools"]
        if allowed is not None:
            catalog = [t for t in catalog if t.get("name") in allowed]
        catalog = [t for t in catalog if t.get("name") not in FORBIDDEN_TOOLS]
        out: list[types.Tool] = []
        for t in catalog:
            # Expose the upstream tool verbatim. No golden-trajectory content is
            # ever appended to descriptions — that would bias/leak the answer.
            out.append(
                types.Tool(
                    name=t["name"],
                    description=t.get("description") or "",
                    inputSchema=(
                        t.get("inputSchema") or {"type": "object", "properties": {}}
                    ),
                )
            )
        return out

    @srv.call_tool()
    async def _call_tool(
        tool_name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        event_id = _new_trace_identity()
        event = {
            "schema": "harbor.proxy_tool_call.v1",
            "event_id": event_id,
            "server": name,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "started_at_ns": time.time_ns(),
        }
        _begin_trusted_tool_event(event)
        # HARBOR-LOCAL: reject calls outside the allowlist before any HTTP
        # work. The denial is still written to the protected trace so evidence
        # remains complete rather than silently disappearing from a run.
        allowed = state.get("allowed_tools")
        if allowed is not None and tool_name not in allowed:
            exc = SafeToolInputError(
                f"tool {tool_name!r} is not allowed for this batch"
            )
            finished_at_ns = time.time_ns()
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            return _mcp_tool_result(_safe_tool_error(exc), event_id, is_error=True)
        if tool_name in FORBIDDEN_TOOLS:
            exc = SafeToolInputError(f"tool {tool_name!r} is forbidden for this task")
            finished_at_ns = time.time_ns()
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            return _mcp_tool_result(_safe_tool_error(exc), event_id, is_error=True)
        try:
            headers = build_headers(state)
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await do_step(
                    client,
                    state["upstream"],
                    headers,
                    {
                        "action_type": "ToolCallAction",
                        "tool_name": tool_name,
                        "arguments": arguments or {},
                    },
                )
            obs = resp.get("observation") or {}
            if not obs.get("success"):
                raise RuntimeError("upstream /step failed")
            result = obs.get("tool_result")
            payload = _extract_tool_payload(result)
            is_error = obs.get("is_error") or (
                isinstance(result, dict) and result.get("isError")
            )
            if is_error:
                raise RuntimeError("tool error")
        except Exception as exc:
            finished_at_ns = time.time_ns()
            error_text = str(exc)
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(error_text.encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            logger.warning("connector tool call failed for %s/%s: %s", name, tool_name, error_text)
            return _mcp_tool_result(_safe_tool_error(exc), event_id, is_error=True)

        finished_at_ns = time.time_ns()
        event.update(
            {
                "accepted": True,
                "isError": False,
                "result": payload,
                "result_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            }
        )
        _append_trusted_tool_event(event)
        return _mcp_tool_result(payload, event_id)

    return srv


def _cli_bridge_schema(binary: str) -> dict[str, Any]:
    """Return the small typed request shape for a configured command bridge."""
    properties: dict[str, Any] = {
        "command": {
            "type": "string",
            "description": f"Complete {binary} command, including the {binary} prefix.",
        },
        "identity_token": {
            "type": "string",
            "description": "Optional caller identity token when the task supplies one.",
        },
    }
    if binary == "gh":
        properties["stdin"] = {
            "type": "string",
            "description": "Optional stdin, for example for `gh auth login --with-token`.",
        }
        properties["repo"] = {
            "type": "string",
            "description": "Optional default repository in OWNER/REPO format.",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": ["command"],
        "additionalProperties": False,
    }


def _validated_bridge_command(binary: str, arguments: dict[str, Any]) -> str:
    command = arguments.get("command")
    if not isinstance(command, str) or not command.strip():
        raise SafeToolInputError("command must be a non-empty string")
    # The connector's parser remains the command allowlist.  This check keeps
    # this bridge from becoming a generic command relay before it reaches it.
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise SafeToolInputError("invalid command quoting") from exc
    if not argv or argv[0] != binary:
        raise SafeToolInputError(f"command must begin with {binary!r}")
    return command


def _bridge_identity_headers(binary: str, arguments: dict[str, Any]) -> dict[str, str]:
    """Map typed identity fields to the selected connector's private headers.

    Values never enter the trusted trace.  They are request credentials, not
    evidence about the command the agent executed.
    """
    headers: dict[str, str] = {}
    identity = arguments.get("identity_token")
    if identity is not None:
        if not isinstance(identity, str):
            raise SafeToolInputError("identity_token must be a string")
        if identity:
            headers["x-gws-auth-token" if binary == "gws" else "x-github-user-token"] = identity
    if binary == "gh" and arguments.get("repo") is not None:
        repo = arguments["repo"]
        if not isinstance(repo, str):
            raise SafeToolInputError("repo must be a string")
        if repo:
            headers["x-gh-repo"] = repo
    return headers


async def _execute_cli_bridge(
    name: str, state: dict[str, Any], tool_name: str, arguments: dict[str, Any]
) -> str:
    binary = str(state["binary"])
    if tool_name == "gws_discovery":
        if binary != "gws":
            raise SafeToolInputError(f"tool {tool_name!r} is not allowed for this bridge")
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{state['upstream']}/commands", headers=build_headers(state)
            )
            response.raise_for_status()
            return json.dumps(response.json(), separators=(",", ":"), default=str)

    if tool_name != binary:
        raise SafeToolInputError(f"tool {tool_name!r} is not allowed for this bridge")
    command = _validated_bridge_command(binary, arguments)
    stdin = arguments.get("stdin")
    if stdin is not None and binary != "gh":
        raise SafeToolInputError("stdin is supported only by gh")
    if stdin is not None and not isinstance(stdin, str):
        raise SafeToolInputError("stdin must be a string")
    if isinstance(stdin, str) and len(stdin.encode("utf-8")) > MAX_CLI_STDIN_BYTES:
        raise SafeToolInputError("stdin is too large")

    headers = build_headers(state)
    headers.update(_bridge_identity_headers(binary, arguments))
    body: dict[str, str] = {"command": command}
    if isinstance(stdin, str):
        body["stdin"] = stdin
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.post(
            f"{state['upstream']}/exec", headers=headers, json=body
        )
        response.raise_for_status()
        result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("connector returned an invalid command result")
    output = result.get("stdout") or result.get("stderr")
    if not isinstance(output, str):
        output = json.dumps(result, separators=(",", ":"), default=str)
    if int(result.get("exit_code") or 0) != 0 or result.get("error"):
        raise RuntimeError(output or "command failed")
    return output


def build_cli_bridge_server(name: str, state: dict[str, Any]) -> Server:
    """Expose a configured gws/gh command runner only through MCP."""
    binary = str(state["binary"])
    srv = Server(name)
    tool_names = CLI_BRIDGE_TOOL_NAMES[binary]

    @srv.list_tools()
    async def _list_tools() -> list[types.Tool]:
        allowed = state.get("allowed_tools")
        tools = [
            types.Tool(
                name=binary,
                description=CLI_BRIDGE_DESCRIPTIONS.get(
                    binary, f"Run an allowlisted {binary} command."
                ),
                inputSchema=_cli_bridge_schema(binary),
            )
        ]
        if "gws_discovery" in tool_names:
            tools.append(types.Tool(
                name="gws_discovery",
                description="List the commands supported by the gws command runner.",
                inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            ))
        return [tool for tool in tools if allowed is None or tool.name in allowed]

    @srv.call_tool()
    async def _call_tool(
        tool_name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        safe_arguments = dict(arguments or {})
        # Identity and stdin can contain secrets.  The trusted trace records
        # the attempted command but never credentials or login payloads.
        trace_arguments = {
            key: value for key, value in safe_arguments.items()
            if key not in {"identity_token", "stdin"}
        }
        event_id = _new_trace_identity()
        event = {
            "schema": "harbor.proxy_tool_call.v1",
            "event_id": event_id,
            "server": name,
            "tool_name": tool_name,
            "arguments": trace_arguments,
            # The verifier uses this declaration to canonicalize the agent's
            # trajectory before it joins it to this protected event.  It must
            # come from the proxy, never from agent-provided trace metadata.
            "redacted_argument_keys": ["identity_token", "stdin"],
            "started_at_ns": time.time_ns(),
        }
        _begin_trusted_tool_event(event)
        if tool_name not in tool_names or (
            state.get("allowed_tools") is not None
            and tool_name not in state["allowed_tools"]
        ):
            exc = SafeToolInputError(f"tool {tool_name!r} is not allowed for this bridge")
            finished_at_ns = time.time_ns()
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            return _mcp_tool_result(_safe_tool_error(exc), event_id, is_error=True)
        try:
            payload = await _execute_cli_bridge(name, state, tool_name, safe_arguments)
        except Exception as exc:
            finished_at_ns = time.time_ns()
            error_text = str(exc)
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(error_text.encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            logger.warning("connector CLI call failed for %s/%s: %s", name, tool_name, error_text)
            return _mcp_tool_result(_safe_tool_error(exc), event_id, is_error=True)

        finished_at_ns = time.time_ns()
        event.update({
            "accepted": True,
            "isError": False,
            "result": payload,
            "result_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "finished_at_ns": finished_at_ns,
            "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
        })
        _append_trusted_tool_event(event)
        return _mcp_tool_result(payload, event_id)

    return srv


async def health(_request: Request) -> JSONResponse:
    if READY:
        if _has_control_capability(_request):
            return JSONResponse(
                {
                    "status": "ok",
                    "servers": list(STATE.keys()),
                    "cli_servers": list(CLI_STATE.keys()),
                },
                status_code=200,
            )
        return JSONResponse({"status": "ok"}, status_code=200)
    return JSONResponse({"status": "starting"}, status_code=503)


def build_public_app() -> Starlette:
    """Build the only HTTP application reachable by the agent.

    Never add OpenEnv control routes here. Public routes are native MCP, health,
    and the bounded command endpoints used exclusively by native CLI binaries.
    """
    # CLI_STATE is deliberately excluded: a native CLI connector must never
    # grow an agent-visible MCP endpoint as a compatibility fallback.
    mcp_servers = {
        name: (
            build_cli_bridge_server(name, state)
            if state.get("binary")
            else build_mcp_server(name)
        )
        for name, state in STATE.items()
    }
    session_managers: dict[str, StreamableHTTPSessionManager] = {
        name: StreamableHTTPSessionManager(
            app=srv, event_store=None, json_response=False
        )
        for name, srv in mcp_servers.items()
    }

    def asgi_for(name: str):
        sm = session_managers[name]

        async def handler(scope, receive, send):
            await sm.handle_request(scope, receive, send)

        return handler

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with contextlib.AsyncExitStack() as stack:
            for sm in session_managers.values():
                await stack.enter_async_context(sm.run())
            yield

    routes: list = [
        Route("/health", health, methods=["GET"]),
    ]

    async def cli_call(request: Request) -> JSONResponse:
        """Run one native CLI command through the proxy-owned episode state."""
        name = request.path_params["name"]
        state = CLI_STATE.get(name)
        if state is None:
            return JSONResponse({"error": "command not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request"}, status_code=400)
        command = body.get("command") if isinstance(body, dict) else None
        binary = str(state["binary"])
        try:
            validated_command = _validated_bridge_command(
                binary, {"command": command}
            )
        except SafeToolInputError as exc:
            return JSONResponse({"error": _safe_tool_error(exc)}, status_code=400)

        # The native wrapper can carry only the identity header understood by
        # this connector. It cannot select an episode database, dataset, or
        # Harbor capability; those are constructed by this proxy.
        identity_headers: dict[str, str] = {}
        if binary == "gws":
            token = request.headers.get("x-gws-auth-token")
            if token:
                identity_headers["x-gws-auth-token"] = token
        event_id = _new_trace_identity()
        event = {
            "schema": "harbor.proxy_tool_call.v1",
            "event_id": event_id,
            "server": name,
            "tool_name": f"cli:{binary}",
            "arguments": {"command": validated_command},
            "started_at_ns": time.time_ns(),
        }
        _begin_trusted_tool_event(event)
        try:
            headers = build_headers(state)
            headers.update(identity_headers)
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{state['upstream']}/exec",
                    headers=headers,
                    json={"command": validated_command},
                )
                response.raise_for_status()
                result = response.json()
            if not isinstance(result, dict):
                raise RuntimeError("connector returned an invalid command result")
        except Exception as exc:
            finished_at_ns = time.time_ns()
            error_text = str(exc)
            event.update({
                "accepted": False,
                "isError": True,
                "error": _safe_tool_error(exc),
                "result_sha256": hashlib.sha256(error_text.encode()).hexdigest(),
                "finished_at_ns": finished_at_ns,
                "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
            })
            _append_trusted_tool_event(event)
            logger.warning("native CLI call failed for %s: %s", name, error_text)
            return JSONResponse(
                {"stdout": "", "stderr": "service unavailable", "exit_code": 69},
                status_code=502,
            )

        rendered = json.dumps(result, separators=(",", ":"), default=str)
        failed = bool(result.get("error")) or int(result.get("exit_code") or 0) != 0
        finished_at_ns = time.time_ns()
        event.update({
            "accepted": not failed,
            "isError": failed,
            "result": result,
            "result_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "finished_at_ns": finished_at_ns,
            "latency_ms": (finished_at_ns - event["started_at_ns"]) / 1_000_000,
        })
        _append_trusted_tool_event(event)
        return JSONResponse(result)

    async def cli_commands(request: Request) -> JSONResponse:
        """List commands for the selected native CLI without exposing MCP."""
        name = request.path_params["name"]
        state = CLI_STATE.get(name)
        if state is None:
            return JSONResponse({"error": "command not found"}, status_code=404)
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(
                    f"{state['upstream']}/commands", headers=build_headers(state)
                )
                response.raise_for_status()
                result = response.json()
        except Exception as exc:
            logger.warning("native CLI command discovery failed for %s: %s", name, exc)
            return JSONResponse({"error": "service unavailable"}, status_code=502)
        return JSONResponse(result)

    routes.extend(
        [
            Route("/cli/{name}", cli_call, methods=["POST"]),
            Route("/cli/{name}/commands", cli_commands, methods=["GET"]),
        ]
    )

    for name in mcp_servers:
        routes.append(Mount(f"/mcp/{name}", app=asgi_for(name)))

    return Starlette(routes=routes, lifespan=lifespan)


def build_trusted_app() -> Starlette:
    """Build the root-only control-plane listener.

    This app is bound only to ``TRUSTED_PROXY_SOCKET``.  It keeps the legacy
    raw operations available to root-run verification and Oracle tooling while
    making them unreachable from the agent's TCP namespace.
    """
    async def authorized_state(request: Request) -> JSONResponse:
        if not verifier_request_is_authorized(request):
            return JSONResponse({"error": "not found"}, status_code=404)
        name = request.path_params["name"]
        all_state = {**STATE, **CLI_STATE}
        if name not in all_state:
            return JSONResponse({"error": "unknown server"}, status_code=404)
        state = all_state[name]
        queries = [
            value
            for key, value in request.query_params.multi_items()
            if key == "verify_queries"
        ]
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            data = await do_state(client, state["upstream"], build_headers(state), queries)
        return JSONResponse(data)

    async def authorized_step(request: Request) -> JSONResponse:
        if not verifier_request_is_authorized(request):
            return JSONResponse({"error": "not found"}, status_code=404)
        name = request.path_params["name"]
        all_state = {**STATE, **CLI_STATE}
        if name not in all_state:
            return JSONResponse({"error": "unknown server"}, status_code=404)
        try:
            action = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid request"}, status_code=400)
        if not isinstance(action, dict):
            return JSONResponse({"error": "invalid request"}, status_code=400)
        state = all_state[name]
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            data = await do_step(client, state["upstream"], build_headers(state), action)
        return JSONResponse(data)

    async def authorized_trace_seal(request: Request) -> JSONResponse:
        if not verifier_request_is_authorized(request):
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            seal = seal_trusted_tool_trace()
        except RuntimeError:
            # A partially written evidence record is an infrastructure fault.
            # Do not expose proxy implementation details on this narrow route.
            return JSONResponse({"error": "trace cannot be sealed"}, status_code=503)
        return JSONResponse({"status": "sealed", "record_count": seal["record_count"]})

    return Starlette(
        routes=[
            Route("/raw/{name}/state", authorized_state, methods=["GET"]),
            Route("/raw/{name}/step", authorized_step, methods=["POST"]),
            Route("/seal-tool-trace", authorized_trace_seal, methods=["POST"]),
        ],
    )


# Kept for template helpers that import build_app.  It deliberately returns
# the public application, never the privileged control plane.
def build_app() -> Starlette:
    return build_public_app()


def bind_trusted_socket(path: Path) -> socket.socket:
    """Bind and protect the verifier socket before any ASGI server starts."""
    try:
        path.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        os.chmod(path, 0o600)
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            listener.close()
            raise RuntimeError("socket mode did not remain 0600")
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError as exc:
        raise RuntimeError("cannot bind protected trusted proxy socket") from exc


def main() -> None:
    try:
        asyncio.run(bootstrap())
    except SystemExit:
        raise
    except Exception as exc:
        die(f"bootstrap failed: {exc}")

    public_app = build_public_app()
    trusted_app = build_trusted_app()
    try:
        _verifier_capability()
        trusted_listener = bind_trusted_socket(TRUSTED_PROXY_SOCKET)
    except RuntimeError as exc:
        die(f"cannot prepare trusted proxy listener: {exc}")
    logger.info(
        "public proxy listening on %s:%d; trusted control socket at %s",
        PROXY_HOST, PROXY_PORT, TRUSTED_PROXY_SOCKET,
    )
    public_server = uvicorn.Server(
        uvicorn.Config(public_app, host=PROXY_HOST, port=PROXY_PORT, log_level="info")
    )
    trusted_server = uvicorn.Server(
        uvicorn.Config(trusted_app, log_level="info")
    )

    async def serve() -> None:
        await asyncio.gather(
            public_server.serve(), trusted_server.serve(sockets=[trusted_listener])
        )

    try:
        asyncio.run(serve())
    finally:
        trusted_listener.close()
        TRUSTED_PROXY_SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
