#!/usr/bin/env python3
"""probe_suite.py - prove the grader before any trial (Standard stage 11, VER-24).

Run from anywhere with Python 3.12:  python tests/probe_suite.py
Every case is graded by the vendored engine exactly as score.py grades it.

  gold         the shipped golden files must score 1.0
  E (equiv.)   meaning-preserving rewrites of the gold must still score 1.0
  B (break)    real mistakes must fail, on the check named for them
  D (decoys)   one solver per expected wrong reading (generate_fixture.WRONG_READINGS);
               each must fail, and only on the rows / figures its reading changes
  F (floor)    degenerate submissions: majority class, instruction pasted as the note,
               a copy of an input, the empty workspace
  N (note)     paraphrased notes must pass; wrong or missing facts must fail
Exit status 0 only when every expectation holds.
"""
import csv
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from rl_world_verifiers.models import VerifierSpec, effective_weights  # noqa: E402
from rl_world_verifiers.sources.registry import SourceRegistry  # noqa: E402
from rl_world_verifiers.verifiers import verify_definition  # noqa: E402
import generate_fixture as gen  # noqa: E402

SPEC = VerifierSpec.model_validate_json((TESTS / "verifier.json").read_text(encoding="utf-8"))
WEIGHTS = effective_weights(SPEC.verifiers)
GOLD = ROOT / "solution" / "files"
GOLD_ROWS = list(csv.reader(io.StringIO((GOLD / "fitting_register.csv").read_text(encoding="utf-8"))))
GOLD_RESULTS = json.loads((GOLD / "results.json").read_text(encoding="utf-8"))
GOLD_NOTE = (GOLD / "takeoff_note.md").read_text(encoding="utf-8")
UNRESOLVED = [r[0] for r in GOLD_ROWS[1:] if r[2] == "UNRESOLVED"]


def failures(files):
    """files: {name: bytes|str}; returns the names of the checks that fail."""
    d = Path(tempfile.mkdtemp())
    try:
        for name, data in files.items():
            (d / name).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        reg = SourceRegistry(d)
        return [v.name for v in SPEC.verifiers
                if not verify_definition(v, reg, WEIGHTS[v.name], config=SPEC.config, completion_fn=None)["result"]["success"]]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def gold_files():
    return {p.name: p.read_bytes() for p in GOLD.iterdir()}


def csv_text(rows, quote=False):
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL if quote else csv.QUOTE_MINIMAL, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def with_rows(rows, **extra):
    f = gold_files(); f["fitting_register.csv"] = csv_text(rows); f.update(extra); return f


def with_results(**changes):
    f = gold_files(); f["results.json"] = json.dumps({**GOLD_RESULTS, **changes}); return f


def note_for(rows, results):
    return gen.gold_note([tuple(r) for r in rows], results)


problems = 0


def expect(label, fails, should_fail, only=None):
    global problems
    ok = bool(fails) == should_fail and (only is None or set(fails) <= set(only))
    problems += not ok
    print(f"{'ok ' if ok else 'BAD'} {label}: {'FAILS ' + str(fails) if fails else 'passes'}")


print("== gold")
expect("gold", failures(gold_files()), False)

print("== E: equivalent rewrites (must pass)")
g = gold_files()
E = {
    "E1 JSON key order reversed": {**g, "results.json": json.dumps(dict(reversed(list(GOLD_RESULTS.items()))))},
    "E4 every CSV field quoted": {**g, "fitting_register.csv": csv_text(GOLD_ROWS, quote=True)},
    "E5 CRLF everywhere": {k: v.replace(b"\n", b"\r\n") for k, v in g.items()},
    "E6 no trailing newline": {**g, "fitting_register.csv": g["fitting_register.csv"].rstrip(b"\n")},
    "E7 UTF-8 BOM on register": {**g, "fitting_register.csv": b"\xef\xbb\xbf" + g["fitting_register.csv"]},
    "E8 counts written as N.0": {**g, "results.json": json.dumps({**GOLD_RESULTS, **{k: float(v) for k, v in GOLD_RESULTS.items() if k.endswith("count")}})},
    "E9 total with trailing zero": {**g, "results.json": g["results.json"].replace(str(GOLD_RESULTS["total_run_ft"]).encode(), (str(GOLD_RESULTS["total_run_ft"]) + "0").encode())},
    "E14 extra scratch file": {**g, "scratch.py": "x = 1\n"},
}
for label, files in E.items():
    expect(label, failures(files), False)

print("== B: real mistakes (must fail)")
rows = [list(r) for r in GOLD_ROWS]
first, last = rows[1][0], rows[-1][0]
flip = [r[:] for r in rows]; flip[1][2] = "COUPLER" if flip[1][2] != "COUPLER" else "REDUCER"
B = {
    "B1 one kind flipped": (with_rows(flip), ["register_table"]),
    "B2 one row dropped": (with_rows([r for r in rows if r[0] != last]), ["register_table"]),
    "B3 spurious row added": (with_rows(rows + [["C-99", "NONE", "COUPLER"]]), ["register_table"]),
    "B3b withdrawn rows kept (as NONE/ADAPTER)": (with_rows(rows + [["C-03", "NONE", "ADAPTER"]]), ["register_table"]),
    "B4 reducer_count +1": (with_results(reducer_count=GOLD_RESULTS["reducer_count"] + 1), ["results_figures"]),
    "B4b total includes unresolved runs": (with_results(total_run_ft=GOLD_RESULTS["total_run_ft"] + 16), ["results_figures"]),
    "B5 rows swapped out of order": (with_rows([rows[0], rows[2], rows[1]] + rows[3:]), ["register_table"]),
    "B6 register emptied": ({**gold_files(), "fitting_register.csv": ""}, None),
    "B7 results.json deleted": ({k: v for k, v in gold_files().items() if k != "results.json"}, ["results_figures"]),
    "B8 results.json is {}": ({**gold_files(), "results.json": "{}"}, ["results_figures"]),
    "B8b note deleted": ({k: v for k, v in gold_files().items() if k != "takeoff_note.md"}, None),
}
for label, (files, only) in B.items():
    expect(label, failures(files), True, only)

print("== D: decoy solvers, one per expected wrong reading (must fail)")
gold_map = {r[0]: (r[1], r[2]) for r in rows[1:]}
for flag, meaning in gen.WRONG_READINGS.items():
    d_rows, d_res = gen.solve(**{flag: True})
    d_map = {c: (f, k) for c, f, k in d_rows}
    changed = sorted(c for c in set(gold_map) | set(d_map) if gold_map.get(c) != d_map.get(c))
    fig = sorted(k for k in GOLD_RESULTS if abs(d_res[k] - GOLD_RESULTS[k]) > 1e-9)
    files = {"fitting_register.csv": csv_text([rows[0]] + [list(r) for r in d_rows]),
             "results.json": json.dumps(d_res), "takeoff_note.md": note_for(d_rows, d_res)}
    fails = failures(files)
    expect(f"D {flag} ({meaning}); rows changed {changed}; figures changed {fig}", fails, True)

print("== F: degenerate submissions (must fail)")
majority = [rows[0]] + [[r[0], "NONE", "REDUCER"] for r in rows[1:]]
conn_copy = (ROOT / "environment" / "input" / "connections.csv").read_text(encoding="utf-8")
F = {
    "F1 majority class (every row REDUCER/NONE)": with_rows(majority),
    "F2 instruction pasted as the note": {**gold_files(), "takeoff_note.md": (ROOT / "instruction.md").read_text(encoding="utf-8")},
    "F3 connections.csv copied as the register": {**gold_files(), "fitting_register.csv": conn_copy},
    "F4 empty workspace": {},
}
for label, files in F.items():
    expect(label, failures(files), True)

print("== N: note wording")
R, C = GOLD_RESULTS["reducer_count"], GOLD_RESULTS["coupler_count"]
ids = " and ".join(UNRESOLVED)
other = next(r[0] for r in rows[1:] if r[2] == "REDUCER")
N_pass = {
    "plain words": f"{gen.WORDS[R].capitalize()} connections need reducers and {gen.WORDS[C]} need couplers.\n\n{ids} are unresolved for now.\n",
    "label after number, digits": f"We need {R} reducer fittings plus {C} couplers.\n\nUnresolved: {', '.join(UNRESOLVED)}. Their ports must be measured.\n",
    "bulleted": f"- reducer count: {R}\n- coupler count: {C}\n\n" + "".join(f"- {u}: fitting_kind `UNRESOLVED`\n" for u in UNRESOLVED),
    "CRLF + BOM": f"﻿Reducers: {R}.\r\nCouplers: {C}.\r\n\r\n{ids} are unresolved.\r\n",
}
N_fail = {
    "wrong reducer number": (f"Reducers: {R + 1}. Couplers: {C}.\n\n{ids} are unresolved.\n", ["note_reducer_count"]),
    "coupler number in another sentence": (f"Reducers: {R}. We need couplers. There are {C}.\n\n{ids} are unresolved.\n", ["note_coupler_count"]),
    "an unresolved id missing": (f"Reducers: {R}. Couplers: {C}.\n\n{', '.join(UNRESOLVED[:-1])} are unresolved.\n", [f"note_unresolved_{UNRESOLVED[-1]}"]),
    "a non-unresolved id in between": (f"Reducers: {R}. Couplers: {C}.\n\n{UNRESOLVED[0]}, then {other}; {', '.join(UNRESOLVED[1:])} are unresolved.\n", [f"note_unresolved_{UNRESOLVED[0]}"]),
    "ids in another paragraph": (f"Reducers: {R}. Couplers: {C}. See {ids}.\n\nTwo runs are unresolved.\n", [f"note_unresolved_{c}" for c in UNRESOLVED]),
}
for label, note in N_pass.items():
    expect(f"N pass: {label}", failures({**gold_files(), "takeoff_note.md": note}), False)
for label, (note, only) in N_fail.items():
    expect(f"N fail: {label}", failures({**gold_files(), "takeoff_note.md": note}), True, only)

print(f"\nPROBLEMS: {problems}")
sys.exit(1 if problems else 0)
