"""make_c1_package.py - assemble the submission package like the accepted reference, on the trainer's machine.

    python make_c1_package.py <task dir> <harbor jobs dir> <output dir>

Copies the task (without its old evaluations/ and caches) to <output dir>/stage/<task name>, then builds
  evaluations/oracle                       <- jobs/oracle-c1-h6/<trial>
  evaluations/stability/repeat-01..03      <- jobs/oracle-c1-h6-stab/<3 trials>
  evaluations/glm-5.2/rN/difficulty/rN     <- jobs/glm-c1-h6/<4 trials, by start time>
  evaluations/harbor_check                 <- <task>/evaluations/harbor_check, only if present (the platform's check output)
It refuses to package if a run is missing, an oracle/stability reward is not 1.0, the trials were not all on the
same task checksum, the mirror or instruction sha is off, a text file has CRLF, or anything looks like a secret.
The judge endpoint URL is replaced by ${OPENAI_BASE_URL} in the copied run records. Writes <output dir>/<task name>.zip.
"""
import hashlib, json, os, re, shutil, sys, zipfile, filecmp
from pathlib import Path

TASK, JOBS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
NAME = TASK.name
STAGE = OUT / "stage" / NAME
problems = []

def trials(job):
    d = JOBS / job
    ts = [p for p in d.iterdir() if p.is_dir() and (p / "result.json").exists()] if d.exists() else []
    return sorted(ts, key=lambda p: json.loads((p / "result.json").read_text(encoding="utf-8")).get("started_at") or "")

def reward(t):
    p = t / "verifier" / "reward.txt"
    return p.read_text().strip() if p.exists() else "missing"

def checksum(t):
    return json.loads((t / "result.json").read_text(encoding="utf-8")).get("task_checksum")

def copy(src_trial, dst, rels):
    for rel in rels:
        s = src_trial / rel
        if s.is_dir():
            shutil.copytree(s, dst / rel, dirs_exist_ok=True)
        elif s.exists():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / rel)
        else:
            problems.append(f"missing {src_trial.name}/{rel}")

# 0. the task itself must be consistent
man = json.loads((TASK / "tests/manifest.json").read_text(encoding="utf-8"))
if man["instruction_sha256"] != hashlib.sha256((TASK / "instruction.md").read_bytes()).hexdigest():
    problems.append("instruction_sha256 does not match instruction.md")
for a, b in [("instruction.md", "environment/_app/instruction.md"), ("task.toml", "environment/_app/task.toml"),
             ("tests/manifest.json", "environment/_app/tests/manifest.json")]:
    if not filecmp.cmp(TASK / a, TASK / b, shallow=False):
        problems.append(f"{a} differs from {b}")
for need in ("README.md", "review.csv", "consistency/requirements.json", "consistency/mutations.json",
             "consistency/readers.json", "consistency/envelope.json", "consistency/shortcut_audit.md"):
    if not (TASK / need).exists():
        problems.append(f"missing {need}")
if (TASK / "consistency/mutations.json").exists():
    m = json.loads((TASK / "consistency/mutations.json").read_text(encoding="utf-8"))
    if not m.get("rubric_validation_summary", {}).get("cases"):
        problems.append("consistency/mutations.json has no rubric validation yet - run consistency_llm.py first")

# 1. stage the task
if STAGE.exists():
    shutil.rmtree(STAGE)
shutil.copytree(TASK, STAGE, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "evaluations", "*.zip"))

# 2. evaluations (a harbor_check folder from the platform, if you have put one in the task, is carried over as is)
ev = STAGE / "evaluations"
if (TASK / "evaluations" / "harbor_check").exists():
    shutil.copytree(TASK / "evaluations" / "harbor_check", ev / "harbor_check")
orc, stab, glm = trials("oracle-c1-h6"), trials("oracle-c1-h6-stab"), trials("glm-c1-h6")
if len(orc) != 1: problems.append(f"oracle-c1-h6 has {len(orc)} trials, expected 1")
if len(stab) != 3: problems.append(f"oracle-c1-h6-stab has {len(stab)} trials, expected 3")
if len(glm) != 4: problems.append(f"glm-c1-h6 has {len(glm)} trials, expected 4")
VER = ["verifier/golden_trajectory.json", "verifier/reward.json", "verifier/reward.txt", "verifier/snapshots",
       "verifier/test-stdout.txt", "verifier/verifier_summary.json"]
for t in orc[:1]:
    copy(t, ev / "oracle", ["agent/oracle.txt", "agent/trajectory.json", "artifacts/manifest.json", "config.json", "lock.json",
                           "result.json", "trial.log"] + VER)
for i, t in enumerate(stab[:3], 1):
    copy(t, ev / "stability" / f"repeat-{i:02d}", ["agent/oracle.txt", "agent/trajectory.json", "config.json", "result.json"] + VER)
for i, t in enumerate(glm[:4], 1):
    copy(t, ev / "glm-5.2" / f"r{i}" / "difficulty" / f"r{i}", ["agent/opencode.txt", "agent/trajectory.json", "result.json", "trial.log",
                                                              "verifier/reward.json", "verifier/test-stdout.txt"])
for t in orc + stab:
    if reward(t) not in ("1.0", "1"):
        problems.append(f"{t.parent.name}/{t.name} reward {reward(t)}, expected 1.0")
sums = {checksum(t) for t in orc + stab + glm}
if len(sums) != 1:
    problems.append(f"runs are on different task checksums: {sorted(map(str, sums))}")
glm_rewards = [reward(t) for t in glm]

# 3. hygiene: CRLF, secrets, endpoint
base = os.environ.get("OPENAI_BASE_URL", "")
key = os.environ.get("OPENAI_API_KEY", "")
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|pplx-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9_\-\.]{20,})")
TEXT = {".md", ".json", ".toml", ".py", ".sh", ".txt", ".csv", ".log", ".html", ".cfg", ".ini", ".yaml", ".yml"}
for p in STAGE.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in TEXT:
        continue
    b = p.read_bytes()
    rel = p.relative_to(STAGE).as_posix()
    if not rel.startswith("evaluations/") and b"\r\n" in b:
        problems.append(f"CRLF line endings in {rel}")
    s = b.decode("utf-8", errors="ignore")
    if base and base in s and rel.startswith("evaluations/"):
        s = s.replace(base, "${OPENAI_BASE_URL}")
        p.write_bytes(s.encode("utf-8"))
    if key and key in s:
        problems.append(f"API key literal found in {rel}")
    for mt in SECRET.findall(s):
        problems.append(f"secret-like string in {rel}: {mt[:8]}...")

if problems:
    print("NOT PACKAGED:")
    for x in problems:
        print("  -", x)
    sys.exit(1)

# 4. zip with the task folder at the top, forward slashes
zp = OUT / f"{NAME}.zip"
if zp.exists():
    zp.unlink()
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(STAGE.rglob("*")):
        if p.is_file():
            z.write(p, f"{NAME}/{p.relative_to(STAGE).as_posix()}")
n = sum(1 for _ in STAGE.rglob("*") if _.is_file())
print(f"PACKAGED {zp} ({n} files)")
print("  oracle", reward(orc[0]), "| stability", [reward(t) for t in stab], "| glm-5.2", glm_rewards, "| checksum", next(iter(sums))[:8])
