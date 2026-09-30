# ATTRIBUTION: lifted from rl-harbor-platform/harbor-task-template/tests/test_outputs.py
# (FROZEN — do not edit; mirror upstream).
"""
Harbor task template — FROZEN verifier.

Reads tests/manifest.json and produces /logs/verifier/reward.json.

Verifier type sub-scores are computed and combined:
  * state       — full-DB diff vs expected_diff.json
  * sql         — trainer-authored SQL assertions
  * rubric      — hierarchical LLM-judge over DB diff + trajectory + final output

The agent trajectory is kept as rubric evidence, but it is not scored against
the golden path. Total is normalized over verifier types that are enabled and
have authored checks/results:

Total = state_gate × equal_weighted_mean(active state/sql/rubric axes)
A non-empty "unauthorized changes" set forces side_effect_gate = 0.

Artifacts are persisted at /logs/verifier/snapshots/ for debugging and re-grading.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import re
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import httpx

TASK_DIR = Path(os.environ.get("TASK_DIR", "/app"))
LOG_DIR = Path("/logs/verifier")
SNAPSHOT_DIR = LOG_DIR / "snapshots"
PROXY_BASE = os.environ.get("PROXY_BASE", "http://localhost:7000")
STATE_SNAPSHOT_SCHEMA = "harbor.state_snapshot.v1"
STATE_DIFF_SCHEMA = "harbor.state_diff.v1"
DIFF_OPS = ("added", "removed", "changed")
VOLATILE_META_KEY = "_harbor_volatile_fields"
TEXT_TYPE_MARKERS = ("CHAR", "CLOB", "TEXT", "VARCHAR", "STRING")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_json_gzip(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any, *, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent, sort_keys=False, default=str) + "\n")


def write_json_gzip(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), default=str)


def load_manifest() -> dict[str, Any]:
    return load_json(TASK_DIR / "tests" / "manifest.json")


def load_task_toml() -> dict[str, Any]:
    return tomllib.loads((TASK_DIR / "task.toml").read_text())


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

def strip_fields(row: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in fields}


def canonicalize_rows(
    rows: list[dict[str, Any]],
    strip: set[str],
    sort: bool,
) -> list[dict[str, Any]]:
    out = [strip_fields(r, strip) for r in rows]
    if sort:
        out.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return out


# ---------------------------------------------------------------------------
# State diff
# ---------------------------------------------------------------------------

REF_RE = re.compile(r"^\$\{(\w+)\}$")
ENV_REF_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}$")


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(REF_RE.match(value))


def resolve_env_ref(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    m = ENV_REF_RE.match(value)
    if not m:
        return value
    return os.environ.get(m.group(1), m.group(2) or "")


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def is_text_column(
    field: str,
    expected: Any,
    actual: Any,
    column_types: dict[str, str] | None,
) -> bool:
    type_name = str((column_types or {}).get(field) or "").upper()
    if type_name and any(marker in type_name for marker in TEXT_TYPE_MARKERS):
        return True
    return not type_name and isinstance(expected, str) and isinstance(actual, str)


def field_matches(
    field: str,
    expected: Any,
    actual: Any,
    column_types: dict[str, str] | None = None,
    *,
    exact_strings: bool = False,
) -> bool:
    if is_ref(expected):
        return True
    if (
        not exact_strings
        and isinstance(expected, str)
        and expected != ""
        and is_text_column(field, expected, actual, column_types)
    ):
        return not is_empty_value(actual)
    return actual == expected


def rows_match(
    expected: dict[str, Any],
    actual: dict[str, Any],
    column_types: dict[str, str] | None = None,
    *,
    exact_strings: bool = False,
) -> bool:
    """Expected keys must all be present in actual.

    Structured values match exactly. Non-empty text expected values require a
    non-empty actual value unless exact string matching is requested. `${ref}`
    placeholders keep legacy behavior: the key only needs to exist.
    """
    for k, v in expected.items():
        if k not in actual:
            return False
        if not field_matches(k, v, actual[k], column_types, exact_strings=exact_strings):
            return False
    return True


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def state_include_exclude(state_cfg: dict[str, Any]) -> tuple[set[str] | None, set[str]]:
    snap_cfg = state_cfg.get("snapshot") or {}
    include_raw = snap_cfg.get("include_tables")
    include = set(include_raw) if include_raw else None
    exclude = set(snap_cfg.get("exclude_tables") or [])
    return include, exclude


def selected_tables(
    tables: list[str],
    state_cfg: dict[str, Any],
) -> list[str]:
    include, exclude = state_include_exclude(state_cfg)
    out = []
    for table in tables:
        if table in exclude:
            continue
        if include is not None and table not in include:
            continue
        out.append(table)
    return sorted(out)


# PR-1331 split the proxy in two. The PUBLIC app on PROXY_BASE keeps /health,
# /cli/* and /mcp/* -- the agent's sanctioned surface. /raw/{gym}/state moved to
# the TRUSTED app on a unix socket, so the old public call now 404s (routing, not
# auth: adding the header alone does nothing).
#
# Measured in-container on the PR-1331 image:
#   verifier runs as root -> reads the 040 capability file, connects to the 0600
#                            socket via CAP_DAC_OVERRIDE, GET .../state -> 200
#   agent (rlgymagent)    -> capability file Permission denied, socket Permission
#                            denied, /raw on 7000 -> 404, /health -> 200
# That asymmetry is the point: it is what closes the client-QC findings
# sanctioned_interface_use and golden_isolation.
#
# No socket == old template, where /raw/state is public. Falling back keeps this
# scorer working unchanged on bundles pinned to the older image.
VERIFIER_CAPABILITY_HEADER = "x-harbor-proxy-verifier-capability"
TRUSTED_PROXY_SOCKET = os.environ.get(
    "TRUSTED_PROXY_SOCKET", "/run/harbor/proxy/trusted-proxy.sock"
)


def verifier_capability() -> str:
    path = os.environ.get(
        "HARBOR_PROXY_VERIFIER_CAPABILITY_FILE",
        "/run/harbor/proxy-verifier-capability",
    )
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def query_state(server_name: str, query: str) -> list[dict[str, Any]]:
    params = [("verify_queries", query)]
    capability = verifier_capability()
    if Path(TRUSTED_PROXY_SOCKET).exists() and capability:
        # Host is ignored for a UDS transport; any absolute URL works.
        client = httpx.Client(
            transport=httpx.HTTPTransport(uds=TRUSTED_PROXY_SOCKET), timeout=60.0
        )
        url = f"http://localhost/raw/{server_name}/state"
        headers = {VERIFIER_CAPABILITY_HEADER: capability}
    else:
        client = httpx.Client(timeout=60.0)
        url = f"{PROXY_BASE}/raw/{server_name}/state"
        headers = {}
    with client as c:
        r = c.get(url, params=params, headers=headers)
        r.raise_for_status()
        body = r.json() or {}
    results = body.get("verification_results") or []
    if not results:
        return []
    return results[0].get("result") or []


def list_tables(server_name: str, state_cfg: dict[str, Any]) -> list[str]:
    rows = query_state(server_name, "SELECT name FROM sqlite_master WHERE type='table'")
    names = [str(r["name"]) for r in rows if r.get("name")]
    return selected_tables(names, state_cfg)


def table_meta(server_name: str, table: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns: list[str] = []
    primary_key: list[tuple[int, str]] = []
    column_types: dict[str, str] = {}
    try:
        info = query_state(server_name, f"PRAGMA table_info({quote_ident(table)})")
    except Exception as exc:  # noqa: BLE001
        print(f"[verifier] table_info failed for {server_name}.{table}: {exc}", file=sys.stderr)
        info = []
    for col in info:
        name = col.get("name")
        if name is not None:
            columns.append(str(name))
            column_types[str(name)] = str(col.get("type") or "")
        pk_index = int(col.get("pk") or 0)
        if pk_index > 0 and name is not None:
            primary_key.append((pk_index, str(name)))
    if not columns:
        columns = sorted({key for row in rows for key in row})
    return {
        "columns": columns,
        "primary_key": [name for _, name in sorted(primary_key)],
        "column_types": column_types,
    }


def dump_table_rows(server_name: str, table: str) -> list[dict[str, Any]]:
    try:
        return query_state(server_name, f"SELECT * FROM {quote_ident(table)} ORDER BY rowid")
    except Exception as exc:  # noqa: BLE001
        print(
            f"[verifier] raw dump failed for {server_name}.{table}; "
            f"retrying with hex-encoded columns: {exc}",
            file=sys.stderr,
        )
        info = query_state(server_name, f"PRAGMA table_info({quote_ident(table)})")
        columns = [str(row["name"]) for row in info if row.get("name")]
        if not columns:
            raise
        exprs = ["rowid AS __rowid__"] + [
            f"hex(CAST({quote_ident(col)} AS BLOB)) AS {quote_ident(col)}"
            for col in columns
        ]
        return query_state(
            server_name,
            f"SELECT {', '.join(exprs)} FROM {quote_ident(table)} ORDER BY rowid",
        )


def dump_full_db(server_name: str, state_cfg: dict[str, Any]) -> dict[str, Any]:
    """Dump the audited DB through the proxy.

    The verifier still audits the full selected DB for side effects, but only
    compact hashes/diffs are written as normal artifacts. Full rows are kept as
    gzip debug snapshots.
    """
    tables = list_tables(server_name, state_cfg)
    out: dict[str, Any] = {"tables": {}}
    for table in tables:
        rows = dump_table_rows(server_name, table)
        meta = table_meta(server_name, table, rows)
        out["tables"][table] = {
            "columns": meta["columns"],
            "primary_key": meta["primary_key"],
            "column_types": meta["column_types"],
            "rows": rows,
        }
    return out


def normalize_rows_snapshot(rows_by_table: dict[str, list[dict[str, Any]]], state_cfg: dict[str, Any]) -> dict[str, Any]:
    include, exclude = state_include_exclude(state_cfg)
    tables: dict[str, Any] = {}
    for table, rows in rows_by_table.items():
        if table in exclude:
            continue
        if include is not None and table not in include:
            continue
        tables[table] = {
            "columns": sorted({key for row in rows for key in row}),
            "primary_key": [],
            "column_types": {},
            "rows": rows,
        }
    return {"tables": tables}


def load_before_snapshot(server_name: str, state_cfg: dict[str, Any]) -> dict[str, Any]:
    summary_path = SNAPSHOT_DIR / f"{server_name}.before.json"
    if not summary_path.exists():
        return {"tables": {}}
    summary = load_json(summary_path)
    if isinstance(summary, dict) and summary.get("schema_version") == STATE_SNAPSHOT_SCHEMA:
        rows_path = SNAPSHOT_DIR / str(summary.get("rows_file", ""))
        if not rows_path.exists():
            raise FileNotFoundError(f"compressed before snapshot missing: {rows_path}")
        return normalize_rows_snapshot(load_json_gzip(rows_path), state_cfg)
    return normalize_rows_snapshot(summary, state_cfg)


def canonical_row(table: str, row: dict[str, Any], state_cfg: dict[str, Any]) -> dict[str, Any]:
    canon_cfg = state_cfg.get("canonicalize") or {}
    strip = set(canon_cfg.get("strip_fields") or [])
    per_table = canon_cfg.get("strip_fields_per_table") or {}
    strip.update(per_table.get(table) or [])
    return strip_fields(row, strip)


def row_identity(
    raw_row: dict[str, Any],
    canonical: dict[str, Any],
    primary_key: list[str],
) -> tuple[str, dict[str, Any]]:
    if primary_key and all(k in raw_row for k in primary_key):
        pk = {k: raw_row.get(k) for k in primary_key}
        return "pk:" + stable_json(pk), pk
    return "row:" + sha256_json(canonical), {}


def build_row_index(
    table: str,
    table_state: dict[str, Any],
    state_cfg: dict[str, Any],
    primary_key: list[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    for raw in table_state.get("rows") or []:
        canonical = canonical_row(table, raw, state_cfg)
        base_key, pk = row_identity(raw, canonical, primary_key)
        if base_key.startswith("row:"):
            seen[base_key] = seen.get(base_key, 0) + 1
            key = f"{base_key}#{seen[base_key]}"
        else:
            key = base_key
        index[key] = {
            "pk": pk,
            "row": canonical,
            "hash": sha256_json(canonical),
        }
    return index


def build_hash_snapshot(server_name: str, dump: dict[str, Any], state_cfg: dict[str, Any]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for table, table_state in sorted((dump.get("tables") or {}).items()):
        pk = list(table_state.get("primary_key") or [])
        row_index = build_row_index(table, table_state, state_cfg, pk)
        row_hashes = [entry["hash"] for _, entry in sorted(row_index.items())]
        tables[table] = {
            "columns": table_state.get("columns") or [],
            "primary_key": pk,
            "column_types": table_state.get("column_types") or {},
            "row_count": len(row_index),
            "table_hash": sha256_json(row_hashes),
        }
    return {
        "schema_version": STATE_SNAPSHOT_SCHEMA,
        "scope": "full_db_hash",
        "server": server_name,
        "tables": tables,
    }


def empty_diff(comment: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": STATE_DIFF_SCHEMA,
        "gyms": {},
    }
    if comment:
        out["_comment"] = comment
    return out


def ensure_diff_table(
    diff: dict[str, Any],
    gym: str,
    table: str,
    column_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    tables = diff.setdefault("gyms", {}).setdefault(gym, {}).setdefault("tables", {})
    ops = tables.setdefault(table, {"added": [], "removed": [], "changed": []})
    if column_types:
        ops.setdefault("column_types", column_types)
    return ops


def add_diff_item(
    diff: dict[str, Any],
    gym: str,
    table: str,
    op: str,
    item: dict[str, Any],
    column_types: dict[str, str] | None = None,
) -> None:
    ops = ensure_diff_table(diff, gym, table, column_types)
    ops.setdefault(op, []).append(item)


def table_diff(
    table: str,
    before_table: dict[str, Any],
    after_table: dict[str, Any],
    state_cfg: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    pk = list(after_table.get("primary_key") or before_table.get("primary_key") or [])
    before_idx = build_row_index(table, before_table, state_cfg, pk)
    after_idx = build_row_index(table, after_table, state_cfg, pk)
    added = [
        {"row": after_idx[key]["row"]}
        for key in sorted(set(after_idx) - set(before_idx))
    ]
    removed = [
        {"row": before_idx[key]["row"]}
        for key in sorted(set(before_idx) - set(after_idx))
    ]
    changed = []
    for key in sorted(set(before_idx) & set(after_idx)):
        if before_idx[key]["hash"] == after_idx[key]["hash"]:
            continue
        item = {
            "before": before_idx[key]["row"],
            "after": after_idx[key]["row"],
        }
        if before_idx[key]["pk"]:
            item["pk"] = before_idx[key]["pk"]
        changed.append(item)
    return {"added": added, "removed": removed, "changed": changed}


def diff_snapshots(
    before_snapshots: dict[str, dict[str, Any]],
    after_snapshots: dict[str, dict[str, Any]],
    state_cfg: dict[str, Any],
) -> dict[str, Any]:
    diff = empty_diff()
    for gym in sorted(set(before_snapshots) | set(after_snapshots)):
        before_tables = (before_snapshots.get(gym) or {}).get("tables") or {}
        after_tables = (after_snapshots.get(gym) or {}).get("tables") or {}
        for table in sorted(set(before_tables) | set(after_tables)):
            before_table = before_tables.get(table) or {"rows": [], "primary_key": [], "column_types": {}}
            after_table = after_tables.get(table) or {"rows": [], "primary_key": [], "column_types": {}}
            column_types = after_table.get("column_types") or before_table.get("column_types") or {}
            ops = table_diff(
                table,
                before_table,
                after_table,
                state_cfg,
            )
            if ops["added"] or ops["removed"] or ops["changed"]:
                ensure_diff_table(diff, gym, table, column_types)
                for op in DIFF_OPS:
                    for item in ops[op]:
                        add_diff_item(diff, gym, table, op, item, column_types)
    return diff


def normalize_diff_item(op: str, item: Any) -> dict[str, Any]:
    if op in {"added", "removed"}:
        if isinstance(item, dict) and "row" in item:
            return {"row": item["row"]}
        return {"row": item}
    if isinstance(item, dict):
        return {
            k: v for k, v in item.items()
            if k in {"pk", "before", "after"}
        }
    return {"after": item}


def iter_diff_entries(diff: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if diff.get("schema_version") == STATE_DIFF_SCHEMA or "gyms" in diff:
        for gym, gym_body in sorted((diff.get("gyms") or {}).items()):
            for table, ops in sorted(((gym_body or {}).get("tables") or {}).items()):
                column_types = (ops or {}).get("column_types") or {}
                for op in DIFF_OPS:
                    for item in ops.get(op) or []:
                        entries.append({
                            "gym": gym,
                            "table": table,
                            "op": op,
                            "item": normalize_diff_item(op, item),
                            "column_types": column_types,
                        })
        return entries

    # Legacy expected_diff.json: {"table": {"added": [{...}], "removed": [{...}]}}
    for table, ops in sorted(diff.items()):
        if table.startswith("_") or not isinstance(ops, dict):
            continue
        for op in DIFF_OPS:
            for item in ops.get(op) or []:
                entries.append({
                    "gym": None,
                    "table": table,
                    "op": op,
                    "item": normalize_diff_item(op, item),
                    "column_types": {},
                })
    return entries


def changed_item_matches(
    expected: dict[str, Any],
    actual: dict[str, Any],
    column_types: dict[str, str] | None = None,
) -> bool:
    if expected.get("pk") and not rows_match(
        expected["pk"],
        actual.get("pk") or {},
        column_types,
        exact_strings=True,
    ):
        return False
    if expected.get("before") is not None:
        if not rows_match(
            expected["before"],
            actual.get("before") or {},
            column_types,
            exact_strings=True,
        ):
            return False
    if expected.get("after") is not None:
        if not rows_match(expected["after"], actual.get("after") or {}, column_types):
            return False
    return True


def diff_entry_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if expected["gym"] is not None and expected["gym"] != actual["gym"]:
        return False
    if expected["table"] != actual["table"] or expected["op"] != actual["op"]:
        return False
    column_types = actual.get("column_types") or expected.get("column_types") or {}
    if expected["op"] in {"added", "removed"}:
        return rows_match(
            expected["item"].get("row") or {},
            actual["item"].get("row") or {},
            column_types,
            exact_strings=expected["op"] == "removed",
        )
    return changed_item_matches(expected["item"], actual["item"], column_types)


def entries_to_diff(entries: list[dict[str, Any]]) -> dict[str, Any]:
    diff = empty_diff()
    for entry in entries:
        gym = entry["gym"] or "_legacy"
        add_diff_item(diff, gym, entry["table"], entry["op"], entry["item"])
    return diff


def diff_has_changes(diff: dict[str, Any]) -> bool:
    return bool(iter_diff_entries(diff))


def volatile_fields_from_expected(expected_diff: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    meta = expected_diff.get(VOLATILE_META_KEY) if isinstance(expected_diff, dict) else None
    if not isinstance(meta, dict):
        return {}
    fields = meta.get("fields")
    if not isinstance(fields, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for gym, tables in fields.items():
        if not isinstance(gym, str) or not isinstance(tables, dict):
            continue
        for table, names in tables.items():
            if not isinstance(table, str) or not isinstance(names, list):
                continue
            clean = sorted({name for name in names if isinstance(name, str)})
            if clean:
                out.setdefault(gym, {})[table] = clean
    return out


def strip_item_fields(item: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    if not fields or not isinstance(item, dict):
        return item
    out = json.loads(json.dumps(item))
    for section in ("row", "pk", "before", "after"):
        row = out.get(section)
        if not isinstance(row, dict):
            continue
        stripped = {k: v for k, v in row.items() if k not in fields}
        if stripped:
            out[section] = stripped
        else:
            out.pop(section, None)
    return out


def canonicalize_diff_volatile_fields(diff: dict[str, Any], expected_diff: dict[str, Any]) -> dict[str, Any]:
    volatile = volatile_fields_from_expected(expected_diff)
    out = json.loads(json.dumps(diff))
    out.pop(VOLATILE_META_KEY, None)
    for gym, gym_body in list((out.get("gyms") or {}).items()):
        for table, ops in list(((gym_body or {}).get("tables") or {}).items()):
            fields = set((volatile.get(gym) or {}).get(table) or [])
            if not fields:
                continue
            for op in DIFF_OPS:
                ops[op] = [strip_item_fields(item, fields) for item in (ops.get(op) or [])]
    return out


def match_expected(
    actual_diff: dict[str, Any],
    expected_diff: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Returns state_score, matched_expectations, unauthorized_entries, unexpected_diff.

    NOTE: Strict (binary row-equality) scorer — preserved for backwards
    compatibility and for tools that need the legacy semantics. The
    production reward path now uses ``match_expected_graded`` below,
    which gives partial credit per-column so a single null/extra field
    on one row doesn't zero the entire entry. See
    ``match_expected_graded`` for the rationale.
    """
    actual_entries = iter_diff_entries(actual_diff)
    expected_entries = iter_diff_entries(expected_diff)
    matched: list[dict[str, Any]] = []
    total_matched = 0

    for exp in expected_entries:
        if any(diff_entry_matches(exp, act) for act in actual_entries):
            total_matched += 1
            matched.append(exp)

    score = (total_matched / len(expected_entries)) if expected_entries else 1.0

    unauthorized = [
        act for act in actual_entries
        if not any(diff_entry_matches(exp, act) for exp in expected_entries)
    ]
    return score, matched, unauthorized, entries_to_diff(unauthorized)


# ────────────────────────────────────────────────────────────────────
#  Graded reward (per-column partial credit)
# ────────────────────────────────────────────────────────────────────
#
# Why we introduced this:
# ----------------------
# The strict scorer above returns binary "row matches" / "row doesn't"
# per expected entry. In practice, a perfectly-on-task agent can fill
# 9 of 10 columns correctly and miss one (e.g. a stylistic ``description``
# the trainer typed but the prompt never required). Under strict scoring
# that single mismatch:
#   - zeroes the matched count for THAT row
#   - lands the same row in unauthorized_changes
#   - triples-counts the miss when the side_effect_gate then multiplies
#     the whole composite by 0
#
# For GRPO training this is catastrophic: most "near-miss" rollouts
# collapse to 0.0, the within-group reward variance collapses, the
# advantage is ~0, and there's no gradient. Across 50 runs/task, you
# need a continuous signal that rewards getting closer rather than
# only rewarding perfection.
#
# Graded scoring fixes this with two coordinated changes:
#
#  1. Per-row partial credit: for each expected row, the row score is
#     ``matched_columns / total_expected_columns`` against the
#     best-matching actual row of the same (gym, table, op). The
#     state score is the mean of those row scores.
#
#  2. Two-tier unauthorized:
#       - "Hard" unauthorized: the agent acted on a (table, op) the
#         trainer never expected → categorical failure → hard_gate=0
#         multiplies the composite to 0. Off-script behaviour stays
#         strictly punished — we want zero gradient for "the agent
#         deleted random rows."
#       - "Soft" unauthorized: same (table, op) as expected but column-
#         level mismatch → continuous penalty proportional to the soft
#         count. Same intent, wrong details — partial credit, not
#         categorical failure.
#
# Pass criterion (for benchmark reporting):
#     pass = total_graded >= PASS_THRESHOLD
# Committed at 1.0 — pass means literally perfect on the graded scale.
# Captured in ``reward.json`` so historical runs stay re-derivable if
# the threshold ever needs to move.

PASS_THRESHOLD: float = 1.0
SOFT_UNAUTHORIZED_PENALTY_COEF: float = 0.1

# ── LLM-judge configuration ─────────────────────────────────────────
# Bump JUDGE_PROMPT_VERSION whenever the prompt template, evidence
# shape, or response schema changes — every reward.json carries this
# tag so historical runs stay comparable (or explicitly mark themselves
# as "scored under a different prompt"). Treat as a semver-ish string:
# major bump on schema change, minor on prompt-text refinement.
JUDGE_PROMPT_VERSION: str = "v2.1-likert"

# Likert range the judge scores each rubric item on. 0-5 is the
# practical sweet spot — granular enough to capture partial work
# (4/5 = "did most of it"), coarse enough that judges don't agonize
# over 0.1 differences. Item is counted as "passed" when its score
# meets ``LIKERT_PASS_THRESHOLD``, which feeds the binary
# benchmark-style ``pass`` derivation for individual items. The
# overall rubric score is the mean(score)/LIKERT_MAX → [0, 1].
LIKERT_MAX: int = 5
LIKERT_PASS_THRESHOLD: int = 4

# ── Verifier composition (3 peer axes) ──────────────────────────────
# Each verifier type is a peer by default. If only one type is authored,
# it owns 100% of the score. If two are authored, each gets 50%; if all
# three are authored, each gets 1/3. Manifests can still override weights
# explicitly via ``[scoring.weights]``.
KNOWN_VERIFIER_AXES = ("state", "sql", "rubric")
DEFAULT_VERIFIER_WEIGHTS: dict[str, float] = {
    "state":  1.0,
    "sql":    1.0,
    "rubric": 1.0,
}


def _row_score(
    expected_row: dict[str, Any],
    actual_row: dict[str, Any],
    column_types: dict[str, str] | None = None,
    *,
    exact_strings: bool = False,
) -> float:
    """Partial-credit version of ``rows_match``.

    Returns the fraction of expected columns that matched in the actual
    row (in ``[0.0, 1.0]``). Same per-field comparator (`field_matches`)
    as strict — we just count the wins instead of short-circuiting on
    the first miss.
    """
    if not expected_row:
        return 1.0
    matched = 0
    for k, v in expected_row.items():
        if k in actual_row and field_matches(
            k, v, actual_row[k], column_types, exact_strings=exact_strings,
        ):
            matched += 1
    return matched / len(expected_row)


def _entry_row_score(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> float:
    """Per-column partial credit between two same-(gym, table, op)
    diff entries. For ``added``/``removed`` this is the row score; for
    ``changed`` we score the before+after halves and take the mean.
    """
    column_types = actual.get("column_types") or expected.get("column_types") or {}
    op = expected["op"]
    if op in ("added", "removed"):
        return _row_score(
            expected["item"].get("row") or {},
            actual["item"].get("row") or {},
            column_types,
            exact_strings=(op == "removed"),
        )
    # ``changed`` — average the pk/before/after partial credits. ``pk``
    # and ``before`` use strict semantics (you need the right row); only
    # ``after`` gets graded credit since that's the "new state" half.
    parts: list[float] = []
    if expected["item"].get("pk"):
        parts.append(
            _row_score(
                expected["item"]["pk"], actual["item"].get("pk") or {},
                column_types, exact_strings=True,
            )
        )
    if expected["item"].get("before") is not None:
        parts.append(
            _row_score(
                expected["item"]["before"], actual["item"].get("before") or {},
                column_types, exact_strings=True,
            )
        )
    if expected["item"].get("after") is not None:
        parts.append(
            _row_score(
                expected["item"]["after"], actual["item"].get("after") or {},
                column_types,
            )
        )
    return sum(parts) / len(parts) if parts else 0.0


def match_expected_graded(
    actual_diff: dict[str, Any],
    expected_diff: dict[str, Any],
) -> dict[str, Any]:
    """Graded scorer — see header comment for motivation.

    Returns a dict with:
      - state_score:        mean of per-row partial-credit scores in [0, 1]
      - matched:            expected entries that had a strict row-match
                            (kept for transparency / verifier_summary)
      - soft_unauthorized:  actual entries whose (table, op) appeared
                            in expected but whose row didn't strict-match
                            any expected row → continuous penalty
      - hard_unauthorized:  actual entries whose (table, op) was NEVER
                            in expected → categorical failure → gate=0
      - hard_gate:          0.0 if any hard_unauthorized, else 1.0
      - soft_penalty:       1 - α × (soft / total_actual); 1.0 when no
                            actual entries or no soft mismatches
      - unexpected_diff:    soft+hard rolled back into diff shape for
                            ``snapshots/unexpected.json`` consumers
    """
    actual_entries = iter_diff_entries(actual_diff)
    expected_entries = iter_diff_entries(expected_diff)

    # Build a quick (gym, table, op) → list[expected_entry] index so the
    # row-score lookup is O(actual × matching_expected) instead of
    # O(actual × all_expected). Cheap and clearer than a triple loop.
    expected_by_slot: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for e in expected_entries:
        key = (e["gym"] or "", e["table"], e["op"])
        expected_by_slot.setdefault(key, []).append(e)

    # ── state_score: mean of per-row partial credit ───────────────
    row_scores: list[float] = []
    matched: list[dict[str, Any]] = []
    for exp in expected_entries:
        candidates = expected_by_slot  # not needed for forward direction; use actual
        # Best-matching actual row of the same slot.
        slot = (exp["gym"] or "", exp["table"], exp["op"])
        actual_in_slot = [
            a for a in actual_entries
            if (a["gym"] or "") == slot[0] and a["table"] == slot[1] and a["op"] == slot[2]
        ]
        if not actual_in_slot:
            row_scores.append(0.0)
            continue
        best = max(_entry_row_score(exp, a) for a in actual_in_slot)
        row_scores.append(best)
        # Keep "matched" semantics aligned with strict scorer so
        # verifier_summary.matched_expectations stays a useful view of
        # "rows the agent reproduced exactly". Doesn't affect the score.
        if any(diff_entry_matches(exp, a) for a in actual_in_slot):
            matched.append(exp)
        _ = candidates  # silence linter; lookup index left for future fast-paths

    state_score = sum(row_scores) / len(row_scores) if row_scores else 1.0

    # ── Hard vs soft unauthorized split ───────────────────────────
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    for act in actual_entries:
        slot = (act["gym"] or "", act["table"], act["op"])
        if slot not in expected_by_slot:
            # Agent acted on a table+op the trainer never expected.
            hard.append(act)
            continue
        # Same slot was expected — was THIS specific row matched?
        if any(diff_entry_matches(e, act) for e in expected_by_slot[slot]):
            continue  # exact match — already counted toward state_score
        soft.append(act)

    hard_gate = 0.0 if hard else 1.0
    total_actual = max(1, len(actual_entries))
    soft_penalty = max(0.0, 1.0 - SOFT_UNAUTHORIZED_PENALTY_COEF * (len(soft) / total_actual))

    return {
        "state_score":       state_score,
        "matched":           matched,
        "soft_unauthorized": soft,
        "hard_unauthorized": hard,
        "hard_gate":         hard_gate,
        "soft_penalty":      soft_penalty,
        # Backwards-compat: keep a flat "unauthorized" + "unexpected_diff"
        # so consumers that read those fields don't break. ``unauthorized``
        # is the union of soft + hard, which matches the strict scorer's
        # set semantics.
        "unauthorized":      soft + hard,
        "unexpected_diff":   entries_to_diff(soft + hard),
    }


# ---------------------------------------------------------------------------
# SQL verifier execution
# ---------------------------------------------------------------------------
#
# Trainer-authored SQL assertions ("does this query return N rows?", "is
# this column equal to X?"). Stored on the task as
# ``task.sql_verifiers`` from the Step-2 wizard. Each entry carries:
#
#   {name, db_query, expected_value, comparison_type, target_gym_server}
#
# Each verifier is run against the post-agent gym state via the same
# ``query_state`` helper the diff comparator uses. The scalar in the
# first cell of the first returned row is compared to ``expected_value``
# under ``comparison_type``. Type-coercion strategy is comparator-driven
# — see ``_compare`` — so "5 > 4" works whether the DB returns int or
# string, but "abc > 3" fails loudly rather than silently lex-comparing.
#
# This module is gated by ``allowed_verifier_types`` containing ``"sql"``
# in the task manifest. When SQL is disabled (or no verifiers authored),
# the axis drops out of the composite score entirely — see ``main()``.


def _extract_scalar(rows: list[dict[str, Any]]) -> Any:
    """First cell of the first row. None when the result set is empty.

    Trainer convention: SQL verifier queries should return one scalar
    (use COUNT/MIN/MAX/SUM or ``LIMIT 1`` + a single column). When the
    query returns more, we silently take the first cell rather than
    raise — produces a comparable value even for "messy" queries.
    """
    if not rows or not isinstance(rows[0], dict) or not rows[0]:
        return None
    return next(iter(rows[0].values()))


def _try_numeric(a: Any, b: Any) -> tuple[float, float] | None:
    """Best-effort numeric coercion of both sides. Returns
    ``(a_num, b_num)`` or ``None`` if either side can't cleanly coerce.

    Tries ``int`` first (preserves precision for large primary keys),
    falls back to ``float`` (handles decimal expected values).

    Booleans are explicitly excluded — without this guard Python's
    ``float(True) == 1.0`` would let ``True == 1`` silently match on
    the numeric path. Whether bool-vs-int should compare equal is a
    judgement call; we handle that case separately via
    ``_BOOL_NUMERIC_LENIENT`` below.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    for caster in (int, float):
        try:
            return caster(a), caster(b)
        except (TypeError, ValueError):
            continue
    return None


# When True, booleans coerce to their int equivalents for numeric
# comparisons (``True → 1``, ``False → 0``). Matches the most common
# trainer intuition: ``is_active equals 1`` should pass when the DB
# returns Python ``True``. Strict mode (False) makes bools fail the
# numeric path entirely — only relevant if a task needs hard
# bool/int separation.
_BOOL_NUMERIC_LENIENT: bool = True


def _coerce_bool_for_numeric(v: Any) -> Any:
    """Map ``True/False → 1/0`` when lenient mode is on, else pass
    through unchanged so ``_try_numeric`` will skip it."""
    if _BOOL_NUMERIC_LENIENT and isinstance(v, bool):
        return int(v)
    return v


def _compare(actual: Any, expected: Any, op: str) -> tuple[bool, str | None]:
    """Compare ``actual`` (from DB) to ``expected`` (from verifier
    config) under ``op``. Returns ``(passed, error_or_None)``.

    Coercion strategy is comparator-driven so we never silently
    fall into a wrong-type comparison:

      - ``greater_than`` / ``greater_or_equal`` / ``less_than`` /
        ``less_or_equal``: both sides MUST coerce to numbers. Failure to
        coerce produces an error (verifier fails with a diagnostic
        message rather than a silent ``False``).
      - ``contains`` / ``not_contains``: both sides cast to ``str``;
        ``None`` becomes ``""`` so a null actual doesn't crash.
      - ``equals`` / ``not_equals``: try numeric coercion first
        (``"5" == 5`` should pass), then fall back to string equality
        (``"active" == "active"``). ``None`` is special-cased — only
        equal to ``None``, never to ``"null"`` or ``""``.
    """
    if op in ("greater_than", "greater_or_equal", "less_than", "less_or_equal"):
        nums = _try_numeric(
            _coerce_bool_for_numeric(actual),
            _coerce_bool_for_numeric(expected),
        )
        if nums is None:
            return False, (
                f"{op}: cannot coerce to number "
                f"(actual={actual!r}, expected={expected!r})"
            )
        a, e = nums
        if op == "greater_than":
            return a > e, None
        if op == "greater_or_equal":
            return a >= e, None
        if op == "less_than":
            return a < e, None
        return a <= e, None  # less_or_equal

    if op in ("contains", "not_contains"):
        a_str = str(actual) if actual is not None else ""
        e_str = str(expected) if expected is not None else ""
        result = e_str in a_str
        return ((result) if op == "contains" else (not result)), None

    if op in ("equals", "not_equals"):
        if actual is None and expected is None:
            result = True
        elif actual is None or expected is None:
            result = False
        else:
            nums = _try_numeric(
                _coerce_bool_for_numeric(actual),
                _coerce_bool_for_numeric(expected),
            )
            if nums is not None:
                result = nums[0] == nums[1]
            else:
                result = str(actual) == str(expected)
        return ((result) if op == "equals" else (not result)), None

    return False, f"unknown comparator: {op}"


def _resolve_sql_target_gym(
    verifier: dict[str, Any],
    task_cfg: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Determine which gym a SQL verifier runs against.

    Priority:
      1. Explicit ``target_gym_server`` on the verifier
      2. Auto-resolve to the only gym when the task has exactly one
      3. Fail loudly when ambiguous

    Returns ``(gym_name, error_or_None)`` — error is non-None on fail.
    """
    explicit = (verifier.get("target_gym_server") or "").strip()
    if explicit:
        return explicit, None

    # Probe the task's gym list from a few well-known manifest paths.
    # Different task templates put the gym list in different places;
    # we accept any of them so the auto-resolve works broadly.
    gyms: list[str] = []
    for path in (
        ("environment", "servers"),
        ("environment", "gyms"),
        ("gyms",),
    ):
        node: Any = task_cfg
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, list):
            for entry in node:
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("mcp_server_name") or entry.get("gym_name")
                    if name and name not in gyms:
                        gyms.append(name)
                elif isinstance(entry, str):
                    if entry not in gyms:
                        gyms.append(entry)
        if gyms:
            break

    if len(gyms) == 1:
        return gyms[0], None
    if not gyms:
        return None, "target_gym_server is required (task has no resolvable gym list)"
    return None, (
        f"target_gym_server is required when task uses multiple gyms "
        f"({', '.join(gyms)})"
    )


def run_sql_verifiers(
    task_cfg: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    """Execute every SQL verifier authored on the task; return
    ``(score, per_verifier_results)``.

    ``score`` is the simple pass-rate (``passed / total``) in ``[0, 1]``.
    No partial credit per-verifier — comparators are inherently binary.
    Continuous signal comes from the pass-rate across the set.

    Verifier list is read from ``manifest.sql_verifiers`` first (the
    canonical location, JSON-friendly), with a fallback to
    ``task_cfg.sql_verifiers`` for any legacy paths that stash them
    under task.toml. When no verifiers are authored, returns
    ``(1.0, [])`` (vacuously passes). Caller is responsible for
    deciding whether to include SQL in the composite — see the
    ``allowed_verifier_types`` gate in ``main()``.
    """
    verifiers: list[Any] = []
    if isinstance(manifest, dict):
        m_verifiers = manifest.get("sql_verifiers")
        if isinstance(m_verifiers, list):
            verifiers = m_verifiers
    if not verifiers:
        t_verifiers = task_cfg.get("sql_verifiers") if isinstance(task_cfg, dict) else None
        if isinstance(t_verifiers, list):
            verifiers = t_verifiers
    if not verifiers:
        return 1.0, []

    results: list[dict[str, Any]] = []
    passed_count = 0
    for v in verifiers:
        if not isinstance(v, dict):
            continue
        name = v.get("name") or "<unnamed>"
        query = (v.get("db_query") or "").strip()
        expected = v.get("expected_value")
        comparator = (v.get("comparison_type") or "equals").strip().lower()

        if not query:
            results.append({
                "name":       name,
                "passed":     False,
                "actual":     None,
                "expected":   expected,
                "comparison": comparator,
                "gym":        None,
                "error":      "db_query is empty",
            })
            continue

        gym, gym_err = _resolve_sql_target_gym(v, task_cfg)
        if gym_err is not None:
            results.append({
                "name":       name,
                "passed":     False,
                "actual":     None,
                "expected":   expected,
                "comparison": comparator,
                "gym":        None,
                "error":      gym_err,
            })
            continue

        try:
            rows = query_state(gym, query)
            actual = _extract_scalar(rows)
        except Exception as exc:  # noqa: BLE001 — verifier shouldn't crash the run
            results.append({
                "name":       name,
                "passed":     False,
                "actual":     None,
                "expected":   expected,
                "comparison": comparator,
                "gym":        gym,
                "error":      f"query failed: {exc}",
            })
            continue

        verdict, cmp_err = _compare(actual, expected, comparator)
        results.append({
            "name":       name,
            "passed":     bool(verdict),
            "actual":     actual,
            "expected":   expected,
            "comparison": comparator,
            "gym":        gym,
            "error":      cmp_err,
        })
        if verdict:
            passed_count += 1

    score = passed_count / len(verifiers) if verifiers else 1.0
    return score, results


# ---------------------------------------------------------------------------
# Trajectory evidence
# ---------------------------------------------------------------------------

def _call_succeeded(ter: Any) -> bool:
    """Whether the gym accepted a call. Consumers read a per-call ``ok`` that
    nothing ever wrote, so every call read as accepted. Optimistic: only an
    explicit error signal marks a call failed."""
    if not isinstance(ter, dict):
        return True
    if ter.get("success") is False:
        return False
    result = ter.get("result")
    if isinstance(result, dict):
        if result.get("isError"):
            return False
        status = result.get("status_code")
        if isinstance(status, int) and status >= 400:
            return False
    return True


def load_agent_trace(path: Path) -> list[dict]:
    """Load an agent's trace into the flat call list the scorer expects.

    Supports two formats:
      * **ATIF-v1.x** — `{steps: [{tool_calls, observation: {results}}, ...]}`.
        Joins each tool_call with the matching observation result by
        `source_call_id` and reconstructs `tool_execution_results`.
      * **flat list** — `[{name, arguments, tool_execution_results}, ...]`
        (legacy / simple shape).

    Strips the `mcp__<server>__` prefix Claude Code prepends so the
    name comparison against golden_trajectory.json's bare tool name works.
    """
    if not path.exists():
        return []
    data = load_json(path)

    def _strip_mcp_prefix(name: str) -> str:
        if isinstance(name, str) and name.startswith("mcp__"):
            parts = name.split("__", 2)
            if len(parts) == 3:
                return parts[2]
        return name

    if isinstance(data, dict) and "steps" in data:
        calls = []
        for s in data["steps"]:
            # Index observation results by source_call_id for fast lookup.
            results = ((s.get("observation") or {}).get("results") or [])
            obs_by_id: dict[str, dict] = {}
            for r in results:
                if isinstance(r, dict) and r.get("source_call_id"):
                    obs_by_id[r["source_call_id"]] = r
            tcs = s.get("tool_calls") or []
            for idx, tc in enumerate(tcs):
                tcid = tc.get("tool_call_id")
                obs = obs_by_id.get(tcid)
                # ``source_call_id`` is optional in ATIF and most emitters omit
                # it, so keying only on it dropped every result. Fall back to
                # position when nothing in the step is keyed.
                if obs is None and not obs_by_id and len(results) == len(tcs):
                    obs = results[idx]
                obs = obs if isinstance(obs, dict) else {}
                # ATIF: observation.content is a string (often stringified JSON).
                content = obs.get("content")
                payload = content
                if isinstance(content, str):
                    try:
                        payload = json.loads(content)
                    except (ValueError, TypeError):
                        payload = content
                # Some authors stash status_code / is_error in step.extra.
                extra = (s.get("extra") or {})
                ter = tc.get("result") or {
                    "success": extra.get("success", True),
                    "result": {
                        "status_code": extra.get("status_code"),
                        "isError": extra.get("is_error", False),
                        "payload": payload,
                    },
                }
                calls.append({
                    "name": _strip_mcp_prefix(
                        tc.get("function_name") or tc.get("name") or ""
                    ),
                    "arguments": tc.get("arguments") or {},
                    "tool_execution_results": ter,
                    "ok": _call_succeeded(ter),
                })
        return calls
    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict) and "name" in c:
                c["name"] = _strip_mcp_prefix(c["name"])
            # Same ``ok`` contract as the ATIF branch.
            if isinstance(c, dict) and "ok" not in c:
                c["ok"] = _call_succeeded(c.get("tool_execution_results"))
        return data
    return []


# ---------------------------------------------------------------------------
# Rubric (hierarchical LLM judge)
# ---------------------------------------------------------------------------

# Char budget for the assembled judge evidence block. The old 24k default only
# fit ~10-15 steps of an indented-JSON trajectory, so any longer run was
# truncated mid-trajectory and the judge scored "no visible evidence" for
# everything past the cutoff. Default is now 120k and, more importantly, the
# per-batch/global ``manifest.rubric.evidence.max_chars`` overrides it.
_EVIDENCE_TRUNCATE_CHARS = int(os.environ.get("RUBRIC_EVIDENCE_CHARS", "120000"))

# Keys that are pure noise for a rubric judge and safe to drop from the
# trajectory JSON handed to it. Dropping them (plus null/empty values, plus
# compact serialization) roughly halves the evidence size WITHOUT removing any
# decision-relevant signal: tool names, arguments, success/error and result
# payloads are all preserved. ``captures`` is an internal wizard mapping;
# ``resolved_arguments`` duplicates ``arguments``; ``executed_at`` is a
# per-call timestamp the rubric never grades.
_EVIDENCE_TRAJECTORY_DROP_KEYS = frozenset(
    {"captures", "resolved_arguments", "executed_at"}
)


def _slim_evidence_value(value: Any) -> Any:
    """Recursively drop safe-to-drop keys and null/empty leaves.

    Conservative on purpose — it only removes structural noise and empty
    values, never domain data (a tool's arguments or its result payload).
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in _EVIDENCE_TRAJECTORY_DROP_KEYS:
                continue
            sv = _slim_evidence_value(v)
            # Preserve ``False`` / ``0`` (meaningful, e.g. success=False), only
            # strip genuinely empty leaves.
            if sv is None or sv == [] or sv == {} or sv == "":
                continue
            out[k] = sv
        return out
    if isinstance(value, list):
        return [_slim_evidence_value(v) for v in value]
    return value


def _slim_trajectory_for_evidence(trajectory: Any) -> Any:
    """Slim each trajectory step for the judge's evidence block (safe drops)."""
    if not isinstance(trajectory, list):
        return trajectory
    return [_slim_evidence_value(step) for step in trajectory]


def _build_evidence_text(manifest: dict[str, Any], evidence: dict[str, Any]) -> str:
    cfg = (manifest.get("rubric") or {}).get("evidence") or {}
    # Per-batch/global override (stamped by harbor_composite.default_manifest);
    # falls back to the env/default cap when the key is absent (legacy tasks).
    try:
        max_chars = int(cfg.get("max_chars") or 0)
    except (TypeError, ValueError):
        max_chars = 0
    if max_chars <= 0:
        max_chars = _EVIDENCE_TRUNCATE_CHARS
    parts: list[str] = []
    if cfg.get("include_db_diff", True):
        parts.append(
            "### DB diff (after-agent minus after-reset)\n"
            + json.dumps(evidence.get("diff") or {}, indent=2, default=str)
        )
    unexpected = evidence.get("unexpected") or {}
    if cfg.get("include_db_diff", True) and diff_has_changes(unexpected):
        parts.append(
            "### Unauthorized / side-effect changes\n"
            + json.dumps(unexpected, indent=2, default=str)
        )
    # Final answer and transcript go BEFORE the unbounded trajectory; the final
    # message used to be last, so truncation cut it first.
    if cfg.get("include_final_output", True) and evidence.get("final_output"):
        parts.append("### Final agent message\n" + str(evidence["final_output"]))
    if cfg.get("include_assistant_messages", True) and evidence.get("agent_messages"):
        parts.append(
            "### Assistant messages (full conversation, most recent last)\n"
            + str(evidence["agent_messages"])
        )
    if cfg.get("include_trajectory", True):
        # Slim (safe drops only) + compact serialization: the indented dump was
        # ~40% whitespace, so this fits far more steps under the same char cap
        # while keeping every tool name / argument / result the judge needs.
        slim_traj = _slim_trajectory_for_evidence(evidence.get("trajectory") or [])
        parts.append(
            "### Agent tool-call trajectory\n"
            + json.dumps(slim_traj, separators=(",", ":"), default=str)
        )
    text = "\n\n".join(parts) if parts else "(no evidence provided)"
    if len(text) > max_chars:
        # Head+tail: opening calls are the least gradeable, closing ones carry
        # the findings.
        head = max_chars // 3
        tail = max_chars - head
        text = (
            text[:head]
            + f"\n\n[… {len(text) - max_chars} chars elided from the middle …]\n\n"
            + text[-tail:]
        )
    return text


def _call_judge(
    model: str,
    api_key_env: str,
    temperature: float,
    max_tokens: int,
    user_prompt: str,
) -> str:
    """Invoke the configured LLM via LiteLLM. Returns raw message text."""
    try:
        import litellm  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "litellm not installed in this environment. Add it to "
            "environment/mcp/proxy/requirements.txt."
        ) from exc
    # Allow provider-specific params we don't care about to be silently dropped.
    litellm.drop_params = True

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
        # Not every provider supports JSON mode, but LiteLLM will drop it
        # when unsupported thanks to drop_params=True.
        "response_format": {"type": "json_object"},
        "api_key": os.environ.get(api_key_env, ""),
    }
    # Newer Anthropic models (claude-opus-4-7+) deprecated the temperature
    # parameter and return HTTP 400 if it's present. Only attach when the
    # caller explicitly asked for a non-default value.
    if temperature is not None and float(temperature) > 0.0:
        kwargs["temperature"] = float(temperature)

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = litellm.completion(**kwargs)
            break
        except Exception as exc:  # noqa: BLE001
            # One-shot retry without temperature if the provider rejected it
            # (covers the case where temperature defaulted in upstream).
            msg = str(exc).lower()
            if "temperature" in msg and "temperature" in kwargs:
                kwargs.pop("temperature", None)
                last_exc = exc
                continue
            last_exc = exc
            transient = any(
                marker in msg
                for marker in ("internal server error", "overloaded", "rate limit", "timeout")
            )
            if attempt < 2 and transient:
                time.sleep(2 ** attempt)
                continue
            raise
    else:  # pragma: no cover
        assert last_exc is not None
        raise last_exc
    return resp.choices[0].message.content or ""


# Cap on how much of the judge's raw response we inline into structured
# output (verifier_summary.json ``rubric.raw``). The FULL response is always
# persisted verbatim to the ``judge_raw.txt`` artifact; this only bounds the
# echoed copy so a runaway response can't bloat the summary.
_JUDGE_RAW_TRUNCATE = 8192


def _persist_judge_raw(raw: str) -> None:
    """Best-effort: persist the judge's raw (unparseable) response to a debug
    artifact so failures are diagnosable. Never raises from the hot path."""
    if not raw:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "judge_raw.txt").write_text(raw)
    except Exception:  # noqa: BLE001  # pragma: no cover
        pass


# JSON literals that are legitimately unquoted in a value position — the
# bare-string repair below must never wrap these into strings.
_JSON_BARE_LITERALS = {"true", "false", "null"}


def _decode_first_or_slice(text: str) -> Any:
    """Decode only the FIRST complete top-level JSON object. This tolerates a
    trailing "Extra data" suffix (prose after the JSON, a second object, a
    stray code fence) that plain ``json.loads`` rejects outright — a common
    judge failure mode that used to throw away an otherwise-scoreable reply.
    Falls back to the widest brace slice (handles an object that isn't at the
    very start even after trimming, e.g. nested leading prose)."""
    try:
        parsed, _end = json.JSONDecoder().raw_decode(text)
        return parsed
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _quote_bare_string_values(text: str) -> str:
    """Best-effort repair for the LLM failure mode where a value that should be
    a quoted string is emitted as a BARE token — ``"confidence":low`` or
    ``"verdict":PASS`` (a "string without quotes"). Quotes any bare word sitting
    in a value position (``"<key>": <word>``) except the JSON literals
    true/false/null; numbers never match (the token must start with a letter).

    Used only as a FALLBACK after a strict parse has already failed, so on the
    happy path valid JSON is never touched (a quoted value starts with ``"`` and
    so is skipped). The worst case on already-broken input is that the repair
    still doesn't yield valid JSON and we fail closed — exactly as before."""

    def _wrap(m: "re.Match[str]") -> str:
        prefix, word = m.group(1), m.group(2)
        if word.lower() in _JSON_BARE_LITERALS:
            return m.group(0)
        return f'{prefix}"{word}"'

    return re.sub(r'("[^"]+"\s*:\s*)([A-Za-z][\w-]*)\b', _wrap, text)


def parse_judge_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    # Drop any leading prose so the object starts at the first brace.
    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    # LLMs emit the confidence enum unquoted ("confidence":low) under the
    # "low"|"med"|"high" prompt notation — invalid JSON. Quote it back. This is
    # surgical (matches only the known "confidence":<enum> shape, so a free-text
    # ``reason`` value can't be corrupted) and behavior-preserving (only the
    # JSON becomes parseable — the judge's scores/reasons are unchanged), so it
    # runs on every parse, ahead of the strict decode.
    text = re.sub(
        r'("confidence"\s*:\s*)(low|med|high|unknown)\b', r'\1"\2"', text
    )
    try:
        parsed = _decode_first_or_slice(text)
    except json.JSONDecodeError:
        # General fallback: any OTHER bare (unquoted) string value the judge
        # emitted on some key we don't special-case (e.g. ``"verdict":PASS``).
        # Only runs once the strict decode has already failed, so valid JSON is
        # never reshaped by it; if the repair changes nothing, re-raise.
        repaired = _quote_bare_string_values(text)
        if repaired == text:
            raise
        parsed = _decode_first_or_slice(repaired)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("judge response was not a JSON object", text, 0)
    return parsed


def _resolve_judge_fallback(judge: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (fallback_model, fallback_api_key_env) for a judge config.

    Prefers explicit ``fallback_model`` / ``fallback_api_key_env`` metadata
    stamped at dispatch time. Old snapshots without those fields fall back to
    legacy env vars (``HR_AUDIT_JUDGE_MODEL`` / ``OPENAI_MODEL``).
    """
    fb_model = judge.get("fallback_model")
    fb_env = judge.get("fallback_api_key_env")
    if fb_model and fb_env:
        return str(fb_model), str(fb_env)
    legacy = os.environ.get("HR_AUDIT_JUDGE_MODEL") or os.environ.get("OPENAI_MODEL")
    if legacy:
        return legacy, "OPENAI_API_KEY"
    return None, None


def _call_judge_with_fallback(
    model: str,
    api_key_env: str,
    temperature: float,
    max_tokens: int,
    user_prompt: str,
    *,
    judge: dict[str, Any] | None = None,
) -> str:
    """Call the configured judge; on failure, retry once on a fallback model.

    Modeled on the ``score_rubric`` Likert fallback block: when the primary
    judge call raises, retry once with explicit ``fallback_model`` metadata
    (or legacy env vars for old snapshots) — but ONLY when that fallback is
    configured, differs from the primary, and the key is set. Otherwise
    re-raise the primary error (caller fails the item closed).

    This is the **engine path only** — the Likert ``score_rubric`` keeps its
    own inline fallback block unchanged.
    """
    try:
        return _call_judge(model, api_key_env, temperature, max_tokens, user_prompt)
    except Exception:  # noqa: BLE001 — try a fallback before giving up
        fallback_model, fallback_env = _resolve_judge_fallback(judge or {})
        if (
            fallback_model
            and fallback_model != model
            and fallback_env
            and os.environ.get(fallback_env, "")
        ):
            return _call_judge(
                fallback_model, fallback_env, temperature, max_tokens, user_prompt
            )
        raise


def score_rubric(
    manifest: dict[str, Any],
    task_cfg: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    rubric_path = TASK_DIR / manifest["rubric"]["file"]
    if not rubric_path.exists():
        return {"score": 0.0, "breakdown": {}, "items": [], "error": "rubric file not found"}
    rubric = tomllib.loads(rubric_path.read_text())

    judge = (task_cfg.get("metadata") or {}).get("verifier_judge") or {}
    model = resolve_env_ref(judge.get("model"))
    api_key_env = resolve_env_ref(judge.get("api_key_env"))
    temperature = float(judge.get("temperature", 0.0))
    max_tokens = int(judge.get("max_tokens", 2048))
    if not model or not api_key_env:
        return {"score": 0.0, "breakdown": {}, "items": [], "error": "verifier_judge not configured in task.toml"}
    if not os.environ.get(api_key_env, ""):
        return {"score": 0.0, "breakdown": {}, "items": [], "error": f"env var {api_key_env} not set"}

    # Flatten items into (category, item) pairs so we can ask the judge once.
    all_items: list[tuple[str, dict[str, Any]]] = []
    for cat in rubric.get("criteria", []):
        for item in cat.get("items") or []:
            all_items.append((cat["category"], item))
    if not all_items:
        return {"score": 0.0, "breakdown": {}, "items": [], "error": None}

    # ── Position-bias mitigation: shuffle the item ordering with a
    # per-run seed. Deterministic for re-evaluations (so the same run
    # always sees the same prompt) but varies across runs of the same
    # task (so the position bias averages out at the dataset level).
    # The seed is keyed on the actual diff — it changes when the agent's
    # behaviour changes, which is exactly the cadence we want.
    diff_for_seed = evidence.get("diff") or {}
    seed_hash = hashlib.sha256(
        json.dumps(diff_for_seed, sort_keys=True, default=str).encode()
    ).hexdigest()
    shuffled_items = list(all_items)
    random.Random(seed_hash).shuffle(shuffled_items)

    preamble = (rubric.get("system") or {}).get("preamble", "").strip()
    evidence_text = _build_evidence_text(manifest, evidence)
    items_listing = "\n".join(
        f"  - id: {it['id']}\n    question: {it['question']}"
        for _, it in shuffled_items
    )

    # ── Likert 0–5 prompt (v2.0). Richer than binary 0/1: judges can
    # express "did most of what the question asked" as 4, "did all of
    # it" as 5, "missed substantially" as 1–2. Threshold of ≥4 marks
    # the item as "passed" in the breakdown; the continuous score is
    # the per-item rating divided by ``LIKERT_MAX``. We also ask for a
    # ``confidence`` field so downstream consumers can flag low-
    # confidence items without re-prompting.
    user_prompt = (
        (preamble + "\n\n" if preamble else "")
        + "## Evidence\n"
        + evidence_text
        + "\n\n## Questions\n"
        + items_listing
        + "\n\n## Scoring rubric\n"
        + f"For each question, return an integer score from 0 to {LIKERT_MAX}:\n"
        + f"  {LIKERT_MAX}  — fully and unambiguously met\n"
        + f"  {LIKERT_MAX - 1}  — substantially met (≥80% of what the question asks)\n"
        + "  3  — partially met (some key sub-conditions satisfied)\n"
        + "  2  — barely met (one minor aspect addressed)\n"
        + "  1  — attempted but missed\n"
        + "  0  — not addressed or done wrong\n\n"
        + "## Output format\n"
        + f"Respond with a single JSON object that has exactly one key per "
        + f"question id ({len(shuffled_items)} total). Each value is "
        + '{"score": <0-' + str(LIKERT_MAX) + '>, "confidence": "low"|"med"|"high", "reason": "<short>"}. '
        + "Return JSON only — no preamble, no code fences."
    )

    try:
        raw = _call_judge(model, api_key_env, temperature, max_tokens, user_prompt)
    except Exception as exc:  # noqa: BLE001
        fallback_model, fallback_env = _resolve_judge_fallback(judge)
        if (
            fallback_model
            and fallback_model != model
            and fallback_env
            and os.environ.get(fallback_env, "")
        ):
            try:
                raw = _call_judge(
                    fallback_model,
                    fallback_env,
                    temperature,
                    max_tokens,
                    user_prompt,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                return {
                    "score": 0.0,
                    "breakdown": {},
                    "items": [],
                    "raw": None,
                    "error": (
                        f"primary judge call failed: {exc}; "
                        f"fallback judge call failed: {fallback_exc}"
                    ),
                }
        else:
            return {"score": 0.0, "breakdown": {}, "items": [], "raw": None, "error": f"judge call failed: {exc}"}

    try:
        parsed = parse_judge_json(raw)
    except json.JSONDecodeError:
        # ── Retry ONCE with a JSON-only reminder ─────────────────────────
        # Judges intermittently wrap the JSON in prose or refuse outright.
        # A single targeted retry recovers most of these before we fail
        # closed — and when it still fails we keep the raw response (in the
        # returned ``raw`` field + a ``judge_raw.txt`` artifact) instead of
        # silently discarding it, so the failure is diagnosable rather than
        # surfacing as a misleading 0.00 score.
        retry_prompt = user_prompt + (
            "\n\n## IMPORTANT — OUTPUT FORMAT\n"
            "Your previous reply was not valid JSON. Respond with ONLY the "
            "JSON object described above — no prose, no markdown, no code "
            "fences, and nothing after the closing brace."
        )
        raw_retry = ""
        try:
            raw_retry = _call_judge(model, api_key_env, temperature, max_tokens, retry_prompt)
        except Exception:  # noqa: BLE001
            raw_retry = ""
        try:
            parsed = parse_judge_json(raw_retry)
        except json.JSONDecodeError as retry_exc:
            combined = "\n\n----- RETRY -----\n\n".join(p for p in (raw, raw_retry) if p)
            _persist_judge_raw(combined)
            return {
                "score": 0.0,
                "breakdown": {},
                "items": [],
                "error": f"judge returned invalid JSON (after one retry): {retry_exc}",
                "raw": combined[:_JUDGE_RAW_TRUNCATE],
            }

    # ── Tally per category + per item ────────────────────────────────
    # Iterate over the ORIGINAL (unshuffled) item list so the output
    # ordering (saved to verifier_summary.json) stays stable across
    # runs — the shuffle only affects what the judge sees in the
    # prompt, not what gets persisted.
    by_category: dict[str, list[float]] = {}
    item_details: list[dict[str, Any]] = []
    for cat_name, item in all_items:
        entry = parsed.get(item["id"])
        if isinstance(entry, dict):
            try:
                raw_score = float(entry.get("score", 0))
            except (TypeError, ValueError):
                raw_score = 0.0
            reason = str(entry.get("reason", ""))
            confidence = str(entry.get("confidence", "")).lower()
            if confidence not in ("low", "med", "high"):
                confidence = "unknown"
        else:
            raw_score, reason, confidence = 0.0, "", "unknown"

        # Likert 0..LIKERT_MAX clamp + normalise to 0..1. Tolerant of
        # older judges that still emit binary 0/1: those land at 0.0
        # and 0.2 under the new scale; trainers re-running an old
        # rubric file should bump JUDGE_PROMPT_VERSION or update the
        # rubric questions so the judge knows to use the new scale.
        clamped = max(0.0, min(float(LIKERT_MAX), raw_score))
        normalized = clamped / float(LIKERT_MAX)
        passed = clamped >= LIKERT_PASS_THRESHOLD
        by_category.setdefault(cat_name, []).append(normalized)
        item_details.append({
            "id":         item["id"],
            "category":   cat_name,
            # ``score`` stays in [0, 1] so downstream consumers
            # (verifier_summary aggregators, frontend chart) don't have
            # to know about the Likert change — the contract is
            # unchanged. ``score_raw`` exposes the Likert integer for
            # debugging / dashboards that want the original scale.
            "score":      round(normalized, 4),
            "score_raw":  clamped,
            "passed":     passed,
            "confidence": confidence,
            "reason":     reason,
        })

    breakdown: dict[str, float] = {}
    total_weight = 0.0
    weighted_sum = 0.0
    for cat in rubric.get("criteria", []):
        cw = float(cat.get("weight") or 0.0)
        total_weight += cw
        scores = by_category.get(cat["category"], [])
        cat_score = (sum(scores) / len(scores)) if scores else 0.0
        breakdown[cat["category"]] = round(cat_score, 4)
        weighted_sum += cw * cat_score
    # ``breakdown`` stays per-category (display-only) either way. In flat
    # mode the overall score pools every individual item's continuous
    # [0,1] score (partial credit) instead of averaging category-by-category
    # then weighting. It does NOT collapse to the item's own PASS/FAIL badge
    # (``LIKERT_PASS_THRESHOLD``-gated) — that stays a stricter, separate
    # per-item concept used for the Rubrics breakdown UI.
    flat_mode = bool((manifest.get("scoring") or {}).get("flat_verifier_scoring", False))
    if flat_mode:
        overall = (sum(it["score"] for it in item_details) / len(item_details)) if item_details else 0.0
    else:
        overall = (weighted_sum / total_weight) if total_weight else 0.0
    return {
        "score":          round(overall, 4),
        "breakdown":      breakdown,
        "items":          item_details,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "likert_max":     LIKERT_MAX,
        "error":          None,
    }


# ---------------------------------------------------------------------------
# benchmark_runner rubric_check judge (in-sandbox, target-aware, atomic PASS/FAIL)
# ---------------------------------------------------------------------------
#
# The ``rubric_check`` verifier of the benchmark_runner engine below, enabled
# when the batch allowlist contains ``agentic_llm_as_judge``. Instead of one
# judge call
# scoring every item on a 0–5 scale, the judge is asked ONE atomic yes/no
# rubric at a time, against the *target-selected* slice of the agent's
# behaviour:
#
#     target == "trace"         → the tool-call sequence [{name, args}, …]
#     target == "final_answer"  → the agent's final text answer (default)
#
# Each call returns ``{"verdict": "PASS"|"FAIL", "motivation": …}``, fail-closed
# (anything that is not an explicit PASS resolves to FAIL). Per-category
# pass-rate × weight → overall ∈ [0, 1]. Ported from ``benchmark_runner.py``'s
# ``_execute_rubric_check_verifier`` / ``_judge_rubric`` / ``_parse_rubric_verdict``,
# re-homed to read evidence off the in-sandbox trajectory + final message and to
# call the existing LiteLLM ``_call_judge`` instead of a live agent's LLM client.

def _step_message_text(msg: Any) -> str:
    """Normalise an ATIF step ``message`` (str | list of parts | object) to text.

    Mirrors the run-explorer's ``_stepMessageText`` and W5's port.
    """
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        parts: list[str] = []
        for p in msg:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
        return "\n".join(p for p in parts if p)
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return _step_message_text(content)
        if isinstance(msg.get("text"), str):
            return msg["text"]
    return ""


def _finish_action_message(step: dict[str, Any]) -> str:
    """The final answer carried by an agent ``finish`` action, if present.

    OpenHands (and other harnesses) end a run with a ``finish`` tool call whose
    ``arguments.message`` holds the agent's actual final answer — while the
    step's own ``message`` is a generic narration (e.g. "All done! What's next
    on the agenda?"). Reading the step message alone would mask the answer, so
    ``_extract_final_output`` prefers this. Returns "" when the step has no
    finish action (or no message on it).
    """
    for tc in step.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        name = (
            tc.get("function_name")
            or tc.get("name")
            or (tc.get("function") or {}).get("name")
            or ""
        )
        if str(name).lower() != "finish":
            continue
        args = tc.get("arguments")
        if args is None:
            args = (tc.get("function") or {}).get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        if isinstance(args, dict):
            for key in ("message", "final_thought", "thought", "content", "answer"):
                msg = args.get(key)
                if isinstance(msg, str) and msg.strip():
                    return msg
    return ""


def _extract_final_output(path: Path) -> str:
    """The agent's final text answer — the last assistant message in the trace.

    Reads the RAW trajectory JSON at ``path`` (the same file
    ``manifest.trajectory.agent_trace_file`` points ``load_agent_trace`` at).
    Prefers a ``finish`` action's message (the real answer) over the step's own
    ``message`` (often a generic narration). Only the ATIF ``{steps}`` shape
    carries assistant messages; a flat tool-call list (or an absent / unreadable
    file) yields an empty string.
    """
    if not path.exists():
        return ""
    try:
        data = load_json(path)
    except (ValueError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    steps = data.get("steps")
    if not isinstance(steps, list):
        return ""
    last = ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        src = step.get("source") or step.get("role")
        if src in ("agent", "assistant"):
            text = _finish_action_message(step) or _step_message_text(step.get("message"))
            if text and text.strip():
                last = text
    return last


# Bound on the assistant-transcript evidence handed to the rubric judge. The
# transcript is every natural-language message the agent emitted (not just the
# trailing one), so a value the model reported mid-conversation — before a
# closing pleasantry like "All done!" — is still judged. Both knobs keep the
# judge prompt bounded no matter how long the run was: each message is clipped
# to ``_AGENT_TRANSCRIPT_TURN_MAX_CHARS`` (so one giant command dump can't crowd
# out the rest) and the joined transcript is capped at ``_AGENT_TRANSCRIPT_MAX_CHARS``
# tail-first. Tool observations are NEVER included here — they live in the
# separate trajectory section.
_AGENT_TRANSCRIPT_MAX_CHARS = int(os.environ.get("RUBRIC_ASSISTANT_CHARS", "12000"))
_AGENT_TRANSCRIPT_TURN_MAX_CHARS = int(os.environ.get("RUBRIC_ASSISTANT_TURN_CHARS", "4000"))


def _clip_turn(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "… [message truncated]"


def _extract_agent_messages(path: Path) -> str:
    """Every natural-language agent message, chronological and length-bounded.

    ``_extract_final_output`` returns only the LAST assistant message, which
    misses a value the model stated mid-conversation before a trailing
    pleasantry (e.g. a "Staff headcount: 13" report followed by "All done!").
    Rubric items whose intent is "at any point in the conversation" need the
    full spoken transcript, so this collects the text of every agent step.

    To keep the judge prompt bounded regardless of run length, each message is
    clipped to ``_AGENT_TRANSCRIPT_TURN_MAX_CHARS`` and the joined transcript is
    kept within ``_AGENT_TRANSCRIPT_MAX_CHARS`` tail-first (a final report or
    summary is almost always near the end). Tool observations are never mixed
    in. Returns "" for a flat / absent / unreadable trace, exactly like
    ``_extract_final_output``.
    """
    if not path.exists():
        return ""
    try:
        data = load_json(path)
    except (ValueError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    steps = data.get("steps")
    if not isinstance(steps, list):
        return ""
    messages: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if (step.get("source") or step.get("role")) in ("agent", "assistant"):
            text = _finish_action_message(step) or _step_message_text(step.get("message"))
            if text and text.strip():
                messages.append(_clip_turn(text, _AGENT_TRANSCRIPT_TURN_MAX_CHARS))
    if not messages:
        return ""
    # Tail-biased budget: keep the most recent messages within the char cap,
    # but always keep at least the final message.
    kept: list[str] = []
    total = 0
    dropped = False
    for m in reversed(messages):
        add = len(m) + 2  # account for the "\n\n" separator
        if kept and total + add > _AGENT_TRANSCRIPT_MAX_CHARS:
            dropped = True
            break
        kept.append(m)
        total += add
    kept.reverse()
    transcript = "\n\n".join(kept)
    if dropped:
        transcript = (
            "[… earlier assistant messages omitted to bound length …]\n\n" + transcript
        )
    return transcript


# ---------------------------------------------------------------------------
# benchmark_runner verifier engine — VENDORED VERBATIM + sandbox adapters
# ---------------------------------------------------------------------------
#
# The ``VerifierConfig`` dataclass + ``VerifierEngine`` class below are a
# VERBATIM copy of ``benchmark_runner.py``'s verifier layer (its
# ``execute_verifier`` / ``_execute_*_verifier`` / ``_judge_rubric`` /
# ``_compare_with_llm`` / ``_extract_value_from_sql_result`` / ``_compare_values``
# / ``_diff_json_expected`` methods) — NOT a hand re-port. When the batch enables
# ``agentic_llm_as_judge`` the engine OWNS THE WHOLE SCORE: it runs its typed
# verifier list and writes benchmark_runner's native result (``verification_results``
# + ``verification_summary`` + ``statistics``).
#
# The verbatim async, LangChain-and-live-gym code runs unchanged via three thin
# sandbox adapters:
#   * ``_ProxyProtocolClient.get_state(verify_queries=[q])`` wraps the sync
#     ``query_state(gym, q)`` proxy call into the ``{success, data:
#     {verification_results:[{result: rows}]}}`` shape the engine's
#     ``_execute_sql_query`` reads.
#   * ``_LitellmJudgeClient.llm.ainvoke(messages)`` folds the engine's
#     ``[SystemMessage, HumanMessage]`` into one prompt and calls the sync
#     ``_call_judge_with_fallback`` (litellm), returning an object with
#     ``.content`` — so a monkeypatched ``_call_judge`` / ``query_state`` still
#     intercepts every judge / SQL touchpoint.
#   * a sync driver (``asyncio.run`` from the sync ``main()``) invokes the async
#     engine; the verifier process has no running loop so this never collides.
#
# The module-level adapters below (``_execute_rubric_check_verifier`` /
# ``_run_tool_execution`` / ``_run_json_match`` / ``_run_response_check`` /
# ``run_benchmark_verifiers``) are thin glue: they resolve the SQL gym, build the
# in-sandbox ``model_response`` from the trajectory + final answer, and enrich the
# result for the run-detail panel — but ALL judging / SQL / JSON-diff / tool-call
# scoring runs through the verbatim ``VerifierEngine``.

import asyncio
import types as _types
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class _EngineLogger:
    """No-op stand-in for benchmark_runner's module ``logger`` (the verbatim
    engine logs verbosely; the FROZEN template has no logger of its own and must
    not spam the verifier stdout)."""

    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass


logger = _EngineLogger()


# ── langchain_core.messages shim ────────────────────────────────────────
# The verbatim engine does ``from langchain_core.messages import SystemMessage,
# HumanMessage`` inside ``_judge_rubric`` / ``_compare_with_llm``. In the sandbox
# there is no langchain; register a minimal module so the verbatim import
# resolves. The judge shim only reads ``.content`` off each message, so a real
# langchain (present in the test container) works too — we never shadow it.

class SystemMessage:
    def __init__(self, content):
        self.content = content


class HumanMessage:
    def __init__(self, content):
        self.content = content


class ToolMessage:
    def __init__(self, content, tool_call_id=None):
        self.content = content
        self.tool_call_id = tool_call_id


def _ensure_langchain_messages_shim() -> None:
    try:
        import langchain_core.messages  # noqa: F401  (real one wins in the test env)
        return
    except Exception:
        pass
    mod = _types.ModuleType("langchain_core.messages")
    mod.SystemMessage = SystemMessage
    mod.HumanMessage = HumanMessage
    mod.ToolMessage = ToolMessage
    pkg = sys.modules.get("langchain_core")
    if pkg is None:
        pkg = _types.ModuleType("langchain_core")
        pkg.__path__ = []  # mark as a package so submodule import resolves
        sys.modules["langchain_core"] = pkg
    pkg.messages = mod
    sys.modules["langchain_core.messages"] = mod


_ensure_langchain_messages_shim()


class _ProxyProtocolClient:
    """Sandbox adapter for the engine's ``protocol_client``. Satisfies the
    verbatim ``_execute_sql_query`` openenv branch by wrapping the synchronous
    ``query_state(gym, q)`` proxy call (PROXY_BASE ``/raw/<gym>/state``)."""

    def __init__(self, gym_name):
        self.gym_name = gym_name
        # The verbatim mcp-mode branch (never reached — execution_mode is always
        # "openenv") reads these; keep them present so the attribute access can't
        # AttributeError even on a defensive path.
        self.database_id = ""
        self.context = {}
        self.base_url = ""

    async def get_state(self, verify_queries=None):
        queries = verify_queries or []
        query = queries[0] if queries else ""
        try:
            rows = query_state(self.gym_name, query)
        except Exception as exc:  # noqa: BLE001 — surface as a failed state result
            return {"success": False, "error": str(exc)}
        return {"success": True, "data": {"verification_results": [{"result": rows}]}}


class _LitellmJudgeResponse:
    """The object the verbatim engine reads ``.content`` off (mirrors a
    LangChain ``AIMessage``)."""

    def __init__(self, content):
        self.content = content


class _LitellmJudge:
    """Stands in for ``LLMClient.llm`` — the engine calls ``.ainvoke(messages)``."""

    def __init__(self, judge_cfg):
        self._cfg = judge_cfg or {}

    async def ainvoke(self, messages):
        # Fold the engine's [SystemMessage, HumanMessage] list into the single
        # user prompt the sync ``_call_judge_with_fallback`` takes.
        parts: list[str] = []
        for m in messages or []:
            content = getattr(m, "content", None)
            if content is None:
                content = m if isinstance(m, str) else str(m)
            parts.append(content if isinstance(content, str) else str(content))
        prompt = "\n\n".join(p for p in parts if p)
        raw = _call_judge_with_fallback(
            self._cfg.get("model"),
            self._cfg.get("api_key_env"),
            float(self._cfg.get("temperature", 0.0) or 0.0),
            int(self._cfg.get("max_tokens", 2048) or 2048),
            prompt,
            judge=self._cfg,
        )
        return _LitellmJudgeResponse(raw)


class _LitellmJudgeClient:
    """Stands in for ``LLMClient`` — exposes ``.llm`` with the async ``ainvoke``
    the verbatim engine calls (``self.judge_llm_client.llm.ainvoke``)."""

    def __init__(self, judge_cfg):
        self.llm = _LitellmJudge(judge_cfg)


# The VerifierEngine + VerifierConfig that used to be inlined here were an
# OLDER revision of benchmark_runner.py's verifier layer (616 vs 1170 lines:
# 9 methods absent, 7 divergent -- including _execute_tool_execution_verifier,
# _execute_rubric_check_verifier, _judge_rubric and the _invoke_judge_llm /
# _judge_ainvoke retry layer). They are now imported from verifier_engine.py,
# an extraction of the current benchmark_runner.py plus the LOCAL EDITs listed
# in its module docstring (notably: trace rubrics receive each call's result,
# not just its arguments).
import sys as _sys
from pathlib import Path as _Path
_ENGINE_DIR = str(_Path(__file__).resolve().parent)
if _ENGINE_DIR not in _sys.path:
    _sys.path.insert(0, _ENGINE_DIR)
from verifier_engine import VerifierConfig, VerifierEngine  # noqa: E402


def _calculate_statistics(
    runs: list[dict[str, Any]],
    discovered_tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single-run (or multi-run) benchmark statistics. VERBATIM from
    benchmark_runner.py's ``_calculate_statistics`` (``self.discovered_tools`` →
    the ``discovered_tools`` param, empty in-sandbox)."""
    discovered_tools = discovered_tools or []
    # Exclude infrastructure / incomplete grades from the headline rate (#555).
    _infrastructure_modes = {"verifier_error", "input_seeding_error"}
    gradable_runs = [
        r
        for r in runs
        if (r.get("failure_mode") or "pass") not in _infrastructure_modes
    ]
    successful_runs = [r for r in gradable_runs if r.get("overall_success")]
    total_runs = len(runs)
    gradable_total = len(gradable_runs)

    overall_success_rate = (
        len(successful_runs) / gradable_total if gradable_total > 0 else 0
    )

    if runs and (runs[0].get("failure_mode") or "pass") in _infrastructure_modes:
        pass_at_1 = None
    else:
        pass_at_1 = 1.0 if runs and runs[0].get("overall_success") else 0.0

    total_verifiers_count = 0
    passed_verifiers_count = 0
    verifier_pass_rates = {}

    for run in runs:
        if "verification_summary" in run:
            total_verifiers_count += run["verification_summary"]["total"]
            passed_verifiers_count += run["verification_summary"]["passed"]

        for verifier_name, result in run.get("verification_results", {}).items():
            if verifier_name not in verifier_pass_rates:
                verifier_pass_rates[verifier_name] = {"passed": 0, "total": 0}
            verifier_pass_rates[verifier_name]["total"] += 1
            if result.get("passed", False):
                verifier_pass_rates[verifier_name]["passed"] += 1

    verifier_stats = {}
    for verifier_name, counts in verifier_pass_rates.items():
        verifier_stats[verifier_name] = {
            "passed": counts["passed"],
            "total": counts["total"],
            "pass_rate": (
                counts["passed"] / counts["total"] if counts["total"] > 0 else 0.0
            ),
        }

    verifier_level_pass_rate = (
        passed_verifiers_count / total_verifiers_count
        if total_verifiers_count > 0
        else 0
    )

    failure_modes: Dict[str, int] = {}
    weighted_rates = []
    for run in runs:
        fm = run.get("failure_mode")
        if fm:
            failure_modes[fm] = failure_modes.get(fm, 0) + 1
        vsum = run.get("verification_summary") or {}
        rate = vsum.get("weighted_pass_rate")
        if rate is not None:
            weighted_rates.append(rate)
    weighted_pass_rate = (
        sum(weighted_rates) / len(weighted_rates)
        if weighted_rates
        else verifier_level_pass_rate
    )

    execution_times = [
        r.get("execution_time_ms", 0) for r in runs if "execution_time_ms" in r
    ]
    mean_time = (
        sum(execution_times) / len(execution_times) if execution_times else 0
    )

    all_tools = []
    for run in runs:
        all_tools.extend(run.get("tools_used", []))

    tool_counts = {}
    for tool in all_tools:
        tool_counts[tool] = tool_counts.get(tool, 0) + 1

    available_tools = sorted(
        {t.get("name") for t in discovered_tools if t.get("name")}
    )
    unused_tools = sorted(set(available_tools) - set(all_tools))

    return {
        "total_runs": total_runs,
        "gradable_runs": gradable_total,
        "successful_runs": len(successful_runs),
        "overall_success_rate": overall_success_rate,
        "pass_at_1": pass_at_1,
        "verifier_level_pass_rate": verifier_level_pass_rate,
        "weighted_pass_rate": weighted_pass_rate,
        "failure_modes": failure_modes,
        "exhausted_runs": failure_modes.get("exhausted_iterations", 0),
        "total_verifiers_checked": total_verifiers_count,
        "total_verifiers_passed": passed_verifiers_count,
        "individual_verifier_stats": verifier_stats,
        "mean_execution_time_ms": mean_time,
        "tool_usage": tool_counts,
        "tool_available": available_tools,
        "tool_unused": unused_tools,
    }


# ── JSON extraction (ported from benchmark_runner.py; the verbatim
#    ``_execute_json_match_verifier`` above calls module-level
#    ``_extract_json_from_text``) ──────────────────────────────────────────


def _top_level_json_objects(s: str) -> list[dict[str, Any]]:
    """Parseable top-level JSON objects embedded in ``s``, in position order.

    Port of ``benchmark_runner.py::_top_level_json_objects``. String- and
    escape-aware brace matching from every ``{`` (objects inside an already
    accepted span are skipped) so a stray brace/quote in surrounding prose can't
    derail detection of the real object.
    """
    objs: list[dict[str, Any]] = []
    accepted: list[tuple[int, int]] = []
    n = len(s)
    for start in range(n):
        if s[start] != "{":
            continue
        if any(a <= start < b for a, b in accepted):
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(start, n):
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(s[start : j + 1])
                        if isinstance(obj, dict):
                            objs.append(obj)
                            accepted.append((start, j + 1))
                    except json.JSONDecodeError:
                        pass
                    break
    return objs


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Parse the LAST JSON object from model text (fenced blocks or inline braces).

    Port of ``benchmark_runner.py::_extract_json_from_text``.
    """
    if not text or not text.strip():
        return None
    stripped = text.strip()
    candidates: list[dict[str, Any]] = []

    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.I):
        try:
            obj = json.loads(block.strip())
            if isinstance(obj, dict):
                candidates.append(obj)
        except json.JSONDecodeError:
            continue

    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            candidates.append(obj)
    except json.JSONDecodeError:
        pass

    candidates.extend(_top_level_json_objects(stripped))

    if candidates:
        return candidates[-1]
    return None


def _strip_tool_prefix(name: Any) -> str:
    """Strip the ``mcp__<server>__`` prefix Claude Code prepends. ``load_agent_trace``
    already does this, but oracle/legacy traces may carry raw names — re-strip
    defensively so tool-name assertions compare against the bare name."""
    if isinstance(name, str) and name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            return parts[2]
    return name if isinstance(name, str) else ""


# ── Sandbox driver glue ─────────────────────────────────────────────────


def _probe_task_gyms(task_cfg: dict[str, Any]) -> list[str]:
    """The task's gym names, probed from the well-known manifest/task.toml
    locations (mirrors ``_resolve_sql_target_gym``'s probe). Used to build the
    engine's ``protocol_clients`` map so SQL-backed verifiers route correctly."""
    gyms: list[str] = []
    for path in (
        ("environment", "servers"),
        ("environment", "gyms"),
        ("gyms",),
    ):
        node: Any = task_cfg
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, list):
            for entry in node:
                if isinstance(entry, dict):
                    name = entry.get("name") or entry.get("mcp_server_name") or entry.get("gym_name")
                    if name and name not in gyms:
                        gyms.append(name)
                elif isinstance(entry, str):
                    if entry not in gyms:
                        gyms.append(entry)
        if gyms:
            break
    return gyms


def _make_engine(judge: dict[str, Any] | None, gyms: list[str] | None) -> VerifierEngine:
    """Build a sandbox ``VerifierEngine``: a ``_ProxyProtocolClient`` per gym +
    the litellm judge shim. A placeholder client guarantees the engine's
    "at least one client" invariant for the no-SQL targets (it is never queried
    on those paths)."""
    clients: dict[str, _ProxyProtocolClient] = {}
    for g in gyms or []:
        if g and g not in clients:
            clients[g] = _ProxyProtocolClient(g)
    if not clients:
        clients["__default__"] = _ProxyProtocolClient(None)
    # Import helpers from the engine module (overlay #555).
    from verifier_engine import _judge_vote_count  # noqa: WPS433

    return VerifierEngine(
        clients,
        None,
        "openenv",
        judge_llm_client=_LitellmJudgeClient(judge or {}),
        judge_vote_count=_judge_vote_count(),
    )


def _model_response_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the live-harness ``model_response`` the verbatim engine expects
    from the in-sandbox evidence:

      ``tool_calls`` → the flat tool-call list (``load_agent_trace`` shape) with
        the ``mcp__<server>__`` prefix stripped off each ``name`` (so the
        verbatim ``_execute_tool_execution_verifier``'s bare-name comparison and
        the rubric ``trace`` target both see the canonical tool name); ``args``
        OR ``arguments`` is preserved for the trace evidence;
      ``content``    → the agent's final message for final_answer / json_match.
    """
    trajectory = evidence.get("trajectory") or []
    tool_calls: list[dict[str, Any]] = []
    for c in trajectory:
        if not isinstance(c, dict):
            continue
        call = dict(c)
        call["name"] = _strip_tool_prefix(c.get("name"))
        tool_calls.append(call)
    return {"tool_calls": tool_calls, "content": evidence.get("final_output") or ""}


# Module alias so existing callers/tests (``mod._parse_rubric_verdict``) keep
# working — same verbatim staticmethod the engine uses internally.
_parse_rubric_verdict = VerifierEngine._parse_rubric_verdict


def _execute_rubric_check_verifier(
    validation_config: dict[str, Any],
    model_response: dict[str, Any],
    judge: dict[str, Any],
    task_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the verbatim engine's ``rubric_check`` on one verifier.

    Sandbox glue around ``VerifierEngine._execute_rubric_check_verifier``:
      * fail closed when the rubric is missing;
      * a ``final_state`` target is judged against authoritative DB state and so
        REQUIRES a ``sql_query`` (fail closed when absent);
      * resolve the SQL gym (``_resolve_sql_target_gym``) when a ``sql_query`` is
        present and route the verbatim engine to it.
    The judging itself (prompt, verdict parsing) is the verbatim engine.
    """
    rubric = (validation_config.get("rubric") or "").strip()
    if not rubric:
        return {"passed": False, "error": "rubric_check: missing 'rubric'"}

    target = (validation_config.get("target") or "final_answer").lower()
    sql_query = (validation_config.get("sql_query") or "").strip()
    if target == "final_state" and not sql_query:
        return {
            "passed": False,
            "error": "rubric_check: final_state target requires a sql_query",
            "rubric": rubric,
        }

    gym = None
    if sql_query:
        gym, gym_err = _resolve_sql_target_gym(validation_config, task_cfg or {})
        if gym_err is not None:
            return {"passed": False, "error": f"rubric_check: {gym_err}", "rubric": rubric}

    engine = _make_engine(judge, [gym] if gym else [])
    return asyncio.run(engine._execute_rubric_check_verifier(validation_config, model_response, gym))


def _run_rubric_check(
    verifier: dict[str, Any],
    model_response: dict[str, Any],
    judge: dict[str, Any],
    task_cfg: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Engine adapter for the ``rubric_check`` verifier — reuses the verbatim
    atomic agentic judge via ``_execute_rubric_check_verifier``."""
    target = str(verifier.get("target") or "final_answer").strip().lower()
    if target not in ("trace", "final_answer", "final_state"):
        target = "final_answer"
    result = _execute_rubric_check_verifier(
        {
            "rubric":            verifier.get("rubric") or verifier.get("question") or "",
            "target":            target,
            "expected":          verifier.get("expected"),
            "sql_query":         verifier.get("sql_query"),
            "target_gym_server": verifier.get("target_gym_server"),
        },
        model_response,
        judge,
        task_cfg,
    )
    # Normalise to the item shape the run-detail panel reads: every rubric_check
    # item carries an explicit ``verdict`` + ``motivation`` even on the error
    # path (a missing rubric or a judge exception surfaces its message as the
    # motivation).
    passed = bool(result.get("passed"))
    result.setdefault("verdict", "PASS" if passed else "FAIL")
    result["motivation"] = result.get("motivation") or result.get("error") or ""
    result.setdefault("target", target)
    return result


def _rubric_check_verifiers_from_rubric(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    """Each ``rubric.toml`` item → one ``rubric_check`` verifier (back-compat:
    existing rubric authoring keeps working unchanged).

    The per-item ``weight`` is the category weight spread evenly across the
    category's items, so the engine's Σ(passed·weight)/Σweight reproduces the
    old per-category pass-rate × weight score EXACTLY. ``category`` is the engine
    core/secondary axis (rubric items are always ``core``); the rubric category
    name is carried separately as ``rubric_category`` for the breakdown display.
    """
    verifiers: list[dict[str, Any]] = []
    for cat in rubric.get("criteria", []):
        if not isinstance(cat, dict):
            continue
        cat_name = cat.get("category") or "uncategorised"
        try:
            cat_weight = float(cat.get("weight") or 0.0)
        except (TypeError, ValueError):
            cat_weight = 0.0
        items = [it for it in (cat.get("items") or []) if isinstance(it, dict)]
        if not items:
            continue
        per_item = cat_weight / len(items)
        for item in items:
            target = str(item.get("target") or "final_answer").strip().lower()
            if target not in ("trace", "final_answer", "final_state"):
                target = "final_answer"
            question = (item.get("question") or "").strip()
            verifiers.append({
                "verifier_type":     "rubric_check",
                "name":              item.get("id"),
                "id":                item.get("id"),
                "category":          "core",
                "weight":            per_item,
                "rubric":            question,
                "question":          question,
                "rubric_category":   cat_name,
                "target":            target,
                "sql_query":         item.get("sql_query"),
                "target_gym_server": item.get("target_gym_server"),
            })
    return verifiers


def _rubric_category_breakdown(items: list[dict[str, Any]]) -> dict[str, float]:
    """Per-rubric-category pass-rate over the ``rubric_check`` items (back-compat
    for the old agentic ``breakdown``). Non-rubric verifiers don't contribute."""
    by_cat: dict[str, list[bool]] = {}
    order: list[str] = []
    for it in items:
        if it.get("verifier_type") != "rubric_check":
            continue
        cat = it.get("rubric_category") or "uncategorised"
        if cat not in by_cat:
            by_cat[cat] = []
            order.append(cat)
        by_cat[cat].append(bool(it.get("passed")))
    out: dict[str, float] = {}
    for cat in order:
        flags = by_cat[cat]
        out[cat] = round(sum(1 for f in flags if f) / len(flags), 4) if flags else 0.0
    return out


def _run_tool_execution(
    verifier: dict[str, Any],
    model_response: dict[str, Any],
) -> dict[str, Any]:
    """Sandbox adapter → verbatim ``VerifierEngine._execute_tool_execution_verifier``."""
    engine = _make_engine({}, [])
    return asyncio.run(engine._execute_tool_execution_verifier(verifier, model_response))


def _run_json_match(
    verifier: dict[str, Any],
    model_response: dict[str, Any],
) -> dict[str, Any]:
    """Sandbox adapter → verbatim ``VerifierEngine._execute_json_match_verifier``.

    Adds a ``parse_ok`` flag (the run-detail panel renders a "parse failed" badge
    off it) which the verbatim result doesn't carry."""
    engine = _make_engine({}, [])
    result = engine._execute_json_match_verifier(verifier, model_response)
    if not isinstance(result, dict):
        return {"passed": False, "error": "json_match: verifier returned non-dict", "parse_ok": False}
    err = str(result.get("error") or "")
    result["parse_ok"] = "could not parse JSON" not in err and "missing expected object" not in err
    return result


def _run_file_check(
    verifier: dict[str, Any],
    model_response: dict[str, Any],
) -> dict[str, Any]:
    """Sandbox adapter → verbatim ``VerifierEngine._execute_file_check_verifier``.

    The engine grades the DELIVERABLE FILES the agent wrote, and reads their
    directory off ``model_response["workspace_dir"]`` — a key the live skills
    harness sets and the in-sandbox evidence (trajectory + final message) has no
    way to carry. This adapter is the only missing piece: it resolves the
    workspace on disk and hands it to the engine unchanged.

    In this bundle the agent's cwd IS the workspace (the Dockerfile sets
    ``WORKDIR /workspace`` and gives it to the agent user), and the verifier runs
    in the SAME container, so the files are on this filesystem. ``TH_WORKSPACE_DIR``
    overrides that default for a harness that mounts the workspace elsewhere.

    Fails LOUDLY when the directory is missing. A silent 0.0 would be
    indistinguishable from an agent that wrote nothing, and this is exactly the
    wiring mistake worth naming.
    """
    workspace = (os.environ.get("TH_WORKSPACE_DIR") or "/workspace").strip()
    if not workspace or not os.path.isdir(workspace):
        return {
            "passed": False,
            "error": (
                f"file_check: workspace directory not found ({workspace!r}). "
                "The deliverable files are graded off the agent's workspace, which "
                "this bundle serves at /workspace (Dockerfile WORKDIR). Set "
                "TH_WORKSPACE_DIR if the harness puts it elsewhere."
            ),
        }
    engine = _make_engine({}, [])
    response = dict(model_response or {})
    response["workspace_dir"] = workspace
    return asyncio.run(engine._execute_file_check_verifier(verifier, response))


def _run_response_check(
    verifier: dict[str, Any],
    model_response: dict[str, Any],
    judge: dict[str, Any],
    task_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sandbox adapter → verbatim ``VerifierEngine._execute_response_check_verifier``.

    Resolves the SQL gym, runs the verbatim verifier, and exposes the judge's
    1–10 rating as ``judge_score`` (the engine reserves ``score`` for the binary
    1.0/0.0 per-verifier score)."""
    sql_query = (verifier.get("sql_query") or "").strip()
    if not sql_query:
        return {"passed": False, "error": "response_check: missing sql_query"}
    gym, gym_err = _resolve_sql_target_gym(verifier, task_cfg or {})
    if gym_err is not None:
        return {"passed": False, "error": f"response_check: {gym_err}"}
    engine = _make_engine(judge, [gym] if gym else [])
    result = asyncio.run(engine._execute_response_check_verifier(verifier, model_response, gym))
    if isinstance(result, dict) and "score" in result and "judge_score" not in result:
        result["judge_score"] = result.pop("score")
    return result


def _run_database_state(
    verifier: dict[str, Any],
    task_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sandbox adapter for the benchmark_runner ``database_state`` verifier."""
    gym, gym_err = _resolve_sql_target_gym(verifier, task_cfg or {})
    if gym_err is not None:
        return {"passed": False, "error": f"database_state: {gym_err}"}
    engine = _make_engine({}, [gym] if gym else [])
    validation_config = {
        "sql_query": verifier.get("sql_query") or verifier.get("query") or "",
        "expected_value": verifier.get("expected_value") if "expected_value" in verifier else verifier.get("expected"),
        "comparison_type": verifier.get("comparison_type") or verifier.get("comparison") or "equals",
        "target_gym_server": verifier.get("target_gym_server"),
    }
    return asyncio.run(engine._execute_database_state_verifier(validation_config, gym))


def _is_near_miss(v: dict[str, Any], factor: float = 3.0) -> bool:
    """True if a failing json_match missed every numeric key by only a small
    margin (within factor*tolerance, or 1% of expected). Port of
    ``benchmark_runner.py::_is_near_miss`` — separates a defensible near-miss
    from a genuinely wrong answer."""
    expected = v.get("expected")
    actual = v.get("actual")
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    try:
        tol = float(v.get("float_tolerance", 0.0) or 0.0)
    except (TypeError, ValueError):
        tol = 0.0
    saw_numeric = False
    for key, exp in expected.items():
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            return False
        try:
            act = float(actual.get(key))
        except (TypeError, ValueError):
            return False
        diff = abs(act - float(exp))
        if diff <= tol:
            continue
        saw_numeric = True
        allowed = max(tol * factor, abs(float(exp)) * 0.01)
        if diff > allowed:
            return False
    return saw_numeric


def _classify_failure(
    scored_results: list[dict[str, Any]],
    overall_success: bool,
) -> str:
    """Tag why a run did/didn't succeed: pass | verifier_error | unparseable_json
    | missing_field | wrong_answer | near_miss.

    Port of ``benchmark_runner.py::_classify_failure`` MINUS ``exhausted_iterations``
    (the agent's iteration budget isn't observable in-sandbox). ``overall_success``
    is core-based, so a failing secondary alone does not produce a failure here —
    that's a pass."""
    if overall_success:
        return "pass"

    core_failing = [
        v for v in scored_results
        if isinstance(v, dict) and not v.get("passed", False)
    ]
    modes: list[str] = []
    for v in core_failing:
        err = str(v.get("error") or "")
        if "could not parse JSON" in err:
            modes.append("unparseable_json")
        elif (
            "missing expected object" in err
            or err.startswith("Unsupported")
            or err.startswith("rubric_check")
            or err.startswith("response_check")
            or err.startswith("tool_execution")
            or err.startswith("json_match")
            or "judge failed" in err
            or "Judge comparison failed" in err
        ):
            modes.append("verifier_error")
        elif any("missing in response" in m for m in (v.get("mismatches") or [])):
            modes.append("missing_field")
        elif _is_near_miss(v):
            modes.append("near_miss")
        else:
            modes.append("wrong_answer")

    if not modes:
        return "wrong_answer"
    for pref in (
        "verifier_error",
        "unparseable_json",
        "missing_field",
        "wrong_answer",
        "near_miss",
    ):
        if pref in modes:
            return pref
    return modes[0]


# Default per-verifier weight when the trainer doesn't author one (faithful to
# ``benchmark_runner.py``'s ``float(verifier.get("weight", 1.0))``).
DEFAULT_VERIFIER_WEIGHT: float = 1.0


def run_benchmark_verifiers(
    verifier_list: list[dict[str, Any]],
    evidence: dict[str, Any],
    judge: dict[str, Any],
    task_cfg: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Run a typed verifier list through the verbatim ``VerifierEngine`` and
    aggregate exactly as benchmark_runner's ``execute_single_run`` scoring does.

    Returns the engine envelope — the legacy back-compat view
    (``{score, items, core_passed, weighted_pass_rate, failure_mode, breakdown,
    mode, error}``) PLUS benchmark_runner's NATIVE output the UIs read:
      * ``verification_results`` — dict keyed by verifier name (== the items);
      * ``verification_summary`` — ``{total, passed, failed, pass_rate,
        core_total, core_passed, weighted_pass_rate}``;
      * ``statistics`` — a single-run ``_calculate_statistics`` block.
    """
    model_response = _model_response_from_evidence(evidence)
    items_out: list[dict[str, Any]] = []
    for v in verifier_list:
        if not isinstance(v, dict):
            continue
        vtype = str(v.get("verifier_type") or "rubric_check").strip().lower()
        # Single-tier (#555): category is metadata only. Default every verifier
        # to core; explicit secondary is still recorded but still gates.
        default_category = "core"
        category = str(v.get("category") or default_category).strip().lower()
        if category not in ("core", "secondary"):
            category = default_category
        try:
            weight = float(v.get("weight", DEFAULT_VERIFIER_WEIGHT))
        except (TypeError, ValueError):
            weight = DEFAULT_VERIFIER_WEIGHT

        try:
            if vtype == "rubric_check":
                result = _run_rubric_check(v, model_response, judge, task_cfg, manifest)
            elif vtype == "database_state":
                result = _run_database_state(v, task_cfg)
            elif vtype == "tool_execution":
                result = _run_tool_execution(v, model_response)
            elif vtype == "json_match":
                result = _run_json_match(v, model_response)
            elif vtype == "file_check":
                result = _run_file_check(v, model_response)
            elif vtype == "response_check":
                result = _run_response_check(v, model_response, judge, task_cfg)
            else:
                result = {
                    "passed": False,
                    "unscored": True,
                    "error": f"Unsupported verifier type: {vtype}",
                }
        except Exception as exc:  # noqa: BLE001 — fail the item, not the engine
            result = {"passed": False, "error": f"{vtype} error: {exc}"}

        if not isinstance(result, dict):
            result = {"passed": False, "error": "verifier returned non-dict"}
        passed = bool(result.get("passed"))
        item = dict(result)
        item["verifier_type"] = vtype
        item["category"] = category
        item["weight"] = weight
        item["passed"] = passed
        item["score"] = 1.0 if passed else 0.0
        item.setdefault("name", v.get("name") or v.get("id") or vtype)
        if "id" not in item:
            item["id"] = v.get("id")
        if "question" not in item and v.get("question") is not None:
            item["question"] = v.get("question")
        if v.get("rubric_category") is not None:
            item["rubric_category"] = v.get("rubric_category")
        items_out.append(item)

    by_type: dict[str, list[dict[str, Any]]] = {}
    for it in items_out:
        by_type.setdefault(str(it.get("verifier_type") or "verifier"), []).append(it)
    type_scores: dict[str, float] = {}
    for vtype, items in by_type.items():
        scored_items = [it for it in items if not it.get("unscored")]
        total_weight = sum(
            float(it.get("weight", DEFAULT_VERIFIER_WEIGHT)) for it in scored_items
        )
        passed_weight = sum(
            float(it.get("weight", DEFAULT_VERIFIER_WEIGHT))
            for it in scored_items
            if it.get("passed")
        )
        type_scores[vtype] = (passed_weight / total_weight) if total_weight > 0 else 0.0
    # LOCAL EDIT 3: honour scoring.flat_verifier_scoring here too — upstream
    # means the per-type rates, so each TYPE weighs equally regardless of how
    # many verifiers it holds. Flat mode pools every item by weight instead.
    scored_all = [it for it in items_out if not it.get("unscored")]
    unscored_n = len(items_out) - len(scored_all)
    failures = [it for it in scored_all if not it.get("passed")]
    complete = bool(items_out) and unscored_n == 0
    # #555: scored failure is conclusive; all-pass + any unscored => ungradable.
    overall_success = complete and not failures
    if bool((manifest.get("scoring") or {}).get("flat_verifier_scoring", False)):
        _tw = sum(float(it.get("weight", DEFAULT_VERIFIER_WEIGHT)) for it in scored_all)
        _pw = sum(
            float(it.get("weight", DEFAULT_VERIFIER_WEIGHT))
            for it in scored_all
            if it.get("passed")
        )
        scored_weighted = (_pw / _tw) if _tw > 0 else 0.0
    else:
        scored_weighted = (
            (sum(type_scores.values()) / len(type_scores)) if type_scores else 0.0
        )
    weighted = scored_weighted if complete else None
    # Single-tier: every verifier is in the gate (category is metadata only).
    scored = items_out
    core_passed = overall_success
    failure_mode = (
        "verifier_error"
        if (not failures and unscored_n)
        else _classify_failure(
            [it for it in scored if not it.get("unscored")], overall_success
        )
    )

    # ── benchmark_runner native output ───────────────────────────────
    # ``verification_results`` keyed by verifier name (the same per-verifier
    # items, as a dict) — the shape the UIs + GVS stats read.
    verification_results: dict[str, Any] = {}
    for it in items_out:
        name = it.get("name") or it.get("id") or it.get("verifier_type") or "verifier"
        key = name
        n = 1
        while key in verification_results:
            n += 1
            key = f"{name}_{n}"
        it["name"] = key
        verification_results[key] = it

    total_verifiers = len(items_out)
    passed_verifiers = sum(1 for it in scored_all if it.get("passed"))
    verification_summary = {
        "total":              total_verifiers,
        "passed":             passed_verifiers,
        "failed":             len(failures),
        "pass_rate":          (passed_verifiers / len(scored_all)) if scored_all else 0.0,
        "core_total":         len(scored),
        # bool overall success (single-tier) — the UIs read this as a flag.
        "core_passed":        core_passed,
        "weighted_pass_rate": (round(weighted, 4) if weighted is not None else None),
        "scored_weighted_pass_rate": round(scored_weighted, 4),
        "unscored":           unscored_n,
        "type_scores":        {k: round(v, 4) for k, v in type_scores.items()},
    }
    single_run = {
        "verification_results": verification_results,
        "verification_summary": verification_summary,
        "overall_success":      core_passed,
        "failure_mode":         failure_mode,
        "tools_used":           sorted({
            tc["name"] for tc in (model_response.get("tool_calls") or [])
            if isinstance(tc, dict) and tc.get("name")
        }),
        "execution_time_ms":    0,
    }
    statistics = _calculate_statistics([single_run], [])

    return {
        "score":                (round(weighted, 4) if weighted is not None else None),
        "items":                items_out,
        "core_passed":          core_passed,
        "weighted_pass_rate":   (round(weighted, 4) if weighted is not None else None),
        "scored_weighted_pass_rate": round(scored_weighted, 4),
        "failure_mode":         failure_mode,
        "breakdown":            _rubric_category_breakdown(items_out),
        "mode":                 "benchmark",
        "error":                None,
        # benchmark_runner native output (read by the run panel + GVS stats):
        "verification_results": verification_results,
        "verification_summary": verification_summary,
        "statistics":           statistics,
    }


def score_benchmark_verifiers(
    manifest: dict[str, Any],
    task_cfg: dict[str, Any],
    evidence: dict[str, Any],
    gyms: list[str] | None = None,
) -> dict[str, Any]:
    """In-sandbox benchmark_runner verifier engine. Builds the verifier list
    (rubric-derived ``rubric_check`` verifiers + the task's
    ``manifest.verifier_configs``) and runs ``run_benchmark_verifiers``.

    Same judge config as ``score_rubric`` (``metadata.verifier_judge``). Returns
    the engine envelope (legacy view + native ``verification_results`` /
    ``verification_summary`` / ``statistics``). ``gyms`` seeds the engine's
    ``protocol_clients`` map (the run's snapshot servers) so SQL-backed verifiers
    route to the right gym even before the task-config probe.
    """
    judge = (task_cfg.get("metadata") or {}).get("verifier_judge") or {}
    model = resolve_env_ref(judge.get("model"))
    api_key_env = resolve_env_ref(judge.get("api_key_env"))
    temperature = float(judge.get("temperature", 0.0))
    max_tokens = int(judge.get("max_tokens", 2048))

    empty: dict[str, Any] = {
        "score": 0.0, "breakdown": {}, "items": [], "core_passed": True,
        "weighted_pass_rate": 0.0, "failure_mode": "pass", "mode": "benchmark",
        "verification_results": {}, "verification_summary": {}, "statistics": {},
    }
    if not model or not api_key_env:
        return {**empty, "error": "verifier_judge not configured in task.toml"}
    if not os.environ.get(api_key_env, ""):
        return {**empty, "error": f"env var {api_key_env} not set"}

    judge_cfg = {
        "model": model,
        "api_key_env": api_key_env,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for _fb_key in ("fallback_model", "fallback_api_key_env"):
        _fb_val = judge.get(_fb_key)
        if _fb_val:
            judge_cfg[_fb_key] = _fb_val

    verifier_list: list[dict[str, Any]] = []
    # Rubric-derived ``rubric_check`` verifiers (one per rubric.toml item).
    rubric_path = TASK_DIR / manifest["rubric"]["file"]
    if rubric_path.exists():
        rubric = tomllib.loads(rubric_path.read_text())
        verifier_list.extend(_rubric_check_verifiers_from_rubric(rubric))
    # The unified ``verifier_configs`` list (tool_execution / json_match /
    # response_check / extra rubric_check).
    extra = manifest.get("verifier_configs")
    if isinstance(extra, list):
        verifier_list.extend(v for v in extra if isinstance(v, dict))

    # Seed the engine's gym map from the run's snapshot servers (passed in) +
    # the verifier target gyms — done inside run_benchmark_verifiers via
    # task_cfg, but a final_state/response_check verifier may target a gym only
    # known via the snapshot. Stash it on task_cfg so the probe sees it.
    if gyms:
        merged = dict(task_cfg or {})
        existing = merged.get("gyms")
        names = list(existing) if isinstance(existing, list) else []
        for g in gyms:
            if g and g not in names:
                names.append(g)
        merged["gyms"] = names
        task_cfg = merged

    return run_benchmark_verifiers(verifier_list, evidence, judge_cfg, task_cfg, manifest)


def _emit_engine_owned_reward(
    manifest: dict[str, Any],
    task_cfg: dict[str, Any],
    evidence: dict[str, Any],
    *,
    allowed_set: set[str],
    snapshot_servers: list[str],
    round_digits: int,
) -> None:
    """Engine-OWNS-the-whole-score path. Runs the vendored benchmark_runner
    engine and writes its native result to ``reward.json`` (+ a scalar
    ``reward.txt`` and ``verifier_summary.json``). The state/sql composite is
    skipped entirely — when ``agentic_llm_as_judge`` is enabled the engine is the
    sole scorer.

    reward.json carries BOTH benchmark_runner's native output
    (``verification_results`` / ``verification_summary`` / ``failure_mode`` /
    ``statistics``) AND a legacy ``rubric`` engine block, so new run panels read
    the native shape while older readers + the Summary card keep working.
    ``pass`` is the engine's core-based ``overall_success`` (not a threshold on
    the weighted score); ``total`` / ``composite`` are the weighted score so the
    Mean metric + Summary card stay correct.
    """
    nd = round_digits
    block = score_benchmark_verifiers(manifest, task_cfg, evidence, gyms=snapshot_servers)

    # An infrastructure failure is not a wrong answer. score_benchmark_verifiers
    # returns score=None with failure_mode='verifier_error' when the judge is
    # unreachable, returns an unusable schema, or reaches no majority -- and
    # returns its `empty` block (score 0.0, core_passed TRUE) when the judge is
    # unconfigured or its API key is unset, i.e. when NO verifier ran at all.
    #
    # Measured on the unpatched engine with the judge unconfigured: it writes
    # reward.json {"total": 0.0, "pass": true, ...} -- a task that was never
    # graded, reported as passing with a zero score. Harbor cannot tell either
    # case from an agent that got everything wrong.
    #
    # Raising leaves reward.json absent, so VerifierResult.rewards is None and
    # the trial is recorded as UNSCORED rather than failed. tests/test.sh already
    # propagates the non-zero exit and its reconcile block is guarded on
    # reward.json existing, so nothing manufactures a zero downstream.
    # Client QC: layer5_llm_judge_design__judge_failure_handling.
    if block.get("error") or block.get("failure_mode") == "verifier_error":
        raise RuntimeError(
            "verifier infrastructure failure, refusing to emit a score: "
            f"{block.get('error') or block.get('failure_mode')}"
        )

    weighted = float(block.get("score") or 0.0)
    core_passed = bool(block.get("core_passed", True))
    failure_mode = block.get("failure_mode") or ("pass" if core_passed else "wrong_answer")

    scoring_cfg = manifest.get("scoring") or {}
    raw_weights = scoring_cfg.get("weights") or {}

    def _w(axis: str) -> float:
        try:
            return float(raw_weights.get(axis, DEFAULT_VERIFIER_WEIGHTS[axis]))
        except (TypeError, ValueError):
            return DEFAULT_VERIFIER_WEIGHTS[axis]

    reward = {
        "total":                  round(weighted, nd),
        # Engine owns the score → pass is core-based overall success, NOT a
        # threshold on the weighted scalar.
        "pass":                   core_passed,
        "threshold":              PASS_THRESHOLD,
        "composite":              round(weighted, nd),
        "mode":                   "benchmark",
        "allowed_verifier_types": sorted(allowed_set),
        "weights": {
            "state":  _w("state"),
            "sql":    _w("sql"),
            "rubric": _w("rubric"),
        },
        "state": {
            "enabled":           "state" in allowed_set,
            "score":             None,
            "matched_expected":  0,
            "soft_unauthorized": 0,
            "hard_unauthorized": 0,
        },
        "sql": {
            "enabled":   "sql" in allowed_set,
            "score":     None,
            "passed":    0,
            "total":     0,
            "verifiers": [],
        },
        # Legacy engine block (back-compat: the run panel + GVS stats fall back
        # to this when ``verification_results`` is absent; the Summary card reads
        # its score).
        "rubric": {
            "enabled":            True,
            "score":              round(weighted, nd),
            "prompt_version":     JUDGE_PROMPT_VERSION,
            "mode":               "benchmark",
            "core_passed":        core_passed,
            "weighted_pass_rate": block.get("weighted_pass_rate"),
            "failure_mode":       failure_mode,
            "items":              block.get("items", []),
        },
        # benchmark_runner NATIVE output — what the run panel + GVS stats read
        # first.
        "verification_results":  block.get("verification_results", {}),
        "verification_summary":  block.get("verification_summary", {}),
        "failure_mode":          failure_mode,
        "statistics":            block.get("statistics", {}),
        # Legacy flat fields.
        "rubric_score":          round(weighted, nd),
        "state_score":           None,
        "side_effect_gate":      1.0,
        "judge_prompt_version":  JUDGE_PROMPT_VERSION,
    }
    for k, v in (block.get("breakdown") or {}).items():
        reward[f"rubric.{k}"] = v

    # harbor >=0.15 reads reward.json FIRST and validates it as a flat
    # dict[str, float|int]; pass_at_k needs len==1 and the leaderboard reads
    # rewards["reward"]. The rich multi-key object raises a Pydantic
    # ValidationError at verify time — after the agent has already succeeded.
    # Emit only the canonical scalar; the full breakdown stays in
    # verifier_summary.json written just below.
    (LOG_DIR / "reward.json").write_text(json.dumps({"reward": reward["total"]}))
    # reward.txt stays a single scalar (Mean "exactly one key" constraint).
    (LOG_DIR / "reward.txt").write_text(f"{reward['total']}\n")
    (LOG_DIR / "verifier_summary.json").write_text(
        json.dumps(
            {
                "reward": reward,
                "verification_results": block.get("verification_results", {}),
                "verification_summary": block.get("verification_summary", {}),
                "statistics": block.get("statistics", {}),
                "allowed_verifier_types": sorted(allowed_set),
            },
            indent=2,
            default=str,
        )
    )
    print(json.dumps(reward, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def active_weighted_score(weights: dict[str, Any], state_score: float, rubric_score: float) -> float:
    active_weights = {
        "state": float(weights.get("state") or 0.0),
        "rubric": float(weights.get("rubric") or 0.0),
    }
    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        return 0.0
    return (
        active_weights["state"] * state_score
        + active_weights["rubric"] * rubric_score
    ) / total_weight


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--emit-expected-diff",
        action="store_true",
        help=(
            "Oracle-dry-run mode: compute the state diff and write it to the "
            "manifest's state.expected_diff_file (solution/expected_diff.json). "
            "Skips trajectory + rubric scoring."
        ),
    )
    args = ap.parse_args()

    manifest = load_manifest()
    task_cfg = load_task_toml()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- State ----
    state_cfg = manifest["state"]

    # BEFORE snapshot was captured by the proxy at bootstrap.
    before_snapshots: dict[str, dict[str, Any]] = {}
    for p in sorted(SNAPSHOT_DIR.glob("*.before.json")):
        server_name = p.stem.removesuffix(".before")
        before_snapshots[server_name] = load_before_snapshot(server_name, state_cfg)
        write_json(
            SNAPSHOT_DIR / f"{server_name}.before.hashes.json",
            build_hash_snapshot(server_name, before_snapshots[server_name], state_cfg),
        )

    # AFTER snapshot: dump now from each MCP server via the proxy.
    after_snapshots: dict[str, dict[str, Any]] = {}
    for server_name in before_snapshots:
        after_snapshots[server_name] = dump_full_db(server_name, state_cfg)
        write_json_gzip(
            SNAPSHOT_DIR / f"{server_name}.after.rows.json.gz",
            {
                table: table_state.get("rows") or []
                for table, table_state in (after_snapshots[server_name].get("tables") or {}).items()
            },
        )
        write_json(
            SNAPSHOT_DIR / f"{server_name}.after.hashes.json",
            build_hash_snapshot(server_name, after_snapshots[server_name], state_cfg),
        )

    actual_diff = diff_snapshots(before_snapshots, after_snapshots, state_cfg)
    expected_diff_path = TASK_DIR / state_cfg["expected_diff_file"]

    # Oracle dry-run: persist the actual diff AS the expected diff and return.
    if args.emit_expected_diff:
        actual_diff["_comment"] = (
            "AUTO-GENERATED by tests/test_outputs.py --emit-expected-diff. "
            "Captures the DB changes produced by running the golden trajectory "
            "via solve.py against the seeded state."
        )
        write_json(expected_diff_path, actual_diff)
        print(f"wrote expected_diff to {expected_diff_path}")
        return

    expected_diff = load_json(expected_diff_path) if expected_diff_path.exists() else {}
    actual_diff = canonicalize_diff_volatile_fields(actual_diff, expected_diff)
    expected_diff = canonicalize_diff_volatile_fields(expected_diff, expected_diff)
    write_json(SNAPSHOT_DIR / "diff.json", actual_diff)
    write_json(SNAPSHOT_DIR / "expected.json", expected_diff)
    expected_state_entries = iter_diff_entries(expected_diff)
    state_axis_active = bool(expected_state_entries)

    # ── Determine which verifier axes are enabled for this run ───────
    # ``allowed_verifier_types`` is plumbed from the batch via the
    # task manifest. When missing (e.g. older tasks) we default to
    # the full set so existing tasks behave as before. Trainers
    # disable axes at the batch level — see HarborBatch model.
    scoring_cfg = manifest.get("scoring") or {}
    allowed = scoring_cfg.get("allowed_verifier_types")
    if not isinstance(allowed, list) or not allowed:
        allowed = list(KNOWN_VERIFIER_AXES)
    allowed_set = {a.lower() for a in allowed if isinstance(a, str)}
    state_enabled   = "state"  in allowed_set
    sql_enabled     = "sql"    in allowed_set
    rubric_enabled  = "rubric" in allowed_set
    # ``agentic_llm_as_judge`` is the opt-in enable flag for the benchmark_runner
    # verifier engine (it drives the same ``rubric`` composite axis as the Likert
    # path). It is never a default — only an explicit batch allowlist enables it —
    # so it stays out of ``KNOWN_VERIFIER_AXES``. (The persisted flag keeps its
    # ``agentic_llm_as_judge`` name; the code path is the renamed engine.)
    engine_enabled = "agentic_llm_as_judge" in allowed_set
    if not (state_enabled or sql_enabled or rubric_enabled or engine_enabled):
        raise ValueError(
            "No verifier axes enabled — allowed_verifier_types must include "
            f"at least one of {sorted(KNOWN_VERIFIER_AXES)} or agentic_llm_as_judge"
        )

    # ── State axis: per-column-partial-credit diff scoring ───────────
    # Only meaningful when ``state`` is enabled. Hard gate + soft
    # penalty are intrinsically tied to the diff comparison — when
    # state is disabled they default to no-op (1.0 each) so they
    # don't accidentally zero a run that opted out of state checking.
    state_score: float | None = None
    matched: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    hard: list[dict[str, Any]] = []
    hard_gate: float = 1.0
    soft_penalty: float = 1.0
    unexpected_diff: dict[str, Any] = {"schema_version": STATE_DIFF_SCHEMA, "gyms": {}}
    if state_enabled and state_axis_active:
        graded = match_expected_graded(actual_diff, expected_diff)
        state_score     = graded["state_score"]
        matched         = graded["matched"]
        soft            = graded["soft_unauthorized"]
        hard            = graded["hard_unauthorized"]
        hard_gate       = graded["hard_gate"]
        soft_penalty    = graded["soft_penalty"]
        unexpected_diff = graded["unexpected_diff"]
    write_json(SNAPSHOT_DIR / "unexpected.json", unexpected_diff)

    # ── SQL axis: trainer-authored assertions against post-agent gym ─
    # Pass-rate across all authored verifiers. When SQL is enabled
    # but the task has no verifiers authored, ``run_sql_verifiers``
    # returns score=1.0 (vacuously passes) and an empty result list —
    # we then drop the axis from the composite so an absent SQL block
    # doesn't artificially inflate the score.
    sql_score: float | None = None
    sql_results: list[dict[str, Any]] = []
    if sql_enabled:
        sql_score_raw, sql_results = run_sql_verifiers(task_cfg, manifest)
        # Only contribute to composite when there were actual verifiers.
        sql_score = sql_score_raw if sql_results else None

    # ── Trajectory + rubric ──────────────────────────────────────────
    traj_cfg = manifest.get("trajectory") or {}
    agent_trace_path = Path(traj_cfg.get("agent_trace_file") or "/logs/agent/trajectory.json")
    actual = load_agent_trace(agent_trace_path)
    # The agent's final text answer — the last assistant message in the ATIF
    # trajectory. Feeds the rubric ``final_output`` evidence (Likert path's
    # ``include_final_output``) and the agentic judge's ``final_answer`` target.
    final_output = _extract_final_output(agent_trace_path)
    # The full spoken transcript (bounded) — feeds the rubric's
    # ``include_assistant_messages`` evidence so a value reported mid-run (before
    # a closing pleasantry) is still judged, not just the trailing message.
    agent_messages = _extract_agent_messages(agent_trace_path)

    # ── Oracle fallback: agent trace is empty → use augmented golden ──
    # Oracle replays don't run a real LLM agent, so they don't write
    # to ``agent_trace_file``. Instead, ``solve.py --write-back``
    # augments ``solution/golden_trajectory.json`` in-place with
    # ``tool_execution_results`` per step. That augmented file has
    # the same flat-list shape ``load_agent_trace`` handles, so we
    # can feed it directly into the rubric's evidence block.
    #
    # Without this fallback, trajectory-dependent rubric items
    # (``used_real_ids``, ``no_destructive_tools``, etc.) score
    # poorly on Oracle runs because the LLM judge sees no tool calls
    # and can't verify the agent's sequencing — even though Oracle
    # produced a perfectly valid trace, just in a different file.
    #
    # GATE: only Oracle runs may substitute the golden. A crashed or
    # no-op REAL agent ALSO writes no trace — substituting the golden for
    # it scores the golden solution it never executed and earns a false
    # pass (the run is ``status=failed`` yet ``reward.json`` shows a
    # passing rubric). ``metadata.agent`` is stamped by the worker at
    # dispatch (app.py ``_build_composite_task_toml``); absent/empty (legacy
    # task.toml, or any non-oracle agent) → no fallback, so the empty
    # trajectory scores ~0. ``nop`` is intentionally excluded — a no-op
    # baseline should score 0, not the golden.
    agent_name = str((task_cfg.get("metadata") or {}).get("agent") or "").lower()
    is_oracle = agent_name == "oracle"
    if not actual and is_oracle:
        golden_path_str = traj_cfg.get("golden_file") or "solution/golden_trajectory.json"
        golden_path = TASK_DIR / golden_path_str
        if golden_path.exists():
            actual = load_agent_trace(golden_path)
            # Mirror the trajectory fallback for the final answer (a flat
            # golden list carries no assistant message → "" — but keep the
            # path symmetric for any future ATIF golden).
            if not final_output:
                final_output = _extract_final_output(golden_path)
            if not agent_messages:
                agent_messages = _extract_agent_messages(golden_path)
    evidence = {
        "diff": actual_diff,
        "unexpected": unexpected_diff,
        "trajectory": actual,
        "final_output": final_output,
        "agent_messages": agent_messages,
    }
    # ── Engine OWNS the whole score ──────────────────────────────────
    # When the batch enables the benchmark_runner verifier engine
    # (``agentic_llm_as_judge``), it is the SOLE scorer: it runs its typed
    # verifier list and writes benchmark_runner's native result. The state/sql
    # composite is skipped entirely (those axes are gated off for these
    # batches). reward.txt stays a single scalar (the engine's weighted score,
    # Mean-safe); ``pass`` is the engine's core-based ``overall_success``.
    if engine_enabled:
        _emit_engine_owned_reward(
            manifest, task_cfg, evidence,
            allowed_set=allowed_set,
            snapshot_servers=list(before_snapshots.keys()),
            round_digits=scoring_cfg.get("round_digits", 4),
        )
        return

    rubric: dict[str, Any] = {"score": 0.0, "breakdown": {}, "items": [], "error": None}
    rubric_score: float | None = None
    # The Likert ``score_rubric`` drives the rubric axis for non-engine batches.
    if rubric_enabled:
        rubric = score_rubric(manifest, task_cfg, evidence)
        # ``score_rubric`` returns 0.0 with an error string when the rubric
        # file is missing or no items exist — don't let that count as a
        # real 0 in the composite. Only contribute when we actually ran
        # the judge on at least one item.
        if rubric.get("items"):
            rubric_score = rubric["score"]

    # ── Compose: weighted mean over enabled-and-scored axes ──────────
    # Trainer can override per-task via ``scoring.weights``. Missing
    # keys fall back to ``DEFAULT_VERIFIER_WEIGHTS``. Axes that are
    # disabled OR didn't produce a score drop out — the remaining
    # weights are then renormalised over what's actually present.
    raw_weights = scoring_cfg.get("weights") or {}
    def _w(axis: str) -> float:
        try:
            return float(raw_weights.get(axis, DEFAULT_VERIFIER_WEIGHTS[axis]))
        except (TypeError, ValueError):
            return DEFAULT_VERIFIER_WEIGHTS[axis]

    # ``flat_verifier_scoring`` (opt-in, cascaded batch → project → global,
    # plumbed via ``harbor_composite.to_composite_body``) pools every
    # individual SQL verifier check + rubric item into ONE flat, unweighted
    # score instead of two separately-weighted axis scores. The ``state``
    # axis is unaffected either way. SQL checks are exact-match (binary, no
    # partial credit); rubric items carry a continuous [0,1] score, so the
    # pooled ``score`` sums that float per rubric item instead of collapsing
    # it to a pass/fail first — a 0.6 gets 0.6 credit, not 0. The displayed
    # ``passed``/``total`` tally stays a separate, coarser count: an item
    # "passes" that tally at score > 0.5, a plain majority-credit bar that's
    # intentionally more lenient than the item's own stricter PASS/FAIL badge
    # (``LIKERT_PASS_THRESHOLD``-gated) shown elsewhere.
    flat_verifier_scoring = bool(scoring_cfg.get("flat_verifier_scoring", False))

    contributors: list[tuple[str, float, float]] = []  # (axis, score, weight)
    if state_score is not None:
        contributors.append(("state", state_score, _w("state")))

    pooled_total = pooled_passed = 0
    pooled_points = 0.0
    pooled_weight = 0.0
    pooled_score: float | None = None
    if flat_verifier_scoring:
        if sql_enabled and sql_results:
            n_sql_passed = sum(1 for v in sql_results if v.get("passed"))
            pooled_total += len(sql_results)
            pooled_passed += n_sql_passed
            pooled_points += n_sql_passed
            pooled_weight += _w("sql")
        if rubric_enabled and rubric.get("items"):
            items = rubric["items"]
            pooled_total += len(items)
            pooled_points += sum(float(it.get("score", 0.0)) for it in items)
            pooled_passed += sum(1 for it in items if float(it.get("score", 0.0)) > 0.5)
            pooled_weight += _w("rubric")
        if pooled_total > 0:
            pooled_score = pooled_points / pooled_total
            contributors.append(("verifiers", pooled_score, pooled_weight))
    else:
        if sql_score is not None:
            contributors.append(("sql", sql_score, _w("sql")))
        if rubric_score is not None:
            contributors.append(("rubric", rubric_score, _w("rubric")))

    if contributors:
        total_w = sum(w for _, _, w in contributors)
        composite = sum(s * w for _, s, w in contributors) / total_w if total_w > 0 else 0.0
    else:
        # All axes disabled or all axes failed to produce a score.
        # ``composite=0`` is the conservative fallback; the upstream
        # ValueError check above already guards the "all-disabled"
        # config case so this branch is reachable only on judge
        # failures or completely-missing-rubric tasks.
        composite = 0.0

    # Hard gate + soft penalty apply on top of the composite — they
    # remain a state-axis concept (off-script detection), but when
    # state is disabled they're no-op (1.0) so the composite passes
    # through unmodified.
    if scoring_cfg.get("side_effect_gate", True):
        total_graded = composite * hard_gate * soft_penalty
    else:
        total_graded = composite * soft_penalty

    nd = scoring_cfg.get("round_digits", 4)
    is_pass = total_graded >= PASS_THRESHOLD

    # ── reward.json — per-axis breakdown ─────────────────────────────
    # Each axis has its own block with ``enabled`` so dashboards and
    # GRPO consumers can tell "this run scored 0 on SQL because SQL
    # was disabled" vs "this run scored 0 on SQL because every
    # verifier failed". Keeps the format extensible for future axes.
    sql_passed_n = sum(1 for v in sql_results if v.get("passed"))
    reward = {
        "total":                  round(total_graded, nd),
        "pass":                   bool(is_pass),
        "threshold":              PASS_THRESHOLD,
        "composite":              round(composite, nd),
        "hard_gate":              hard_gate,
        "soft_penalty":           round(soft_penalty, nd),
        "allowed_verifier_types": sorted(allowed_set),
        "flat_verifier_scoring":  flat_verifier_scoring,
        "weights":                {
            "state":     _w("state"),
            "sql":       _w("sql"),
            "rubric":    _w("rubric"),
            "verifiers": pooled_weight,
        },
        # Pooled SQL+rubric axis, only populated when flat_verifier_scoring
        # is on (otherwise 0/0/0.0, enabled=False) — provenance for how the
        # composite ``total`` was derived. See the per-axis blocks below for
        # the un-pooled sql/rubric diagnostics, which are unchanged in shape.
        "verifiers": {
            "enabled": flat_verifier_scoring,
            "score":   round(pooled_score, nd) if pooled_score is not None else None,
            "passed":  pooled_passed,
            "total":   pooled_total,
            "weight":  pooled_weight,
        },
        # Per-axis blocks. Each carries ``enabled`` so consumers can
        # distinguish "disabled" from "ran and scored zero".
        "state": {
            "enabled":           state_enabled and state_axis_active,
            "score":             round(state_score, nd) if state_score is not None else None,
            "matched_expected":  len(matched),
            "soft_unauthorized": len(soft),
            "hard_unauthorized": len(hard),
        },
        "sql": {
            "enabled":           sql_enabled,
            "score":             round(sql_score, nd) if sql_score is not None else None,
            "passed":            sql_passed_n,
            "total":             len(sql_results),
            "verifiers":         sql_results,
        },
        "rubric": {
            "enabled":           rubric_enabled or engine_enabled,
            "score":             round(rubric_score, nd) if rubric_score is not None else None,
            "prompt_version":    rubric.get("prompt_version") or JUDGE_PROMPT_VERSION,
            # ``mode`` distinguishes the Likert path ("likert") from the
            # benchmark_runner verifier engine ("benchmark"). When the engine
            # ran, carry the full per-verifier breakdown + the engine roll-up
            # (``core_passed`` / ``weighted_pass_rate``) so the frontend reads
            # them straight from reward.json (no separate review service).
            "mode":              rubric.get("mode") or "likert",
            **(
                {
                    "core_passed":        rubric.get("core_passed"),
                    "weighted_pass_rate": rubric.get("weighted_pass_rate"),
                    # Why the engine did/didn't pass (pass | verifier_error |
                    # unparseable_json | missing_field | wrong_answer | near_miss).
                    "failure_mode":       rubric.get("failure_mode"),
                    # Full per-verifier items (each carries verifier_type,
                    # category, weight, passed + its type-specific detail).
                    "items":              rubric.get("items", []),
                }
                if rubric.get("mode") == "benchmark"
                else {}
            ),
        },
        # Provenance — which judge-prompt template scored the rubric.
        "judge_prompt_version":  rubric.get("prompt_version") or JUDGE_PROMPT_VERSION,
        # Legacy flat fields, kept so any consumer that grew up
        # against the pre-3-axes shape keeps working. Mirror the new
        # per-axis blocks; will deprecate after frontend catches up.
        "state_score":           round(state_score, nd) if state_score is not None else None,
        "rubric_score":          rubric.get("score") if (rubric_enabled or engine_enabled) else None,
        "side_effect_gate":      hard_gate,
        "matched_expected":      len(matched),
        "soft_unauthorized":     len(soft),
        "hard_unauthorized":     len(hard),
    }
    for k, v in rubric.get("breakdown", {}).items():
        reward[f"rubric.{k}"] = v

    # harbor >=0.15 reads reward.json FIRST and validates it as a flat
    # dict[str, float|int]; pass_at_k needs len==1 and the leaderboard reads
    # rewards["reward"]. The rich multi-key object raises a Pydantic
    # ValidationError at verify time — after the agent has already succeeded.
    # Emit only the canonical scalar; the full breakdown stays in
    # verifier_summary.json written just below.
    (LOG_DIR / "reward.json").write_text(json.dumps({"reward": reward["total"]}))
    # Harbor's verifier reads reward.txt FIRST (single scalar -> Mean-safe);
    # only falls back to reward.json when reward.txt is missing. Multi-key
    # reward.json crashes the Mean metric with "Expected exactly one key in
    # reward dictionary, got N". Write the composite total as the scalar.
    (LOG_DIR / "reward.txt").write_text(f"{reward['total']}\n")
    (LOG_DIR / "verifier_summary.json").write_text(
        json.dumps(
            {
                "reward": reward,
                # State-axis diagnostics (empty when state is disabled).
                "matched_expectations": matched,
                "unauthorized_changes": soft + hard,
                "unexpected_diff":      unexpected_diff,
                # SQL-axis diagnostics — full per-verifier breakdown so the
                # Summary card can render pass/fail badges and show actual
                # vs expected for each entry. Empty when SQL is disabled
                # or no verifiers authored on the task.
                "sql_verifiers":        sql_results,
                # Rubric LLM-judge output, unchanged.
                "rubric":               rubric,
                # Provenance for the entire verifier run.
                "allowed_verifier_types": sorted(allowed_set),
            },
            indent=2,
            default=str,
        )
    )

    print(json.dumps(reward, indent=2))


if __name__ == "__main__":
    main()
