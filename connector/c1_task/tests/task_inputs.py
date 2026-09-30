"""Read-only input files shipped with a benchmark task.

A task folder may carry fixture files the solving agent reads:

    <tasks-dir>/<task_name>/
        <task_name>.json     # declares scenario_config.inputs.sha256
        inputs/              # committed loose, for reviewable diffs
        input.zip            # committed, AUTHORITATIVE at run time

Before each run the harness extracts `input.zip` into `<workspace>/input/`.
Identity is a hash over FILE CONTENTS, never over archive bytes: zip archives
embed mtimes and depend on entry ordering, so regenerating an archive from
identical files yields different bytes.
"""

import hashlib
import os
import posixpath
import re
import zipfile

# Directory the agent reads inputs from, relative to its workspace.
INPUT_DIR_NAME = "input"
# Directory inside a task folder holding the loose (reviewable) fixtures.
INPUTS_SUBDIR = "inputs"
# The authoritative archive inside a task folder.
INPUT_ZIP_NAME = "input.zip"

_CHUNK = 1024 * 1024


class InputSeedingError(RuntimeError):
    """Raised when a task's declared input files cannot be seeded.

    This is INFRASTRUCTURE failure, never model failure — callers must ensure
    it is never classified as `wrong_answer`.
    """


def file_sha256(path: str) -> str:
    """Return the hex sha256 of a file's contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_from_dir(root: str) -> list:
    """Return a sorted [(relative_posix_path, sha256)] manifest of a directory."""
    entries = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            entries.append((rel, file_sha256(full)))
    return sorted(entries)


def manifest_from_zip(zip_path: str) -> list:
    """Return a sorted [(relative_posix_path, sha256)] manifest of a zip's members."""
    entries = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            digest = hashlib.sha256()
            with zf.open(info) as fh:
                for chunk in iter(lambda: fh.read(_CHUNK), b""):
                    digest.update(chunk)
            entries.append((info.filename.replace(os.sep, "/"), digest.hexdigest()))
    return sorted(entries)


def manifest_hash(manifest: list) -> str:
    """Hash a manifest into the single value recorded in the task JSON."""
    blob = "".join(f"{path}\x00{digest}\n" for path, digest in manifest)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def extract_inputs(zip_path: str, workspace_dir: str) -> list:
    """Extract `zip_path` into `<workspace_dir>/input/`.

    Returns the sorted seeded paths RELATIVE TO THE WORKSPACE (e.g.
    `input/a.csv`), which is the form the provenance and grading guards use.
    Each recorded path is `posixpath.normpath`-ed independently of what gets
    WRITTEN to disk (`target`, below, is derived from the raw archive member
    name) -- a member like `./r.csv` still writes to `input/r.csv` on disk,
    but must also be RECORDED as `input/r.csv`, not `input/./r.csv`, or
    `list_workspace_files` fails to recognize the seeded file as provenance
    (misreporting it as agent-produced) and the system prompt advertises a
    path that doesn't match the one actually on disk.

    Raises InputSeedingError on zip-slip or absolute member names.
    """
    dest_root = os.path.join(workspace_dir, INPUT_DIR_NAME)
    resolved_root = os.path.realpath(dest_root)
    os.makedirs(dest_root, exist_ok=True)

    seeded = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", name):
                raise InputSeedingError(
                    f"{zip_path}: input.zip member has an absolute path: {name!r}"
                )
            target = os.path.realpath(os.path.join(dest_root, name))
            if target != resolved_root and not target.startswith(resolved_root + os.sep):
                raise InputSeedingError(
                    f"{zip_path}: input.zip member escapes the input directory: {name!r}"
                )
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target):
                os.chmod(target, 0o644)
                os.remove(target)
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
            os.chmod(target, 0o444)
            recorded = posixpath.normpath(f"{INPUT_DIR_NAME}/{name.replace(os.sep, '/')}")
            seeded.append(recorded)
    return sorted(seeded)


def seed_inputs(task_file: str, workspace_dir: str, expected_sha256: str) -> list:
    """Seed a task's declared inputs into `workspace_dir`.

    `task_file` is the task's JSON path; the archive is its sibling `input.zip`.
    Verifies the archive's manifest hash against `expected_sha256` BEFORE
    extracting, so a stale or wrong archive never reaches the agent.

    Returns the sorted workspace-relative seeded paths.
    """
    task_folder = os.path.dirname(os.path.abspath(task_file))
    zip_path = os.path.join(task_folder, INPUT_ZIP_NAME)
    if not os.path.isfile(zip_path):
        raise InputSeedingError(
            f"task declares inputs but {INPUT_ZIP_NAME} is missing at {zip_path}"
        )

    actual = manifest_hash(manifest_from_zip(zip_path))
    if actual != expected_sha256:
        raise InputSeedingError(
            f"input hash mismatch for {zip_path}: declared {expected_sha256}, "
            f"archive is {actual}. The archive is stale or the wrong one shipped."
        )
    return extract_inputs(zip_path, workspace_dir)


def verify_task_inputs(task_folder: str, expected_sha256: str) -> None:
    """Fail if `inputs/`, `input.zip`, and the declared hash disagree.

    Run this in CI or as a pre-commit hook: it turns a silent grading bug
    (fixtures edited, archive not regenerated) into a loud one.
    """
    zip_path = os.path.join(task_folder, INPUT_ZIP_NAME)
    loose_dir = os.path.join(task_folder, INPUTS_SUBDIR)

    if not os.path.isfile(zip_path):
        raise InputSeedingError(f"missing {INPUT_ZIP_NAME} in {task_folder}")
    if not os.path.isdir(loose_dir):
        raise InputSeedingError(f"missing {INPUTS_SUBDIR}/ in {task_folder}")

    zip_hash = manifest_hash(manifest_from_zip(zip_path))
    loose_hash = manifest_hash(manifest_from_dir(loose_dir))

    if zip_hash != loose_hash:
        raise InputSeedingError(
            f"input drift in {task_folder}: {INPUTS_SUBDIR}/ and {INPUT_ZIP_NAME} "
            f"disagree ({loose_hash} vs {zip_hash}). Regenerate the archive."
        )
    if zip_hash != expected_sha256:
        raise InputSeedingError(
            f"input drift in {task_folder}: files hash to {zip_hash} but the task "
            f"JSON declares {expected_sha256}. Update scenario_config.inputs.sha256."
        )
