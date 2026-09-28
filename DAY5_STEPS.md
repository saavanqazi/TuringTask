# Day 5: stronger hardening after 4/4 (Windows CMD)

## Why

`glm-4x-day4` scored **4/4**. Together with day3's 3/4, this shows GLM passes about 80–90% of the time. Every rule was a clean one-line lookup, and a few places even pointed at the trap, so a single script solved it.

`day5_package.zip` (rules **Rev D**) does three things, keeping every rule written down and a single correct answer:

| Change | What the model now has to do |
|---|---|
| **Coaching removed** | The spec sheet no longer says "the listing describes the kit, not the port" or "the maker's table states 1". The rules lose their bold emphasis. The rules still say that the maker's table governs; they just stop pointing at the trap. |
| **Amendments vs reissues** (T2) | Every revision is marked *reissue* (replaces the table whole) or *amendment* (changes only the rows it lists; the rest carry over). So carrying rows forward is right for amendments and wrong for reissues. Revisions affected: TJ-150 Rev 2 changes the suction to 1-1/2; the BJ-75 and HJ-1 amendments; the PV-60 reissue that drops the inlet size. |
| **Site measurements** (new file `site_measurements.csv`, T4) | The owner's own measurements. One counts only for a port the table in force does **not** state, only if dated on or before 2026-09-15, and the latest one wins. It never overrides a size the maker states. Decoys: an older P1-S reading that a later one supersedes, a P2-D reading that must be ignored, a P6-S reading dated after the take-off, a spare pump that isn't in the kit, and a V3 reading dated exactly on the take-off date. |

New gold: 24 rows, 9 reducers, 6 couplers, 8 adapters, 1 unresolved (C-24), 190.5 ft.
The probe suite runs **51 cases with 0 problems**, and all **18 decoy solvers** fail, each on different rows.

---

## Steps

**1. Install, keeping your pinned Dockerfile.** Save `day5_package.zip` into `C:\turing\scratch\` first.

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
copy /y "%TASK%\environment\Dockerfile" C:\turing\scratch\Dockerfile.pinned
cd /d C:\turing\work
rmdir /s /q tech-b53-t9-water-system-fitting-takeoff
tar -xf C:\turing\scratch\day5_package.zip
copy /y C:\turing\scratch\Dockerfile.pinned "%TASK%\environment\Dockerfile"
findstr /b "FROM" "%TASK%\environment\Dockerfile"
git status --short
```

- The `FROM` line must end in `@sha256:...`.
- `git status` should show `M` for `instruction.md`, the input files, `solution\files` and `tests\*`, and `??` for the new `environment\input\site_measurements.csv`.
- `Dockerfile` must **not** appear in the list.

**2. Test the grader.** The last line must be `PROBLEMS: 0`.

```bat
cd /d %TASK%
C:\turing\venv312\Scripts\python tests\probe_suite.py
rmdir /s /q tests\__pycache__
fc /b tests\verifier.json tests\manifest.json
```

**3. Run the oracle.** It must print `1.0`.

```bat
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-day5 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-day5\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
```

**4. Commit, then update the two notes files before the battery.**

```bat
cd /d C:\turing\work
git add -A
git commit -m "Day 5 hardening: rules Rev D - amendments vs reissues, site measurements, coaching removed"
notepad C:\turing\scratch\departures.md
notepad C:\turing\scratch\expected_wrong_readings.md
```

**4a.** Add these rows to `departures.md`:

```markdown
| 23 | 2026-09-28 | environment/input/takeoff_rules.md | Rev C | Rev D: T2 revisions are reissues (replace whole) or amendments (change listed rows only), table in force = latest reissue in force + later amendments in force; T4 site measurements fill an unstated port (dated on or before the take-off date, latest wins, never override a stated size); bold emphasis removed | glm-4x-day4 scored 4/4 (too easy, DIF-7); coupled rules instead of independent ones | probe_suite 51/51; 18 decoys fail |
| 24 | 2026-09-28 | environment/input/spec_sheet.md | editorial hints after retailer quotes; revisions unlabeled | hints removed; every revision labeled reissue/amendment; TJ-150 Rev 2 amendment (suction 1-1/2); BJ-75 and HJ-1 revisions now amendments | coaching removed (INS-14); amendment pattern | oracle-day5 1.0 |
| 25 | 2026-09-28 | environment/input/site_measurements.csv (new), instruction.md | absent | owner's site log: 6 rows (P1-S twice, P2-D, P6-S after the take-off date, spare pump P7-S not in the kit, V3 on the take-off date); instruction lists the file in one line | cross-source synthesis with dated distractors (FIX-7) | probe decoys ignore_measurements, measurement_overrides, measurement_any_date, earliest_measurement fail |
| 26 | 2026-09-28 | solution/files/*, tests/verifier.json, tests/manifest.json, tests/input_hashes.json | 10 reducer / 3 coupler / 4 unresolved, 171.5 ft | regenerated: 9 reducer / 6 coupler / 1 unresolved (C-24), 190.5 ft; 7 core checks | one derivation (GLD-11) | oracle-day5 1.0 |
```

**4b.** Replace everything in `expected_wrong_readings.md` with:

```markdown
# Expected wrong readings (declared before glm-4x-day5)

| # | Wrong reading | Rows it changes |
|---|---|---|
| W1 | Uses the retailer's listed_size_in instead of the maker's table | C-04, C-05, C-09, C-10, C-11, C-13, C-14, C-19, C-22, C-24, C-25, C-27 |
| W2 | Applies every revision, including ones not yet in force | C-05, C-06, C-10, C-14, C-16, C-22, C-24 |
| W3 | Uses the first revision listed for each product | C-02, C-04, C-05, C-06, C-09, C-10, C-11, C-13, C-14, C-16, C-21, C-22, C-23, C-24, C-25, C-27 |
| W4 | Treats a revision or measurement dated ON 2026-09-15 as not counting | C-11, C-19, C-22, C-25 |
| W5 | Compares sizes as text (1.25 vs 1-1/4, DN32 vs 1-1/4) | C-01, C-02, C-12, C-15, C-19, C-21, C-22, C-23, C-25 |
| W6 | Requires the catalogue end order to follow from -> to | C-01, C-05, C-06, C-11, C-13, C-14, C-26 |
| W7 | Picks a DISCONTINUED catalogue row | C-04, C-23 |
| W8 | Keeps withdrawn (re-routed) runs in the register | adds C-03, C-07, C-17 |
| W9 | Matches catalogue ends on sizes without pairing each size with its thread | C-20 |
| W10 | Marks every port of a product unresolved when one port is unstated | C-16, C-23 |
| W11 | Fills a port a reissue does not state from an earlier revision (PV-60 3/4) | C-11, C-25 |
| W12 | Takes a discontinued row's superseded_by row though its ends do not match | C-04 |
| W13 | Treats an amendment as a whole new table (rows it omits become unstated) | C-02, C-11, C-14, C-18, C-21, C-26 |
| W14 | Ignores amendments | C-04, C-05, C-09, C-13, C-19, C-22, C-27 |
| W15 | Never uses a site measurement | C-10, C-11, C-25 |
| W16 | Lets a measurement override a size the maker states (P2-D) | C-11, C-14 |
| W17 | Uses a measurement dated after the take-off date (P6-S) | C-24 |
| W18 | Uses the earliest measurement instead of the latest (P1-S) | C-10 |

History: glm-4x-day3 3/4 (failed run matched W1); glm-4x-day4 4/4.
```

**5. The 4-run battery.**

```bat
cd /d C:\turing\scratch
docker ps --format "{{.Names}}"
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; json.dump(d,open(p,'w'),indent=2); print('job_name =',d['job_name'])" glm-4x-day5
harbor run -c glm-harbor-config.json -n 3 -k 4 -y
```

**6. Read the results.**

```bat
for /d %d in (C:\harbor-jobs\glm-4x-day5\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-4x-day5\*) do @if exist "%d\exception.txt" echo CRASHED: %~nxd
for /d %d in (C:\harbor-jobs\glm-4x-day5\*) do @if exist "%d\verifier\score.json" (echo === %~nxd & findstr /c:"detail" "%d\verifier\score.json")
```

**Send me:** the `PROBLEMS:` line, the oracle reward, and everything step 6 prints.

| Result | Next |
|---|---|
| **1/4 or 2/4** | Stop hardening and move to packaging. |
| 3/4 | Decide with your lead. |
| 4/4 | Another round. |
| 0/4 | I check every failed run for fairness before anything else. |
