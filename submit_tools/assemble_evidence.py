#!/usr/bin/env python3
"""assemble_evidence.py - build evaluations/ for the submission bundle from harbor job folders.

Usage (Windows CMD):
  py -3.12 assemble_evidence.py --task C:\\turing\\submit\\tech-b53-t9-water-system-fitting-takeoff ^
      --difficulty-job C:\\harbor-jobs\\glm-4x-day3 --solvability-job C:\\harbor-jobs\\glm-smoke-day3

What it does (and nothing else):
  1. copies the 4 trial folders of the difficulty job, unflattened, to evaluations/difficulty/r1..r4
     (sorted by trial name, case-insensitive; the mapping is printed)
  2. copies one reward-1.0 trial of the solvability job to evaluations/solvability/r1
  3. copies that run's agent/trajectory.json to solution/golden_trajectory.json (PKG-8)
  4. never copies job-level files (job config.json, lock.json, job.log, result.json)
  5. redacts the API key (the value of %OPENAI_API_KEY% and anything shaped sk-...) in every copied file
  6. reports any personal Windows path (C:\\Users\\...) left in the copied files
  7. deletes __pycache__ / .pytest_cache anywhere in the task folder
  8. prints a per-run checklist of the files the delivery format expects

Optional: --annotate adds the five result.json fields and writes verifier/reward.json and
verifier/verifier_summary.json. Use this ONLY if you do not have the team's
tools/annotate_rollout.py; the team tool is the reference.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

EXPECTED = ["agent/trajectory.json", "result.json", "config.json", "verifier/reward.txt",
            "verifier/reward.json", "verifier/ctrf.json", "verifier/test-stdout.txt"]
DIFFICULTY_ONLY = ["verifier/verifier_summary.json"]
KEY_SHAPE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def trials(job):
    out = [p for p in Path(job).iterdir() if p.is_dir() and (p / "result.json").is_file()]
    return sorted(out, key=lambda p: p.name.lower())


def reward_of(trial):
    f = trial / "verifier" / "reward.txt"
    try:
        return float(f.read_text().strip())
    except Exception:
        return None


def redact(root, key):
    changed = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        if key and len(key) >= 8:
            new = new.replace(key, "REDACTED")
        new = KEY_SHAPE.sub("sk-REDACTED", new)
        if new != text:
            p.write_text(new, encoding="utf-8", newline="")
            changed += 1
    return changed


def personal_paths(root):
    hits = []
    for p in root.rglob("*"):
        if p.is_file():
            try:
                t = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r"C:[\\/]{1,2}Users[\\/]{1,2}", t, re.I):
                hits.append(p)
    return hits


def annotate(run, difficulty):
    res_p = run / "result.json"
    res = json.loads(res_p.read_text(encoding="utf-8"))
    reward = reward_of(run)
    score_p = run / "verifier" / "score.json"
    score = json.loads(score_p.read_text(encoding="utf-8")) if score_p.is_file() else {}
    final = None
    for cand in (run / "artifacts" / "app" / "results.json", run / "artifacts" / "results.json"):
        if cand.is_file():
            try:
                final = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                final = cand.read_text(encoding="utf-8")
            break
    res.update({"model": "GLM-5.2", "overall_pass": reward == 1.0, "reward": reward,
                "final_answer": final,
                "judge": {"type": "deterministic file_check", "judge_model": None}})
    res_p.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    (run / "verifier" / "reward.json").write_text(json.dumps({"reward": reward}) + "\n", encoding="utf-8")
    if difficulty:
        items = [{"name": c["name"], "passed": c["passed"], "verifier_type": "file_check",
                  "motivation": c.get("detail", "")} for c in score.get("checks", [])]
        summary = {"reward": {"total": reward, "rubric": {"items": items}},
                   "verification_summary": {"passed": sum(i["passed"] for i in items), "total": len(items),
                                            "type_scores": {"file_check": (sum(i["passed"] for i in items) / len(items)) if items else 0.0}}}
        (run / "verifier" / "verifier_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--difficulty-job", required=True)
    ap.add_argument("--solvability-job", required=True)
    ap.add_argument("--annotate", action="store_true")
    a = ap.parse_args()
    task = Path(a.task)
    ev = task / "evaluations"
    if ev.exists():
        shutil.rmtree(ev)
    diff = trials(a.difficulty_job)
    if len(diff) != 4:
        sys.exit(f"expected 4 trials in {a.difficulty_job}, found {len(diff)}: {[p.name for p in diff]}")
    for i, t in enumerate(diff, 1):
        dst = ev / "difficulty" / f"r{i}"
        shutil.copytree(t, dst)
        print(f"difficulty/r{i}  <- {t.name}  reward {reward_of(t)}  {'CRASHED' if (t / 'exception.txt').exists() else ''}")
    solv = [t for t in trials(a.solvability_job) if reward_of(t) == 1.0 and not (t / "exception.txt").exists()]
    if not solv:
        sys.exit(f"no reward-1.0 trial in {a.solvability_job}")
    shutil.copytree(solv[0], ev / "solvability" / "r1")
    print(f"solvability/r1 <- {solv[0].name}  reward 1.0")
    shutil.copy2(solv[0] / "agent" / "trajectory.json", task / "solution" / "golden_trajectory.json")
    print("solution/golden_trajectory.json <- solvability/r1/agent/trajectory.json")

    n = redact(ev, os.environ.get("OPENAI_API_KEY", ""))
    n += redact(task / "solution", os.environ.get("OPENAI_API_KEY", ""))
    print(f"redacted key text in {n} file(s)")
    for junk in list(task.rglob("__pycache__")) + list(task.rglob(".pytest_cache")):
        shutil.rmtree(junk, ignore_errors=True)
    if a.annotate:
        for i in range(1, 5):
            annotate(ev / "difficulty" / f"r{i}", True)
        annotate(ev / "solvability" / "r1", False)
        print("annotated result.json + wrote reward.json / verifier_summary.json (fallback annotator)")

    print("\nchecklist (missing files):")
    for run in sorted(ev.glob("*/r*")):
        need = EXPECTED + (DIFFICULTY_ONLY if run.parent.name == "difficulty" else [])
        missing = [f for f in need if not (run / f).is_file()]
        has_art = (run / "artifacts").is_dir()
        print(f"  {run.relative_to(task)}: {'OK' if not missing else 'MISSING ' + ', '.join(missing)}"
              f"{'' if has_art else '  (no artifacts/ folder)'}")
    left = personal_paths(task)
    if left:
        print("\nWARNING - personal Windows paths still present in:")
        for p in left:
            print("  ", p.relative_to(task))
    key = os.environ.get("OPENAI_API_KEY", "")
    leaked = [p for p in task.rglob("*") if p.is_file() and key and len(key) >= 8
              and key.encode() in p.read_bytes()]
    print("\nKEY LEAK CHECK:", "FAILED in " + ", ".join(str(p) for p in leaked) if leaked else "clean")


if __name__ == "__main__":
    main()
