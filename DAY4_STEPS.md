# Day 4: second hardening round (Windows CMD)

## Why

The `glm-4x-day3` battery scored **3/4** (1.0, 0.0, 1.0, 1.0).

The failed run was `dy4QzNT`. It took the TJ-150 discharge size from the retailer's listing (1-1/4) instead of the maker's table (1), which changed C-14 (COUPLER instead of REDUCER) and C-11 (NONE instead of AD-1N-34B). That is a **MODEL** failure matching W1, so it is real difficulty.

3/4 is inside Turing's band, but your lead says only 1/4 or 2/4 is safe, so we harden once more. Re-running the same battery until it happens to show 2/4 would be cherry-picking, and that isn't allowed.

## What changed in `day4_package.zip`

Two coupled changes. Each is stated in the rules or data in plain words:

| Change | Rule | Effect |
|---|---|---|
| PV-60 has a **Rev B, in force since 2026-04-01, that no longer states the inlet size** | T2 now says: "a port the revision in force does not state is not stated, whatever an earlier revision said" | C-11 and C-25 become UNRESOLVED. Carrying Rev A's `3/4` forward is the trap. |
| Discontinued `RD-114-1-B` now names a successor, `RD-114-34-B`, **whose ends are different** | T7 already says the successor "is selected only if it matches the connection itself" | C-04 stays `NONE`. Picking the successor is the trap. |

New gold: 24 rows, 10 reducers, 3 couplers, 7 adapters, 4 unresolved (C-25, C-11, C-10, C-24), 171.5 ft.
The probe suite runs 45 cases with **0 problems**, and all 12 decoy solvers fail.

---

## Steps

**1. Install, keeping your pinned Dockerfile.** Save `day4_package.zip` into `C:\turing\scratch\` first, then:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
copy /y "%TASK%\environment\Dockerfile" C:\turing\scratch\Dockerfile.pinned
cd /d C:\turing\work
rmdir /s /q tech-b53-t9-water-system-fitting-takeoff
tar -xf C:\turing\scratch\day4_package.zip
copy /y C:\turing\scratch\Dockerfile.pinned "%TASK%\environment\Dockerfile"
findstr /b "FROM" "%TASK%\environment\Dockerfile"
git status --short
```

- The `FROM` line must end in `@sha256:...`.
- `git status` should show `M` only for:
  - `spec_sheet.md`, `fitting_catalog.csv` and `takeoff_rules.md`;
  - the 3 `solution\files`;
  - `tests\verifier.json`, `tests\manifest.json`, `tests\input_hashes.json`, `tests\generate_fixture.py` and `tests\probe_suite.py`.

  `Dockerfile` must **not** be listed.

**2. Test the grader.** The last line must be `PROBLEMS: 0`.

```bat
cd /d %TASK%
C:\turing\venv312\Scripts\python tests\probe_suite.py
rmdir /s /q tests\__pycache__
fc /b tests\verifier.json tests\manifest.json
```

**3. Run the oracle.** It must print `1.0`.

```bat
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-day4 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-day4\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
```

**4. Commit, then update the two notes files BEFORE the battery.**

```bat
cd /d C:\turing\work
git add -A
git commit -m "Day 4 hardening: PV-60 Rev B withdraws inlet size; discontinued reducer names a non-matching successor"
notepad C:\turing\scratch\departures.md
notepad C:\turing\scratch\expected_wrong_readings.md
```

**4a.** In `departures.md`, add these rows:

```markdown
| 20 | 2026-09-28 | environment/input/spec_sheet.md, takeoff_rules.md | PV-60 Rev A only; T2 "replaces the earlier table whole" | PV-60 Rev B (effective 2026-04-01) states no inlet size; T2 adds "a port the revision in force does not state is not stated, whatever an earlier revision said" | glm-4x-day3 scored 3/4 (run dy4QzNT failed on W1, MODEL); lead: only 1-2/4 safe. Clarifying sentence keeps the answer single (GLD-5) | probe_suite 45/45; decoy carry_forward fails on C-11, C-25 |
| 21 | 2026-09-28 | environment/input/fitting_catalog.csv | RD-114-1-B DISCONTINUED, no successor | RD-114-1-B superseded_by RD-114-34-B (STOCKED, different ends) | T7 already states the successor is selected only if it matches; tests reading it | decoy follow_superseded fails on C-04 |
| 22 | 2026-09-28 | solution/files/*, tests/verifier.json, tests/manifest.json, tests/input_hashes.json | 11 reducer / 3 coupler / 2 unresolved, 181.5 ft | regenerated: 10 reducer / 3 coupler / 4 unresolved (C-25, C-11, C-10, C-24), 171.5 ft; 9 core checks | one derivation (GLD-11) | oracle-day4 1.0 |
```

**4b.** Replace everything in `expected_wrong_readings.md` with this, then save:

```markdown
# Expected wrong readings (declared before glm-4x-day4)

| # | Wrong reading | Rows it changes | Figures it changes |
|---|---|---|---|
| W1 | Uses the retailer's listed_size_in instead of the maker's table | C-04, C-05, C-10, C-11, C-14, C-19, C-22, C-24, C-25 | all four |
| W2 | Uses the newest revision even when it is not yet in force | C-05, C-06, C-10, C-14, C-16, C-22, C-24 | reducer_count, unresolved_count, total_run_ft |
| W3 | Uses the first revision listed for a product | C-04, C-05, C-06, C-10, C-11, C-14, C-16, C-22, C-24, C-25 | all four |
| W4 | Treats a revision effective ON 2026-09-15 as not yet in force | C-19, C-22 | none |
| W5 | Compares sizes as text (1.25 vs 1-1/4, DN32 vs 1-1/4) | C-01, C-02, C-12, C-15, C-19, C-21, C-22, C-23 | reducer_count, coupler_count |
| W6 | Requires the catalogue end order to follow from -> to | C-01, C-05, C-06, C-13, C-14, C-26 | none |
| W7 | Picks a DISCONTINUED catalogue row | C-04, C-13, C-23 | none |
| W8 | Keeps withdrawn (re-routed) runs in the register | adds C-03, C-07, C-17 | reducer_count, unresolved_count, total_run_ft |
| W9 | Matches catalogue ends on sizes without pairing each size with its thread | C-20 | none |
| W10 | Marks every port of a product unresolved when one port is unstated | C-06, C-08, C-16, C-20, C-23 | all four |
| W11 | Carries a size forward from an earlier revision when the revision in force does not state it | C-11, C-25 | reducer_count, unresolved_count, total_run_ft |
| W12 | Takes a discontinued row's superseded_by row even though its ends do not match | C-04 | none |

Earlier battery for reference: glm-4x-day3 (before this round) scored 3/4; the failed run dy4QzNT matched W1 on C-14 and C-11.
```

**5. The 4-run battery.** No smoke run is needed this time: the task's structure hasn't changed since the day3 smoke run passed.

```bat
cd /d C:\turing\scratch
docker ps --format "{{.Names}}"
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; json.dump(d,open(p,'w'),indent=2); print('job_name =',d['job_name'])" glm-4x-day4
harbor run -c glm-harbor-config.json -n 3 -k 4 -y
```

**6. Read the results.**

```bat
for /d %d in (C:\harbor-jobs\glm-4x-day4\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-4x-day4\*) do @if exist "%d\exception.txt" echo CRASHED: %~nxd
for /d %d in (C:\harbor-jobs\glm-4x-day4\*) do @if exist "%d\verifier\score.json" (echo === %~nxd & findstr /c:"detail" "%d\verifier\score.json")
```

**Send me:** the `PROBLEMS:` line, the oracle reward, and everything step 6 prints.

## What happens next

| Result | Next step |
|---|---|
| **1/4 or 2/4** | Done hardening. Move on to packaging: the evidence folders, `annotate_rollout.py`, README, `review.csv`, then the Delivery Gate. |
| 3/4 | Decide with your lead: submit as an attempt, or one more round. |
| 4/4 | Another round. |
| 0/4 | I check every failed run to make sure each one is really the model's mistake, not a task problem. |
