# ATTRIBUTION: lifted from rl-harbor-platform/harbor-task-template/solution/solve.py
# (FROZEN — do not edit; mirror upstream).
"""
Harbor task template — oracle replay (FROZEN).

Replays ``solution/golden_trajectory.json`` through the in-container MCP
proxy, substituting ``${ref}`` placeholders with IDs captured from earlier
upstream responses. Two intended uses:

  * **Oracle dry-run** during task authoring — populates
    ``tool_execution_results`` on every step (when ``--write-back`` is set)
    and provides the post-state that the verifier uses to compute
    ``tests/expected_diff.json``.
  * **Reference solution** — running the golden trajectory end-to-end is a
    sanity check that a correctly-performed task actually reaches the
    expected DB state.

The default proxy base is ``http://localhost:7000``. When running inside
the agent container (``docker compose exec main ...``) that just works.
From the host, either publish port 7000 in ``docker-compose.yaml`` or use
``docker compose exec``.

Exit codes:
  0  all steps succeeded
  2  golden trajectory not found
  3  proxy unreachable
  4  step is missing 'server' and no --server default was passed
  5  unresolved ``${ref}`` in a step's arguments
  6  upstream ``/step`` returned an error
  7  capture JSONPath did not match the response
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

REF_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
PATH_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]")


def substitute(value: Any, captures: dict[str, Any]) -> Any:
    """Recursively replace ``${name}`` strings with captured values."""
    if isinstance(value, str):
        m = REF_RE.match(value)
        if m:
            key = m.group(1)
            if key not in captures:
                raise KeyError(f"unresolved ${{{key}}} (no such capture yet)")
            return captures[key]
        return value
    if isinstance(value, dict):
        return {k: substitute(v, captures) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, captures) for v in value]
    return value


def resolve_jsonpath(data: Any, path: str) -> Any:
    """Minimal JSONPath evaluator (``$.a.b[0].c``). Dots and integer indices only."""
    if not path.startswith("$"):
        raise ValueError(f"jsonpath must start with '$': {path!r}")
    cur = data
    for token in PATH_TOKEN_RE.findall(path[1:]):
        if token.startswith("["):
            cur = cur[int(token[1:-1])]
        else:
            cur = cur[token]
    return cur


def _try_parse_json_value(s: str) -> Any:
    """Parse ``s`` as JSON if the head char suggests it; else return ``s``.

    Cheap pre-check (first non-whitespace char) avoids the cost of feeding
    non-JSON prose like ``"Error: foo"`` through ``json.loads`` only to
    fail. Matches the frontend's ``tryParseJsonObject`` policy so both
    sides expose identical tree shapes for JSONPath.
    """
    if not isinstance(s, str):
        return s
    stripped = s.strip()
    if not stripped:
        return s
    head = stripped[0]
    if head not in ("{", "[", "\""):
        return s
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return s


def extract_payload(tool_result: Any, _depth: int = 0, _max_depth: int = 12) -> Any:
    """Gym-agnostic tool-result unwrap. Recursively replaces every string
    in the tree that parses as JSON with the parsed value.

    Why this design (not gym-specific shape handlers): Harbor hosts 200+
    gyms and each is free to envelope its tool_result however it wants:

      * Gmail returns ``{result: "<json>", success: bool}``
      * Calendar returns ``{text: "<json>", status_code: int, isError: bool}``
      * MCP-canonical gyms return ``{content: [{type, text: "<json>"}]}``
      * OpenEnv passthrough returns ``{data: "<json>"}``
      * Future gyms will invent more

    The old shape-list approach (MCP + OpenEnv only) silently failed for
    every gym that uses a different wrapper, exiting solve.py at step 1
    with ``capture 'X' at <path> failed: '<root_key>'``. We don't want
    to add a branch per gym — that doesn't scale to 200+.

    Instead: deeply parse JSON-encoded strings wherever they appear. The
    gym's envelope shape is preserved verbatim, but any embedded JSON
    string is auto-expanded into a real subtree. JSONPath captures the
    trainer authored against the wizard's rendered tree therefore walk
    the same tree solve.py sees, so authored paths just work.

    Trainer's path semantics:
      * Gmail: ``$.result.messages[0].id``  (NOT ``$.messages[0].id``)
      * Calendar: ``$.text.currentDate``
      * MCP-canonical: ``$.content[0].text.X``
      * The wizard's "Quick capture" chips show the correct path
        automatically, so the trainer never has to know the wrapper.

    Termination: ``_max_depth`` caps recursion (defensive — pathological
    cases like a string that parses to a single-element list containing
    itself would otherwise spin forever; the depth check stops cycles
    even before the value-equality check could).
    """
    if _depth > _max_depth:
        return tool_result
    if tool_result is None:
        return None

    if isinstance(tool_result, str):
        parsed = _try_parse_json_value(tool_result)
        # If parsing yielded a container, recurse so nested encoded
        # payloads also get expanded (one pass handles arbitrarily-
        # deep encoding).
        if parsed is not tool_result and isinstance(parsed, (dict, list)):
            return extract_payload(parsed, _depth + 1, _max_depth)
        return parsed

    if isinstance(tool_result, list):
        return [extract_payload(v, _depth + 1, _max_depth) for v in tool_result]

    if isinstance(tool_result, dict):
        return {k: extract_payload(v, _depth + 1, _max_depth) for k, v in tool_result.items()}

    # Scalars (int, float, bool) pass through untouched.
    return tool_result


async def call_step(
    proxy_base: str,
    server: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one golden step through the public native MCP surface.

    Oracle runs as the unprivileged agent user, by design.  It must therefore
    exercise exactly the same allowlisted MCP interface as a model rather than
    calling the proxy's verifier-only raw control endpoint.  Preserve the MCP
    TextContent envelope so existing ``captures`` JSONPaths such as
    ``$.content[0].text.id`` keep their authored meaning.
    """
    url = f"{proxy_base}/mcp/{server}"
    async with streamablehttp_client(url, timeout=180.0) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    if result.isError:
        message = ""
        for content in result.content:
            text = getattr(content, "text", None)
            if isinstance(text, str) and text:
                message = text
                break
        raise RuntimeError(message or f"MCP tool {tool_name!r} failed")

    content: list[dict[str, Any]] = []
    for item in result.content:
        # TextContent is the normal connector response.  Preserve any future
        # MCP content block faithfully enough for JSON-path captures and audit
        # evidence instead of assuming a connector-specific response shape.
        if hasattr(item, "model_dump"):
            block = item.model_dump(mode="json", exclude_none=True)
        else:
            block = {"type": getattr(item, "type", "text")}
            if hasattr(item, "text"):
                block["text"] = item.text
        content.append(block)
    return {"content": content}, {"transport": "mcp", "server": server}


async def run(
    task_dir: Path,
    proxy_base: str,
    default_server: str | None,
    timeout: float,
    write_back: bool,
    quiet: bool,
) -> int:
    golden_path = task_dir / "solution" / "golden_trajectory.json"
    if not golden_path.exists():
        print(f"golden trajectory not found: {golden_path}", file=sys.stderr)
        return 2

    golden = json.loads(golden_path.read_text())
    captures: dict[str, Any] = {}

    # Bound connect separately from the overall read/write window so a wedged
    # proxy or gym sidecar can't hang the oracle replay at TCP-connect time: a
    # stuck connect fails fast (<=10s) while a legitimately slow tool call still
    # gets the full ``timeout``. (The standalone worker's solve.sh golden curls
    # had no caps at all — same gap, closed here for the embedded composite path.)
    client_timeout = httpx.Timeout(timeout, connect=min(10.0, timeout))
    async with httpx.AsyncClient(timeout=client_timeout) as client:
        try:
            h = await client.get(f"{proxy_base}/health")
            h.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"proxy not reachable at {proxy_base}: {exc}", file=sys.stderr)
            return 3

        for i, step in enumerate(golden):
            server = step.get("server") or default_server
            if not server:
                print(
                    f"step {i + 1}: missing 'server' field and no --server default",
                    file=sys.stderr,
                )
                return 4

            tool_name = step.get("name") or step.get("tool")
            raw_args = step.get("arguments") or step.get("args") or {}
            try:
                args = substitute(raw_args, captures)
            except KeyError as exc:
                print(f"step {i + 1} ({tool_name}): {exc}", file=sys.stderr)
                return 5

            if not quiet:
                print(f"[{i + 1}/{len(golden)}] {server}.{tool_name}")

            try:
                tool_result, _ = await call_step(
                    proxy_base, server, tool_name, args
                )
            except Exception as exc:  # noqa: BLE001
                print(f"step {i + 1} ({tool_name}) failed: {exc}", file=sys.stderr)
                return 6

            payload = extract_payload(tool_result)

            for cap_name, jpath in (step.get("captures") or {}).items():
                try:
                    captures[cap_name] = resolve_jsonpath(payload, jpath)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"step {i + 1} ({tool_name}): capture "
                        f"'{cap_name}' at {jpath} failed: {exc}",
                        file=sys.stderr,
                    )
                    return 7

            if write_back:
                # Canonical execution-results shape — same as the
                # live-gym Run All → Approve and per-step Execute paths.
                # Keeps every consumer on a single branch.
                step["tool_execution_results"] = {
                    "success": True,
                    "resolved_arguments": args,
                    "result": tool_result,
                    "error": None,
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                }

    if write_back:
        payload_str = json.dumps(golden, indent=2) + "\n"
        # Primary location — same dir Harbor's authoring layer reads
        # from (``solution/golden_trajectory.json``).
        golden_path.write_text(payload_str)
        if not quiet:
            print(f"wrote captured responses to {golden_path}")

        # Mirror into ``/logs/verifier/`` so the augmented file makes
        # it back to the host on the Daytona backend. Background:
        #
        #   • ``NamedVolumeDockerEnvironment`` (local docker) bind-mounts
        #     ``/app`` to host's ``work_dir``, so anything written under
        #     ``solution/`` is visible on host immediately.
        #
        #   • ``AuthDaytonaEnvironment`` (Daytona) does NOT bind-mount;
        #     ``/app`` lives entirely inside the sandbox VM. Harbor's
        #     framework only auto-pulls the trial's ``/logs/`` tree
        #     back to host's ``job_dir`` (which ``_collect_artifacts``
        #     then reads). The composite verifier (``test_outputs.py``)
        #     writes its outputs to ``/logs/verifier/`` for exactly
        #     this reason. Without mirroring solve.py's augmented
        #     trajectory there, the post-replay file with
        #     ``tool_execution_results`` is stranded in the sandbox
        #     and the host never sees it.
        #
        # NOTE: previous attempt wrote to ``<task_dir>/verifier/`` —
        # that's a Daytona-isolated path, NOT pulled. Must be
        # ``/logs/verifier/`` (the LOG_DIR test_outputs.py uses).
        #
        # Frontend already looks for both paths (``readBySuffix`` of
        # ``solution/golden_trajectory.json`` first, then ``verifier/``
        # as fallback), so either landing place renders correctly.
        try:
            mirror_dir = Path("/logs/verifier")
            mirror_dir.mkdir(parents=True, exist_ok=True)
            mirror_path = mirror_dir / "golden_trajectory.json"
            mirror_path.write_text(payload_str)
            if not quiet:
                print(f"mirrored to {mirror_path} (for daytona artifact pull)")
        except OSError as exc:
            # Don't fail the run on a mirror-write hiccup — the primary
            # file at ``solution/`` is still good for local-docker runs.
            print(f"warning: failed to mirror to /logs/verifier/: {exc}", file=sys.stderr)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--task-dir", default=os.environ.get("TASK_DIR", "/app"))
    parser.add_argument(
        "--proxy-base",
        default=os.environ.get("PROXY_BASE", "http://localhost:7000"),
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("ORACLE_DEFAULT_SERVER"),
        help="Default MCP server name when steps omit 'server' field",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="Persist recorded tool_execution_results into golden_trajectory.json",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    rc = asyncio.run(
        run(
            Path(args.task_dir).resolve(),
            args.proxy_base,
            args.server,
            args.timeout,
            args.write_back,
            args.quiet,
        )
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
