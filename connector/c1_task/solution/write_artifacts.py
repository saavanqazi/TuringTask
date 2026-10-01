#!/usr/bin/env python3
"""Materialise the ORACLE's deliverables into the agent workspace.

The golden trajectory is gym tool calls only, so nothing in the replay puts a file on
disk -- but the `file_check` verifier grades files in the workspace. Without this the
oracle scores less than 1.0 on a task that is not actually broken, which is what happened
on the first round of this batch (github 0.8, notion 0.6667, slack 0.8333).

The CSV files are written verbatim from artifact_plan.json, the same rows the row checks are generated from.
The xlsx workbook is built FROM THE ASSERTIONS (sheet + cell -> expected), so the cells
the grader reads and the cells the oracle writes cannot drift apart.
"""
import json, os, sys
from pathlib import Path

sol = Path(os.environ.get("SOLUTION_DIR", "/solution"))
ws = Path(os.environ.get("WORKSPACE", os.environ.get("TH_WORKSPACE_DIR", "/workspace")))
ws.mkdir(parents=True, exist_ok=True)
plan = json.loads((sol / "artifact_plan.json").read_text())

if plan.get("report_path"):
    (ws / plan["report_path"]).write_text(plan["report"])
    print("wrote", plan["report_path"])

for path, text in (plan.get("csv") or {}).items():
    (ws / path).write_text(text)
    print("wrote", path, "rows", text.count("\n") - 1)

if plan.get("json_path"):
    (ws / plan["json_path"]).write_text(json.dumps(plan["json"], indent=2) + "\n")
    print("wrote", plan["json_path"], "keys", sorted(plan["json"])[:8])

if plan.get("xlsx_path"):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, cells in plan["xlsx"].items():
        w = wb.create_sheet(title=sheet[:31])
        for cell, value in cells.items():
            w[cell] = value
    wb.save(ws / plan["xlsx_path"])
    print("wrote", plan["xlsx_path"], "sheets", list(plan["xlsx"]))
