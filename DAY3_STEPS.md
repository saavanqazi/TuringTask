# Day 3: install the hardened task, check it, run the GLM battery (Windows CMD)

The first battery (`glm-4x-day2`) passed **4/4**, so the task was too easy.
`day3_package.zip` hardens it with four rules. Each one is fully written down in `takeoff_rules.md` (Rev C), and each one changes several answers at once:

| New rule | What the model has to do |
|---|---|
| **Re-routed runs (T1)** | `connections.csv` has a new `replaces` column. A replaced run is *withdrawn*: it gets no register row, no count and no pipe. |
| **Table revisions (T2)** | Five makers have revised tables with effective dates. Only the revision **in force on 15 Sep 2026** counts: one takes effect exactly on that date (in force), and others take effect later (not yet). |
| **DN sizes (T5)** | One maker (Aquaflux) prints `DN25`, `DN32` and `DN40`; the rules give the mapping to inches. |
| **Discontinued fittings (T7)** | The catalogue has `status` and `superseded_by` columns. A `DISCONTINUED` row is never picked, and each end must match on size **and** thread. |

The task now has 27 runs, 3 of them withdrawn, so 24 rows are taken off. The gold answer is 11 reducers, 3 couplers, 8 adapters, 2 unresolved and 181.5 ft of pipe.
Every value comes from `tests/generate_fixture.py`, and `tests/probe_suite.py` proves the grader (0 problems in 37 cases).

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
```

---

## Step 1: Install the Day 3 package, keeping your pinned Dockerfile (5 min)

Save `day3_package.zip` into `C:\turing\scratch\`, then:

```bat
copy /y "%TASK%\environment\Dockerfile" C:\turing\scratch\Dockerfile.pinned
cd /d C:\turing\work
rmdir /s /q tech-b53-t9-water-system-fitting-takeoff
tar -xf C:\turing\scratch\day3_package.zip
copy /y C:\turing\scratch\Dockerfile.pinned "%TASK%\environment\Dockerfile"
findstr /b "FROM" "%TASK%\environment\Dockerfile"
git status --short
```

- `findstr` must show your `FROM python:3.12-slim-bookworm@sha256:...` line.
- `git status` should list:
  - `M` for `instruction.md`, the 4 input CSV/MD data files, `submission_format.md`, `takeoff_rules.md`, the 3 `solution\files`, `tests\verifier.json` and `tests\manifest.json`;
  - `??` for `tests\generate_fixture.py`, `tests\probe_suite.py` and `tests\input_hashes.json`.

  **`Dockerfile` must NOT be in the list.**

---

## Step 2: Prove the grader on your machine (2 min)

```bat
cd /d %TASK%
C:\turing\venv312\Scripts\python tests\probe_suite.py
rmdir /s /q tests\__pycache__
fc /b tests\verifier.json tests\manifest.json
```

- The last line of the probe output must be **`PROBLEMS: 0`**.
- `fc` must say `no differences encountered`.
- The `rmdir` removes the cache folder Python creates, which must never ship.

If the probe suite errors on Windows, run it inside Docker instead and send me the output:

```bat
docker run --rm -v "%TASK%":/work -w /work python:3.12-slim-bookworm sh -c "pip install -q pydantic==2.12.5 'jsonpath-ng>=1.6,<2' 'tenacity>=9.0,<10' && python tests/probe_suite.py"
```

---

## Step 3: Oracle (about 1 min; the image is cached). It must print 1.0

```bat
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-day3 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-day3\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
```

---

## Step 4: Commit, log the changes, and write down the expected wrong readings BEFORE the battery (10 min)

```bat
cd /d C:\turing\work
git add -A
git commit -m "Day 3 hardening: withdrawn runs, table revisions, DN sizes, discontinued fittings; generator + probe suite"
```

**4a.** Open `notepad C:\turing\scratch\departures.md` and add these rows:

```markdown
| 12 | 2026-09-28 | environment/input/takeoff_rules.md | Rev B, rules T1-T8 | Rev C, T1-T10: take-off date 2026-09-15; T1 withdrawn (re-routed) runs; T2 revision in force (latest effective date on or before the take-off date, publication date ignored); T5 DN sizes mapped to inches; T7 STOCKED rows only, each end matched on size and thread | First battery glm-4x-day2 passed 4/4 (too easy, DIF-7); each rule stated in one sentence (DIF-1) | probe_suite: 10 decoys fail; glm-4x-day3 |
| 13 | 2026-09-28 | environment/input/spec_sheet.md | one table per product | effective/published-dated revisions for TJ-100, TJ-200, BJ-75, HJ-1, PV-44; new products CT-300, TJ-200, AF-40 (DN), AV-50 (DN) | Stale-authority and cross-source patterns (Standard 3.3) | oracle-day3 1.0 |
| 14 | 2026-09-28 | environment/input/components.csv | 14 ports | 20 ports | New products above | oracle-day3 1.0 |
| 15 | 2026-09-28 | environment/input/connections.csv | 16 runs, no replaces column | 27 runs with a replaces column (3 withdrawn); connection_ids assigned with seed 53, not in file order | Unit-of-analysis / state-across-steps pattern | oracle-day3 1.0 |
| 16 | 2026-09-28 | environment/input/fitting_catalog.csv | 16 rows, no status | 21 rows with status and superseded_by (2 DISCONTINUED, one listed before its replacement) | Misdirection with a disclosed tie-breaker; status derivable from a field (FIX-4) | oracle-day3 1.0 |
| 17 | 2026-09-28 | environment/input/submission_format.md, instruction.md | register = every connection; one unresolved id per paragraph | register = connections taken off; unresolved ids may be listed together; T9/T10 references; instruction mentions revisions and "catalogue" | Keep format consistent with Rev C; avoid a formatting-only failure | probe_suite N cases |
| 18 | 2026-09-28 | solution/files/*, tests/verifier.json, tests/manifest.json | hand-made gold, 6 checks | regenerated by tests/generate_fixture.py: 24 rows, 11 reducer / 3 coupler / 2 unresolved, 181.5 ft; 7 core checks (one per unresolved id) | One derivation for inputs, gold and checks (GLD-11) | gold 1.0; manifest identical |
| 19 | 2026-09-28 | tests/generate_fixture.py, tests/probe_suite.py, tests/input_hashes.json | absent | added | FIX-9, VER-24, FIX-11 | probe_suite PROBLEMS: 0 |
```

**4b.** Create the expected-wrong-readings file. The Standard (DIF-4) requires this **before** the battery runs:

```bat
notepad C:\turing\scratch\expected_wrong_readings.md
```

Paste this, then save:

```markdown
# Expected wrong readings (declared before glm-4x-day3)

| # | Wrong reading | Rows it changes | Figures it changes |
|---|---|---|---|
| W1 | Uses the retailer's listed_size_in instead of the maker's table | C-04, C-05, C-10, C-11, C-14, C-19, C-22, C-24 | coupler_count, unresolved_count, total_run_ft |
| W2 | Uses the newest revision even when it is not yet in force | C-05, C-06, C-10, C-14, C-16, C-22, C-24 | reducer_count, unresolved_count, total_run_ft |
| W3 | Uses the first revision listed for a product | C-04, C-05, C-06, C-10, C-14, C-16, C-22, C-24 | all four |
| W4 | Treats a revision effective ON 2026-09-15 as not yet in force | C-19, C-22 | none |
| W5 | Compares sizes as text (1.25 vs 1-1/4, DN32 vs 1-1/4) | C-01, C-02, C-12, C-15, C-19, C-21, C-22, C-23, C-25 | reducer_count, coupler_count |
| W6 | Requires the catalogue end order to follow from -> to | C-01, C-05, C-06, C-13, C-14, C-26 | none |
| W7 | Picks a DISCONTINUED catalogue row | C-04, C-13, C-23 | none |
| W8 | Keeps withdrawn (re-routed) runs in the register | adds C-03, C-07, C-17 | reducer_count, unresolved_count, total_run_ft |
| W9 | Matches catalogue ends on sizes without pairing each size with its thread | C-20 | none |
| W10 | Marks every port of a product unresolved when one port is unstated | C-06, C-08, C-16, C-20, C-23 | all four |
```

---

## Step 5: GLM battery on the hardened task

**5.1** Smoke run (1 attempt):

```bat
cd /d C:\turing\scratch
docker ps --format "{{.Names}}"
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; json.dump(d,open(p,'w'),indent=2); print('job_name =',d['job_name'])" glm-smoke-day3
harbor run -c glm-harbor-config.json -n 1 -k 1 -y
for /d %d in (C:\harbor-jobs\glm-smoke-day3\*) do @if exist "%d\verifier\reward.txt" (echo REWARD: & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-smoke-day3\*) do @if exist "%d\exception.txt" (echo CRASHED: & type "%d\exception.txt")
```

The smoke run only checks that the task runs; its reward can be 1.0 or 0.0. If it **crashed**, send me the text and stop.

**5.2** The 4-run battery:

```bat
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; json.dump(d,open(p,'w'),indent=2); print('job_name =',d['job_name'])" glm-4x-day3
harbor run -c glm-harbor-config.json -n 3 -k 4 -y
```

**5.3** Read the results:

```bat
for /d %d in (C:\harbor-jobs\glm-4x-day3\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-4x-day3\*) do @if exist "%d\exception.txt" echo CRASHED: %~nxd
for /d %d in (C:\harbor-jobs\glm-4x-day3\*) do @if exist "%d\verifier\score.json" (echo === %~nxd & findstr /c:"core_failures" "%d\verifier\score.json")
for /d %d in (C:\harbor-jobs\glm-4x-day3\*) do @if exist "%d\verifier\score.json" (echo === %~nxd & findstr /c:"detail" "%d\verifier\score.json")
```

---

## Send me

1. `git status --short` from step 1.
2. The `PROBLEMS:` line from step 2.
3. The oracle reward from step 3.
4. Everything step 5.3 prints: the 4 rewards, `core_failures` and the `detail` lines.

From the failing checks and details, I'll match each failed run to a wrong reading W1–W10. Then we decide:
- **1/4 or 2/4:** we stop hardening.
- **4/4:** add the next lever.
- **0/4:** check that every failure is really the model's fault.
