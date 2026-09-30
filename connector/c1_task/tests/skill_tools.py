"""Local skill execution for the task-harness.

Adds a single built-in ``bash`` tool so the model under test can use the office
document skills in ``skills/`` (each a ``SKILL.md`` guide + helper scripts) via
the command line, instead of MCP gym tools. The model creates/edits documents by
running shell commands (its skill scripts, python, etc.) in a per-run writable
workspace.

Kept separate from ``benchmark_runner.py`` so the harness wiring stays a handful
of small edits. Nothing here imports the runner (no circular import); results are
returned in the same OpenEnv envelope shape the runner already understands, so the
existing logging/result plumbing works unchanged.
"""

import os
import shutil
import subprocess

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(HARNESS_DIR, "skills")

BASH_TOOL_NAME = "bash"

# MCP-style tool dict (name/description/inputSchema). The runner converts this to
# each provider's native tool shape via LangChain, so one definition covers
# Anthropic / OpenAI / Gemini.
BASH_TOOL_DEF = {
    "name": BASH_TOOL_NAME,
    "description": (
        "Run a shell command in your task workspace (a writable scratch directory "
        "that is your current working directory and persists across calls within a "
        "run). Use this to create and edit documents with the available skills: read "
        "a skill's SKILL.md, then run its scripts / your own python. Returns the "
        "command's exit code plus combined stdout and stderr."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute with bash -c.",
            },
            "timeout": {
                "type": "integer",
                "description": "Max seconds before the command is killed (default 120, max 600).",
            },
        },
        "required": ["command"],
    },
}


_NODE_PATH = None  # cached global node_modules dir (so `require('docx')` resolves)


def _node_path():
    """NODE_PATH covering both a harness-local ``node_modules`` (from package.json)
    and the global npm root, so ``require('docx')`` resolves either way."""
    global _NODE_PATH
    if _NODE_PATH is None:
        paths = []
        local = os.path.join(HARNESS_DIR, "node_modules")
        if os.path.isdir(local):
            paths.append(local)
        try:
            out = subprocess.run(
                ["npm", "root", "-g"], capture_output=True, text=True, timeout=15
            )
            if out.returncode == 0 and out.stdout.strip():
                paths.append(out.stdout.strip())
        except Exception:
            pass
        _NODE_PATH = os.pathsep.join(paths)
    return _NODE_PATH


def _gym_shaped(text, is_error=False):
    """Wrap output in the OpenEnv MCPObservation envelope the runner expects
    (``result.tool_result.text`` / ``.isError``)."""
    return {
        "success": True,
        "result": {"tool_result": {"isError": bool(is_error), "text": text}},
    }


def run_bash(args, cwd, default_timeout=120, max_output=20000):
    """Execute one shell command in ``cwd`` and return a gym-shaped result dict."""
    args = args or {}
    command = args.get("command")
    if not command or not isinstance(command, str):
        return _gym_shaped("error: a non-empty 'command' string is required", is_error=True)

    timeout = args.get("timeout") or default_timeout
    try:
        timeout = max(1, min(int(timeout), 600))
    except (TypeError, ValueError):
        timeout = default_timeout

    if not cwd or not os.path.isdir(cwd):
        return _gym_shaped(f"error: workspace directory is unavailable ({cwd!r})", is_error=True)

    env = os.environ.copy()
    node_path = _node_path()
    if node_path:  # make globally-installed skill libs (docx-js, pptxgenjs) resolvable
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = node_path if not existing else f"{node_path}{os.pathsep}{existing}"

    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return _gym_shaped(f"error: command timed out after {timeout}s", is_error=True)
    except Exception as exc:  # pragma: no cover - defensive
        return _gym_shaped(f"error: failed to run command: {exc}", is_error=True)

    body = proc.stdout or ""
    if proc.stderr:
        body = f"{body}\n[stderr]\n{proc.stderr}" if body else f"[stderr]\n{proc.stderr}"
    if len(body) > max_output:
        body = body[:max_output] + f"\n... [truncated; {len(body)} chars total]"
    text = f"exit_code: {proc.returncode}\n{body}".rstrip()
    return _gym_shaped(text, is_error=proc.returncode != 0)


def prepare_workspace(run_number=1, base_dir=None):
    """Create a fresh, empty per-run workspace and return its absolute path.

    The workspace holds ONLY the files the agent creates — skills are NOT copied
    or linked in; the agent reaches them by their absolute path (see the skills
    index). ``base_dir`` roots the workspace (recommended: the task's results dir,
    so produced documents are preserved next to their results and never clobbered
    by a later run). Falls back to the git-ignored ``.temp_workspace/`` when unset.
    """
    root = base_dir or os.path.join(HARNESS_DIR, ".temp_workspace")
    workspace = os.path.join(root, f"run_{run_number}")
    shutil.rmtree(workspace, ignore_errors=True)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _validate_document(path):
    """Best-effort validity check for known document types: open the file with the
    matching library. Returns ``(kind, valid)`` — valid True/False for a recognized
    document type, or ``(None, None)`` if the extension isn't a checked format."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            from docx import Document

            Document(path)
            return "docx", True
        if ext in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook

            load_workbook(path)
            return "xlsx", True
        if ext == ".pdf":
            from pypdf import PdfReader

            len(PdfReader(path).pages)
            return "pdf", True
        if ext == ".pptx":
            from pptx import Presentation

            Presentation(path)
            return "pptx", True
    except Exception:
        return (ext.lstrip(".") or "file"), False
    return None, None


def list_workspace_files(workspace_dir, seeded_paths=None):
    """Return the files the agent created in its workspace as
    ``[{"path", "bytes", ["kind", "valid"]}]`` (sorted). ``valid`` is the result of
    opening a recognized document (docx/xlsx/pdf/pptx) with its library. Empty list
    if none. This is how a run is checked for produced (and valid) files — no
    verifier required.

    ``seeded_paths`` are workspace-relative paths that were seeded as read-only task
    inputs; they are excluded so "produced" means "the agent made this". Defaults to
    None so tasks without inputs behave exactly as before."""
    created = []
    seeded = set(seeded_paths or ())
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return created
    for dirpath, _dirs, files in os.walk(workspace_dir):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, workspace_dir).replace(os.sep, "/")
            if rel in seeded:
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            entry = {"path": rel, "bytes": size}
            kind, valid = _validate_document(full)
            if kind is not None:
                entry["kind"] = kind
                entry["valid"] = valid
            created.append(entry)
    return sorted(created, key=lambda f: f["path"])


def _parse_frontmatter(skill_md_path):
    """Return (name, description) from a SKILL.md YAML frontmatter, or (None, None)."""
    name = description = None
    try:
        with open(skill_md_path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, None
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else ""
    for line in block.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("'\"")
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip().strip("'\"")
    return name, description


def build_skills_index(skills_dir=SKILLS_DIR, seeded_inputs=None):
    """Build a system-prompt block listing the available skills + how to use them.
    Returns "" when there are no skills.

    ``seeded_inputs`` are workspace-relative paths to read-only task input files.
    They are listed explicitly so the agent reads the data it was given instead of
    fabricating it."""
    entries = []
    if os.path.isdir(skills_dir):
        for name in sorted(os.listdir(skills_dir)):
            skill_md = os.path.join(skills_dir, name, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            sname, sdesc = _parse_frontmatter(skill_md)
            sname = sname or name
            sdesc = (sdesc or "").split(". ")[0].strip()[:280]
            entries.append(f"- **{sname}** — {sdesc} (guide: `{skills_dir}/{name}/SKILL.md`)")

    inputs_block = []
    if seeded_inputs:
        listing = "\n".join(f"- `{p}`" for p in seeded_inputs)
        inputs_block = [
            "",
            "## Provided input files (read-only)",
            "These files were placed in your workspace for this task. Read them "
            "before answering — they are the data the task refers to. Do NOT "
            "invent values you could have read from them, and do not modify them.",
            listing,
        ]

    if not entries and not inputs_block:
        return ""

    skills_block = []
    if entries:
        skills_block = [
            "",
            "## Tools: shell + document skills",
            "You have a `bash` tool that runs shell commands in a writable workspace "
            "(your current working directory). Use it to create and edit document "
            "files. A set of **skills** is available — each is a folder with a "
            "`SKILL.md` guide plus helper scripts. **Read the relevant `SKILL.md` "
            "first** (e.g. `cat <path>`), then follow it (run its scripts / write python).",
            "Available skills:",
            *entries,
            f"The skills live at `{skills_dir}/<name>/` (absolute paths — they are NOT "
            "in your workspace, so reference them absolutely). Python libraries "
            "(python-docx, python-pptx, openpyxl, pypdf, pdfplumber, reportlab, pandas, "
            "lxml, defusedxml) are preinstalled — prefer them. Node tools (docx, "
            "pptxgenjs) are optional and only available if `npm install` has been run in "
            "the harness dir. Save every deliverable into your current working directory "
            "(the workspace).",
        ]

    return "\n".join(skills_block + inputs_block)
