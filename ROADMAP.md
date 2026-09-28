# Roadmap: `tech-b53-t9-water-system-fitting-takeoff`

This is the phase-by-phase plan for turning the mined package into a deliverable non-connector Harbor task.
It is built from four sources: your pasted QC brief, the **Non-Connector Task Standard v2 (2026-09-04)**, **Shannon Task QC North Star**, and **Trainer Guidelines**.
Identifiers such as `INS-1`, `VER-17` and `E4` refer to the Non-Connector Task Standard.

---

## 0. What this task is (Stage 1.3 understanding paragraph, reusable as the README opening)

A homeowner is putting in a house water system: three storage tanks, four jet pumps and three pressure vessels, with 16 pipe runs between their ports. Before ordering, they want a fitting take-off. For each connection the agent has to:

1. Read the size of each of the two ports from the **manufacturer's table** (`spec_sheet.md`), not from the retailer's `listed_size_in` column in `components.csv`.
2. Read each port's thread (NPT or BSP) from `components.csv`.
3. Classify the connection with rules T2 → T4, in order:
   - `UNRESOLVED` if the maker states no size for one of its ports,
   - otherwise `ADAPTER` if the threads differ,
   - otherwise `REDUCER` if the sizes differ,
   - otherwise `COUPLER`.
4. Pick the catalogue row whose two ends match the two ports in either order, comparing sizes numerically (`1.25` = `1-1/4`). If no row matches, the fitting is `NONE` and the kind still stands.

The deliverables are:

- `fitting_register.csv`: one row per connection, in the input file's order.
- `takeoff_note.md`: prose giving the reducer and coupler counts, and naming the UNRESOLVED connection.
- `results.json`: the three counts plus `total_run_ft`, which leaves out unresolved runs.

### Traps already in the mined data (seed for the DIF-4 "expected wrong readings")

| # | Wrong reading | Rows it changes |
|---|---|---|
| W1 | Trusts the retailer's `listed_size_in` instead of the maker's table | C-03 (becomes a reducer instead of UNRESOLVED), C-04 (becomes a coupler), C-09 (adapter row becomes NONE); counts and total also change |
| W2 | Compares sizes as text (`1.25` ≠ `1-1/4`, `1.0` ≠ `1`) | C-07, C-08, C-14, C-16 lookups |
| W3 | Requires the catalogue's end order (larger end first) to match the connection's from→to order | C-05, C-14, C-15 |
| W4 | Treats "no catalogue row" as UNRESOLVED, or drops the kind | C-06 (should be `NONE`, `REDUCER`) |
| W5 | Counts adapters in a count, or subtracts nothing for UNRESOLVED from the total | `results.json` |
| W6 | Reads "the component" in T2 as the whole pump (TJ-100), not the port row `P1-S` | C-01 and C-15 wrongly become UNRESOLVED (**this is an ambiguity to fix, not a trap**, see Phase 2) |

### Baseline I measured (Stage 1.4.a, engine run locally on Python 3.12)

| Submission | Reward | Checks passed |
|---|---|---|
| Mined gold (`solution/files/`) | **1.0** | 13/13 |
| Empty workspace | 0.0 | 0/13 |
| Naive "listing-lure" solver (W1) with the gold note | 0.0 | 10/13 (fails `register_table`, `register_table_trap_c03` and `results_figures`) |

I re-derived every one of the 16 gold rows by hand. All are correct: 9 REDUCER, 2 COUPLER, 4 ADAPTER, 1 UNRESOLVED, and `total_run_ft` = 133.5 − 9 = **124.5**.

**Honest prediction:** the task has 16 rows, and T1–T8 spell out the method almost step by step. GLM-5.2 will very likely pass it **4/4** as it stands. Hardening (Phase 5) is the real job.

---

## Conflicts between the documents: decided

| # | Conflict | Decision |
|---|---|---|
| K1 | **Pass band.** Trainer Guidelines say 5 runs and ≤50%. The brief and the Standard (Q1) say 4 runs, 1–3 of 4 passing. The client's script still fails a task at >2 passes. | **Lead:** 1/4 or 2/4 is safe. 3/4 may or may not be accepted, but we can try submitting it. **So: stop hardening at 1/4 or 2/4. If you land on 3/4, you may submit it, but expect a possible rejection.** |
| K2 | **Checks file.** The brief says rewrite `verifier.json` as `manifest.json`; the Standard v2 ships `verifier.json`. | **Lead: ship both, byte-identical.** Nothing is rewritten or renamed. The engine, `score.py` and `test_outputs.py` load `verifier.json`, as the Standard says. `tests/manifest.json` exists only because the upload validator rejects a bundle without it ("tests/manifest.json must contain a nonempty native assertion list"). Our generator writes both files in the same run so they cannot drift, and the zip preflight fails if they differ (Phases 5b, 6 and 8). |
| K3 | **Golden trajectory.** The brief calls it the "required Oracle asset". PKG-8 says it must be a **real model run scoring 1.0, never the oracle**. The mined `solution/golden_trajectory.json` is a synthetic list of 10 `printf` commands. | Replace it with the `agent/trajectory.json` of a passing GLM run (Phase 8), and make `solve.sh`'s emit step tolerate the ATIF format. |
| K4 | **"Secondary" verifiers.** This package has no `"category": "secondary"`. It has `metadata.tag: "incidental"`, 6 of 13 checks, all on the note. | **Decided:** treat `incidental` as secondary; nothing non-core ships. The note's facts become **core checks with loose matching** (exact spec in Phase 3, step 4). Delete `note_exists`, `note_prose_floor` (and remove the "sixty words" ask) and both `*_exactly_one` hedge checks. |
| K7 | **`result.json` fields.** The gate wants `model`, `overall_pass`, `reward`, `final_answer` and judge provenance. | **Lead:** harbor does not write them. Harbor's native `result.json` only has the trial identity, config, agent and environment setup, `agent_result`, `exception_info`, timestamps, and `verifier_result` with a bare `rewards` object. **`tools/annotate_rollout.py`** adds five fields without touching harbor's own. The same script also derives `verifier/reward.json` and `verifier/verifier_summary.json` from harbor's `reward.txt` and `score.json` (harbor writes neither). See Phase 8. |
| K5 | **Oracle evidence.** The brief says ship none. The Standard says Turing adds `oracle/`. | Either way, **delete** `evaluations/oracle/` and `evaluations/nop/`. |
| K6 | **Stability.** | Ship no `stability/` folder. Delivery Gate finding R3 is expected; mark it reviewed with "Turing runs stability". |

---

## Phase 0: One-time setup on your Windows machine, using CMD (about half a day)

You can do the whole job from a normal **CMD** window. WSL is not needed.
The evidence: the mining team's oracle run for this exact package was done with harbor on native Windows. Its `evaluations/oracle/result.json` shows a `C:\Users\...` task path, a `docker` environment, reward 1.0 and no exception.
Every command below is CMD syntax. Appendix A lists the differences from the Linux commands in the guides.

1. **Security first.** Your task folder contains a `glm` env file holding your key. **Move it out of `tech-b53-…\` right now.** If it gets zipped, the key ships to the client (TOML-10 and SEC-1 are both blocking). Never commit it.
2. **Docker Desktop.** Install it with the default WSL2 backend. That is only Docker's engine; you never open a WSL shell. Start Docker Desktop, then in CMD run:

   ```bat
   docker run --rm hello-world
   ```

   - This task's image is `python:3.12-slim-bookworm`, so **no `benchmark-base` / gcloud is needed**. That image is for connector tasks only.
3. **Python and harbor.** Install Python 3.12 from python.org and tick "Add to PATH". Then run:

   ```bat
   py -3.12 -m pip install uv
   py -3.12 -m uv tool install harbor
   harbor --version
   ```

   - Expect 0.20.0 or newer. If `harbor` is not found, add `%USERPROFILE%\.local\bin` to PATH and open a new CMD.
   - The vendored engine (`tests\rl_world_verifiers\*.pyc`) is **Python 3.12 bytecode**. Any local probe script must run with `py -3.12`; 3.11 fails with "bad magic number".
4. **Key file.** CMD cannot `source` a file, so make a batch file **outside the task folder**, e.g. `%USERPROFILE%\.config\harbor\harbor-env.cmd`:

   ```bat
   @echo off
   set "OPENAI_API_KEY=sk-...your key..."
   set "GLM_API_KEY=%OPENAI_API_KEY%"
   set "OPENAI_BASE_URL=http://34.41.10.8:4000/v1"
   set "JUDGE_MODEL=openai/glm-5.2"
   set "PYTHONUTF8=1"
   ```

   Load it in every new CMD window with `call "%USERPROFILE%\.config\harbor\harbor-env.cmd"`, then run the key check:

   ```bat
   curl -s -i "%OPENAI_BASE_URL%/models" -H "Authorization: Bearer %OPENAI_API_KEY%" | findstr /b HTTP
   ```

   Expect `HTTP/1.1 200 OK`; `401` means a wrong key or URL. Don't use `setx` for the key: that writes it permanently into your user environment.
5. **Paths without your name or spaces.** Put everything under `C:\turing\` and write jobs to `C:\harbor-jobs`. Harbor writes the full task path into every `result.json` and `config.json`, and those get shipped. The mined oracle folder leaked "C:\Users\Syed Raza\Downloads\…" exactly this way. Spaces in paths also break unquoted CMD arguments.

   ```
   C:\turing\
     mined\tech-b53-…\     pristine copy: never edit (the "mined version" for PKG-2)
     work\tech-b53-…\      the package you edit and zip
     scratch\              departures log, probes, decoys, job copies, glm-harbor-config.json
     venv312\              Python 3.12 venv for local probes
   C:\harbor-jobs\         harbor -o / jobs_dir
   ```

6. **GLM config.** Create `C:\turing\scratch\glm-harbor-config.json` from Trainer Guidelines §1.9, with these changes:
   - `"jobs_dir": "C:/harbor-jobs"`.
   - `"n_attempts": 4`.
   - `"tasks": [{"path": "C:/turing/work/tech-b53-t9-water-system-fitting-takeoff"}]`.

   Use forward slashes inside the JSON, or escape each backslash as `\\`. Keep `${OPENAI_API_KEY}` as written: harbor expands it, not CMD.
   **Always use the config file on CMD, never the inline `--ak '{json}'` form.** CMD does not treat single quotes as quotes, so that JSON gets mangled.
7. **Line endings: the biggest Windows risk.** Every file must stay **LF, UTF-8, no BOM** (FIX-10).
   - `test.sh` or `solve.sh` saved with CRLF breaks inside the Linux container (`$'\r': command not found`), and the oracle fails.
   - CRLF in an input file changes its hash and breaks the fixture rule.

   Set these up once:

   ```bat
   git config --global core.autocrlf false
   ```

   - In `C:\turing\work`, add a `.gitattributes` containing `* -text`, so Git stores bytes exactly as they are and never converts line endings (it stays outside the zip).
   - In VS Code, set `"files.eol": "\n"`.
   - Don't edit task files in plain Notepad unless it shows "Unix (LF)" in the status bar.
8. **Python venv for local probes** (quote the version specifiers, because `<` and `>` are redirection in CMD):

   ```bat
   py -3.12 -m venv C:\turing\venv312
   C:\turing\venv312\Scripts\pip install "pydantic==2.12.5" "jsonpath-ng>=1.6,<2" "tenacity>=9.0,<10" "pytest==8.4.1"
   ```

9. **Team tooling.** Get the team scripts from your lead: `tools\annotate_rollout.py`, the zip preflight and the review form link. They are **not** in the downloaded package, and they stay **outside** the task folder.
10. **QC platform.** Sign in to the Shannon QC platform with your `@turing-gpt-git.com` account. Check that the header shows *glm access ready*.

**Exit criteria:**
- `hello-world` works.
- The curl check shows `200`.
- `harbor --version` is ≥ 0.20.0.
- The key lives only in `harbor-env.cmd`, outside the task folder and outside git.
- `.gitattributes` contains `* -text`, so Git never converts line endings.

---

## Phase 1: Intake, inventory and baseline (Stage 1, about 1 hour)

1. **Inventory (1.2).** Record the file list of the mined package into `C:\turing\scratch\departures.md`, e.g. with `dir /s /a-d C:\turing\mined\tech-b53-t9-water-system-fitting-takeoff > C:\turing\scratch\mined_inventory.txt`. That list is the "mined version".
   - All five core components are present: `task.toml`, `instruction.md`, `environment/`, `solution/`, `tests/`.
2. **Understanding paragraph (1.3).** Use §0 above.
3. **Complexity measurement (1.4).**
   - **Fixture:** 14 ports, 16 connections, 16 catalogue rows and 10 products.
   - **Verifier:**
     - 3 existence checks: `register_exists`, `results_exists`, `note_exists`.
     - 1 header regex.
     - 2 table checks: C-03 is split out on its own.
     - 1 closed JSON object.
     - 6 note-prose regexes.
   - **Reward shape:** two-tier. Any core failure scores 0. Incidental checks add weight.
4. **Oracle, as mined.** Run it on your machine and confirm it scores 1.0, so the setup is known-good before you change anything:

   ```bat
   call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
   set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
   harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% ^
     --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% -o C:\harbor-jobs ^
     --job-name oracle-b53t9-mined -n 1 -y
   for /d %d in (C:\harbor-jobs\oracle-b53t9-mined\*) do @type "%d\verifier\reward.txt"
   ```

   The last line should print `1.0`. In CMD, `^` continues a line (bash uses `\`). The `for` line replaces bash's `cat …/*/…`; inside a `.cmd` file, write `%%d` instead of `%d`.
   There is no judge in this task, so the `--ve` flags are unused but harmless.

5. **Departures log (1.7).** Start it now. Every later change gets one line: file, what it was, what it is now, and why.

---

## Phase 2: Picky-reader review (brief Step 4, Stages 2 and 4.x, about 2–3 hours)

This is the highest-value step. The findings below are already checked against the files. Confirm them yourself; QC requires that a human looked.

### 2a. Guesses and ambiguities (every one is a defect, never a difficulty knob)

| ID | Finding | Fix |
|---|---|---|
| A1 | T2: "every connection touching **that component**". It is not clear whether this means the port row (`P1-S`) or the whole product (TJ-100, including `P1-D`). The gold uses the port row. The other reading flips C-01 and C-15. | Rewrite T2 to say it means the `component_id` whose port the maker leaves unstated, and that other ports on the same product are unaffected. |
| A2 | T8: "a row carrying ADAPTER is counted by **neither**", but there are three counts. | Change "neither" to "none of them". |
| A3 | T5 does not say whether a catalogue row's `kind` must equal the T4 kind. It is harmless today because only adapters mix threads, but it will matter once hardening adds rows. | Add one sentence stating it. |
| A4 | `submission_format.md` has no stated rounding or format for `total_run_ft` beyond "plain number". The verifier tolerance is 0.01. | State "to one decimal place, or exact". |

### 2b. Leakage and realism (INS-8, INS-9, INS-11, INS-13, INS-1)

- **Template residue.** The block after `---` has to go:
  - **INS-1 (illegal):** "Writing those files … must be your final action; confirm each one exists before you answer."
  - **INS-13:** "Working environment" meta-lines.
  - A duplicate deliverable list.
- **INS-15.** Deliverables must be named once, as **absolute `/app/...` paths in backticks**, spelled identically in the instruction, `task.toml` artifacts, `verifier.json` and `solution/files/`.
- **Verifier-shaped format file.** `submission_format.md`'s note section reads like a regex spec ("no other connection's identifier and no other `fitting_kind` token may stand between…"). North Star says real users don't write this.
  - Plan: rewrite it as a short, natural contract.
  - The note's graded facts become "state the reducer and coupler counts; name each unresolved connection and say it is unresolved".
  - The verifier then does tolerant matching on those facts only.
- **No leaked answers.** The instruction states no counts or totals. The field names `fitting_kind` and `UNRESOLVED` are the domain vocabulary, not a hint. OK.

### 2c. Verifier coverage, forward and backward (North Star 2a–2c)

**Forward: my list from the instruction, mapped to the checks.**

| Ask | Check(s) that cover it | Gap? |
|---|---|---|
| Register exists | `register_exists` | Fold into content check (VER-21) |
| Register header, stated "exactly" | `register_header` | OK |
| Correct `fitting_id` and `fitting_kind` per connection, in order, none missing or extra | `register_table` + `register_table_trap_c03` | Merge into one (VER-26: one decision charged once) |
| Counts and total in `results.json`, closed key set | `results_figures` | OK |
| Note: reducer and coupler counts stated | `note_reducer`, `note_coupler`, `*_exactly_one` (all *incidental*) | **Must become core or be removed with the ask** (K4) |
| Note: name the UNRESOLVED connection | `note_unresolved` (core) | Simplify the regex (O14) |
| Note ≥ 60 words | `note_prose_floor` (incidental) | Drop the check and the word-count ask. It is an unprovable quality ask with no business value. |

**Backward:** no verifier grades something the prompt never asked for. `results_exists` is redundant with `results_figures`.

### 2d. Package defects to log as departures (PKG-14 template defects)

| Where | Defect | Rule |
|---|---|---|
| **Every text file (39)** | **CRLF line endings.** Under bash, `solve.sh` stops at `set -euo pipefail` and writes nothing, and `test.sh`'s continuation lines break too. Harbor on Windows still scored the mined oracle 1.0 (it appears to cope with the CRLF scripts), but plain Linux bash does not, and the client replays the oracle on Linux. Converted to LF on Day 1 (see `DAY1_STEPS.md` step 6). | FIX-10, HAR-10 |
| `task.toml` | `artifacts = []` | TOML-4 |
| `task.toml` | `network_mode = "public"` with no judge; should be `"no-network"` | ENV-4 |
| `task.toml` | `schema_version = "1.3"`; check that it loads under your harbor version | TOML-1 |
| `environment/Dockerfile` | Base image not pinned by digest; apt packages unpinned; no `.dockerignore` | ENV-3, ENV-8 |
| `tests/test.sh` | Runs pytest from `/app`, not `--rootdir=/tests`. No `-I` or `-p no:cacheprovider`. `reward.txt` is empty if `score.py` crashes. Errored checks are not separated from failed ones. | HAR-9, EXP-8, HAR-1, HAR-6 |
| `solution/golden_trajectory.json` | Synthetic, not a model run | PKG-8 |
| `consistency/` (top level) | Not in the allowed tree | PKG-1 |
| `evaluations/oracle/`, `evaluations/nop/` | Not allowed. Also contain a personal Windows user path. | EVD-1, TOML-10 |
| No fixture generator, no input hashes, no discrimination harness | — | FIX-9, FIX-11, VER-24 |

**Exit criteria:** a written guess list, a forward/backward table and a defects list are all in `scratch/`.

---

## Phase 3: Hygiene fixes, without changing difficulty (about half a day)

The goal is a **clean, fair, 1.0-oracle package** before any GLM run, so the first battery measures the task and not template defects.

1. **`instruction.md`.** Rewrite it as about 100–150 words of natural voice, following Standard Stage 5:
   - One sentence per input file.
   - The three deliverables as `/app/...` paths.
   - Which source governs, e.g. "the makers' tables govern over the retailer's listing". That is a disclosed tie-breaker, not a leak.
   - Points to `/app/input/submission_format.md` for layout.
   - No template block, no "final action", no step-by-step recipe.
2. **`submission_format.md`.** Make it natural:
   - Keep the exact header and enum literals, stated as case-sensitive (INS-4).
   - Keep the JSON key set and types.
   - Make the note requirements a short plain list.
   - Mark examples as shape-only placeholders that cannot be real answers (INS-17). `C-00` is fine.
3. **`takeoff_rules.md`.** Apply fixes A1–A3.
4. **`verifier.json`.**
   - Delete every incidental check.
   - Merge `register_table_trap_c03` into `register_table`.
   - Fold `register_exists` and `results_exists` into content checks.
   - The note checks, all **core**:

     | Check | Passes when (case-insensitive) | Fails on (breaking suite) |
     |---|---|---|
     | `note_reducer` | "reducer" or "reducers" appears in the same sentence as the reducer count, written as digits (`9`, `9.0`) or as a word (`nine`), in either order | wrong number, number missing, label missing |
     | `note_coupler` | same as above, for "coupler(s)" and the coupler count | same |
     | `note_unresolved` (one check per unresolved ID) | the ID exactly as spelled (`C-03`) and the word "unresolved" appear in the same paragraph, with no other connection ID between them | ID missing, only "unresolved" in the note, ID attributed to a different kind |

   - Delete `note_exists` (the content checks already need the file), `note_prose_floor`, and both `*_exactly_one` hedge checks. A hedged figure still fails, because the correct number must stand beside the label.
   - In `submission_format.md`, rewrite the note section as three plain sentences: state the reducer count, state the coupler count, and name each unresolved connection by its `connection_id` saying it is unresolved. Remove the "sixty words" requirement.
   - Every check's `why_justification` must quote the sentence it enforces (DIS-2, VER-15).
   - After every edit, copy the result over `tests/manifest.json` byte-for-byte (`copy /y tests\verifier.json tests\manifest.json`) until the generator does this for you (K2).
5. **`tests/test.sh`.** This script runs inside the Linux container, so it stays bash and **must be saved with LF endings**. Harden it:

   ```bash
   #!/bin/bash
   mkdir -p /logs/verifier; echo 0 > /logs/verifier/reward.txt        # HAR-1: written on every path
   cd /tests || exit 1
   PY=/usr/local/bin/python3; export PATH=/usr/local/bin:/usr/bin:/bin; unset PYTHONPATH
   "$PY" -I -m pytest --rootdir=/tests -p no:cacheprovider --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
   "$PY" -I /tests/score.py > /logs/verifier/score.json || true
   "$PY" -I -c "import json;print(json.load(open('/logs/verifier/score.json'))['reward'])" > /logs/verifier/reward.txt || echo 0 > /logs/verifier/reward.txt
   ```

   - `-I` ignores `PYTHONPATH`, so `score.py` and `test_outputs.py` must keep their own `sys.path.insert(0, TESTS_DIR)`. They already do.
   - Update `score.py` so an engine exception is recorded as *errored* and the run exits 2, rather than being silently counted as a failure (HAR-6).
   - Document the reward shape as **binary (all core checks must pass)** once incidental checks are gone (HAR-2).
6. **`task.toml`:**
   - `artifacts = ["/app/fitting_register.csv", "/app/takeoff_note.md", "/app/results.json"]` at top level.
   - `network_mode` stays `"public"`. `"no-network"` was tried and blocks the opencode agent's own setup (apt-get nodejs/npm) and its calls to the GLM proxy (job glm-smoke-day2). This is recorded as an ENV-4 exception.
   - Keep the `obi/<folder>` name and the `non-connector` / `offline` keywords.
   - Verify it loads by actually running harbor on it, not by eye.
7. **`Dockerfile`:**
   - Pin `python:3.12-slim-bookworm@sha256:<digest>`. Get the digest with `docker pull` then `docker inspect --format '{{index .RepoDigests 0}}'`.
   - Pin apt versions.
   - Add a `.dockerignore`.
   - Keep `COPY input/ /app/input/` only.
8. **Clean-up.** Delete `consistency/`, `evaluations/oracle/` and `evaluations/nop/`. Log each deletion.
9. **Oracle.** Run it **twice from a clean checkout**. Both must be exactly **1.0** (HAR-10).

**Exit criteria:** the oracle scores 1.0 twice, and every change is in the departures log.

---

## Phase 4: First GLM battery on the cleaned version (about 2 hours of wall time)

This gives an honest measurement, and it becomes evidence for the review.csv *Layer 2 Difficulty* row ("first battery passed 4/4 because …").

Before each run, edit `job_name` in the config, e.g. to `glm-smoke-b53t9` and then `glm-4x-b53t9-v1`.

```bat
cd /d C:\turing\scratch
rem budget check FIRST, every time
docker ps --format "{{.Names}}"
rem smoke: check for exception.txt, trajectory, sane reward
harbor run -c glm-harbor-config.json -n 1 -k 1 -y
rem the battery: -n = (RAM_GB-4)/4, minus containers already running
harbor run -c glm-harbor-config.json -n 2 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-4x-b53t9-v1\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-4x-b53t9-v1\*) do @if exist "%d\exception.txt" echo CRASHED: %~nxd
harbor view C:\harbor-jobs
```

If you hit `AgentSetupTimeoutError`, add `--agent-setup-timeout-multiplier 3`.

- Read each run's `verifier/verifier_summary.json` as whole `items[]` entries. Don't grep for "passed".
- **Classify every non-1.0 run** (Standard 12.2, North Star §9). The categories are MODEL, SPEC/TASK (ambiguity), VERIFIER and TOOL/INFRA.
  - If the run has `exception.txt` or no `trajectory.json`, it is infra: re-run it, and never count it.
- If a run fails **because of the grader or the wording**, fix that first (back to Phase 3). It is not difficulty.
- The expected result is 4/4, which goes on to Phase 5.

---

## Phase 5: Hardening design and seeded fixture generator (the real job, 1–2 days)

**Rule of thumb from the brief:** stacking more independent rules doesn't work. GLM writes one script per rule. Build **coupled** reasoning where one fact changes several downstream answers, and keep every rule **stated in one sentence** (DIF-1 "difficulty survives full disclosure").

### 5a. Proposed levers, ranked by leverage and all using sanctioned patterns (Standard 3.3)

| # | Lever | Sanctioned pattern | What changes | Why it couples |
|---|---|---|---|---|
| H1 | **Revised maker tables.** `spec_sheet.md` gives some products two table revisions with *effective dates*. T1 then says: "the revision in force on the take-off date (stated, e.g. 15 Sep 2026) governs; a revision effective later is not yet in force." Include one revision that *is* in force and changes a size (e.g. BJ-75 discharge 1-1/4 → 1), and one that is *future-dated* and would flip a vessel to a coupler. | Stale authority + wrong-default lure (latest ≠ in force) | 3–5 connections change kind **and** catalogue row, plus both counts | A size change flows into kind → catalogue lookup → counts → note. The as-of date must be stated (FIX-14), and future dates must be declared as existing (FIX-13). |
| H2 | **Catalogue stock status.** Add `status` (`STOCKED` / `DISCONTINUED`) and `superseded_by` columns. T5 says a discontinued row is never selected, and where its `superseded_by` row is stocked, that row is. One pair of ends is offered **only** by a discontinued row with no successor, which gives `NONE` with the kind kept. | Misdirection with a disclosed tie-breaker; distractor status derivable from a field (FIX-4) | 2–3 `fitting_id`s | Interacts with W3 (order-free matching) and W4 (NONE keeps kind) |
| H3 | **Re-routed runs.** `connections.csv` gains a `replaces` column. A connection named in another row's `replaces` is withdrawn: it gets no register row and no pipe. Shuffle the file order so replacements don't sit next to what they replace (T5 ordering assumption). | State across steps / unit-of-analysis | Row population, `total_run_ft`, counts | A withdrawn run can also be the one that *would* have been UNRESOLVED, so the dedupe has to happen before T2. That is an exclusion discovered late that invalidates earlier work. |
| H4 | **Metric notation from one maker.** One BSP maker prints `DN32` / `DN25`. T3 gains a disclosed one-line DN→inch table (DN20 = 3/4, DN25 = 1, DN32 = 1-1/4, DN40 = 1-1/2, DN50 = 2). | Cross-source synthesis (rule in the rules doc, data in the spec sheet, match in the catalogue) | 2–3 lookups | This extends W2 (numeric, not text, comparison) across three notations |
| H5 | **Population to about 30–34 connections.** Every added row carries a *distinct* signature: (kind, deciding rule, source, boundary). Sample rows stay uniform on key variables (T9), and IDs don't follow scenario order (4.12.a). | Removes the "16 rows fits in one glance" shortcut without padding (FIX-8) | — | — |

Pick **H1 + H2 + H3** first. Add H4 and H5 only if the next battery is still 4/4.
Never harden through hidden rules, vague wording, tight tolerances, or file volume alone (T15, DIF-6).

### 5b. Build it properly

- **`tests/generate_fixture.py`** (FIX-9, GLD-11): a *seeded* script that writes, from one source:
  - `environment/input/*`,
  - `solution/files/*`,
  - the expected values inside `tests/verifier.json`, **and a byte-identical `tests/manifest.json` in the same run** (K2),
  - `tests/input_hashes.json` (SHA-256 of every input, per FIX-11).

  Have the generator write files with `newline="\n"` and `encoding="utf-8"`, so Windows never adds CRLF to the inputs.

  Any edit then means re-running one command. Never hand-edit the fixture and the key separately. The generator lives under `tests/` and never enters the image.
- **Declare expected wrong readings in the README draft before trials** (DIF-4): W1–W5 plus the new ones from H1–H4, each with the rows it changes.
- **Golden key checks (Stage 6):**
  - Re-derive every **boundary / trap row by hand** from the documents, on paper, not with the generator (GLD-4).
  - Group rows by governing fields and check that identical inputs give identical outputs (GLD-2).
  - Re-derive any two-way reading under both readings. If the key changes, add a sentence (GLD-5).
  - Recompute the note's figures from the CSV and JSON (GLD-6).
  - Grep the gold note for "intended", "should be", "we set" and "resolved by" (GLD-7).
  - Ideally get a second person to derive the contested rows blind (GLD-8).
- **Blind-reader test (DIS-6).** Give only `instruction.md` and `input/` to someone, or to a fresh GLM chat, and have them list every literal the deliverables must contain. Anything the verifier knows that they don't is **illegal**.

---

## Phase 6: Verifier rebuild and "prove it" suites (Stage 7 + 11, about 1 day)

1. Regenerate `verifier.json` and `manifest.json` from the generator. Confirm they are identical with `fc /b tests\verifier.json tests\manifest.json`, which should say *FC: no differences encountered*. The new `verifier.json` should contain:
   - One core `table_equals` over all rows, with `row_set_ordered`, closed columns, and a population lock that pairs with the counts (VER-5).
   - One closed `object_equals` on `results.json` (tolerance 0.01 on the total; exact on counts).
   - One header check, if "exactly" stays in the format doc.
   - Tolerant core note checks: counts beside their labels, and each unresolved ID in the same paragraph as "unresolved".
2. Write **`tests/probe_suite.py`** (VER-24 discrimination harness) and record its output in the README:
   - **Equivalence suite, which must still score 1.0:**
     - E1 shuffle rows *(expected to fail, because the order is stated; confirm the instruction states it)*
     - E3 JSON key order
     - E4 quote every field
     - E5 CRLF
     - E6 trailing newline
     - E7 BOM
     - E8 / E9 `124.5` vs `124.50`
     - E10 padded spaces
     - E12 paraphrased note
     - E13 / E14 extra or removed scratch files
   - **Breaking suite, which must fail on the named check:**
     - B1 flip one kind
     - B2 drop a row
     - B3 add a row
     - B4 count ±1
     - **B5 flip each trap row first**
     - B6 empty files
     - B7 delete each deliverable
     - B8 `{}` or header-only
   - **Decoys (VER-23).** One wrong solver per expected wrong reading (W1–W5, H1–H4). Each must fail **only** on the rows it changes.
   - **Degenerate floor (HAR-4).**
     - All-COUPLER: majority-class answer.
     - Listing-only: the naive solver.
     - Keyword-only note.
     - The instruction pasted in as the note.
     - A copy of `connections.csv`.
     - Record each reward.
3. **Spoofing and containment (EXP-3…8, ENV-7, HAR-11).**
   - Symlinked deliverables must score **0**.
   - Hard link, directory or oversized file: rejected.
   - A planted `/app/conftest.py` or `sitecustomize.py` must have no effect.
   - The empty workspace must score **< 1**.
   - In a fresh container, the search below must print nothing, and `/tests` must be absent during the agent phase. Run it from CMD; the command inside the quotes runs in Linux:

     ```bat
     docker build -t b53t9-check C:\turing\work\tech-b53-t9-water-system-fitting-takeoff\environment
     docker run --rm b53t9-check bash -c "find / \( -name solve.sh -o -name verifier.json -o -name manifest.json -o -name test.sh -o -name generate_fixture.py \) 2>/dev/null; ls -d /tests /solution 2>&1"
     ```
   - Confirm that nothing under `tests/` reads `/app/input` at grade time.
4. **Security sweep (SEC-1…6).** Check for credentials, undeclared network calls, obfuscated payloads and prompt injection in inputs.
5. **Oracle ×2 → 1.0.**

---

## Phase 7: Difficulty loop (repeat until you're in the band, about 1–3 days of wall time)

```
edit (generator → regenerate) → oracle ×1 = 1.0 → probe_suite green → smoke 1 run → 4-run battery → classify → decide
```

- **Band:** 1/4 or 2/4 is safe, so stop hardening there. 3/4 may or may not be accepted; the lead says we can attempt to submit it (K1). 4/4 means harden again (next lever). 0/4 means check fairness first: open every trajectory and confirm each failure is MODEL-attributed.
- **Bimodal rewards** (e.g. 1.0 / 0.0 / 1.0 / 0.0 on the *same* check) mean a coin-flip on an ambiguity. Fix the wording and don't count the runs.
- **Change in the verifier only?** Re-grade the existing runs; no re-run is needed. **Change in the instruction, inputs or asks?** The runs are void, so re-run all four (EVD-12).
- For each failed run, write one line: run, failing check, wrong reading matched (W#/H#), and attribution (MODEL / SPEC / VERIFIER / INFRA). This table goes straight into the README *Trial Results* section and review.csv.
- If more than 20% of runs are infra-broken, fix the environment first. Don't average the noise in.

---

## Phase 8: Evidence assembly (Stage 13, about half a day)

Final layout. Zip **this folder only**:

```
tech-b53-t9-water-system-fitting-takeoff/
  task.toml  instruction.md  README.md  review.csv  qc_report.html
  environment/  Dockerfile  .dockerignore  input/…
  solution/     solve.sh  files/…  golden_trajectory.json   ← a passing GLM run's trajectory (K3)
  tests/        verifier.json + manifest.json (byte-identical, K2)  test_outputs.py  test.sh  score.py
                rl_world_verifiers/ (UNMODIFIED)  generate_fixture.py  probe_suite.py  input_hashes.json
  evaluations/
    solvability/r1/     ← copy of one reward-1.0 GLM run (never oracle)
    difficulty/r1..r4/  ← the four GLM trial folders, unflattened
```

Checklist:

- **Where the runs come from:** all four difficulty runs and the solvability run come from the **final checksum**. Any edit after the battery voids them (PKG-11).
- **Contents of each run folder:**
  - `agent/trajectory.json`
  - `result.json`
  - `config.json`, **with the keys redacted**. It contains `OPENAI_API_KEY` in expanded form.
  - `verifier/reward.json`, `reward.txt`, `ctrf.json`, `test-stdout.txt`
  - `artifacts/app/` holding the graded deliverables
  - `artifacts/manifest.json`
  - `verifier/verifier_summary.json`, for difficulty runs
- **Annotate every copied rollout with `tools\annotate_rollout.py`** (K7). Run it on each `difficulty\r1..r4` and on `solvability\r1`, with `py -3.12` and the arguments from its README. It adds these five fields to `result.json` and leaves harbor's own fields untouched:

  | Field | Value |
  |---|---|
  | `model` | `"GLM-5.2"` |
  | `overall_pass` | reward equals 1.0 |
  | `reward` | float from `verifier/reward.txt` |
  | `final_answer` | the agent's `results.json` parsed from the trajectory, or the gold figures when the results check passed |
  | `judge` | type `"deterministic file_check"`, `judge_model: null` |

  It also derives **`verifier/reward.json`** and **`verifier/verifier_summary.json`** from harbor's `reward.txt` and `score.json`, since harbor writes neither.
  - Afterwards, spot-check one run: `type evaluations\difficulty\r1\result.json | findstr /c:"overall_pass" /c:"\"model\""`.
  - Note in the README's evidence-format section that these fields and files come from `annotate_rollout.py`.
- **Never include:** job-level `config.json`, `lock.json`, `job.log`, the job-root `result.json`, anything loose under `evaluations/`, `platform/`, or `stability/`.
- **Replay check (EVD-8).** Re-run `test.sh` against each `artifacts/app/`. It must reproduce the recorded reward exactly.
- **`solve.sh`.** Update the emit step for the ATIF-format golden trajectory (or copy the trajectory through as-is). Re-run the oracle: **1.0**.
- **Final hygiene.** Remove `__pycache__`, `.pytest_cache`, `.DS_Store`, backups, the `glm` env file, `.git` and `.gitattributes` (PKG-1, PKG-9). Then run these from inside the task folder:

  ```bat
  rem key leak check (prints nothing when clean):
  findstr /s /i /m /c:"sk-" /c:"OPENAI_API_KEY=" *.*
  rem personal-path check (prints nothing when clean):
  findstr /s /i /m /c:"C:\\Users" *.*
  rem must say no differences:
  fc /b tests\verifier.json tests\manifest.json
  ```

- **Zip the folder alone, from its parent**, using Windows' built-in `tar`. It writes forward-slash paths:

  ```bat
  cd /d C:\turing\work
  tar -a -c -f tech-b53-t9-water-system-fitting-takeoff.zip tech-b53-t9-water-system-fitting-takeoff
  tar -tf tech-b53-t9-water-system-fitting-takeoff.zip
  ```

  Check that the listing starts with the task folder itself, and contains no `glm` file and no `__pycache__`.
- **Run the team zip preflight on the zip.** Among other things, it fails if `verifier.json` and `manifest.json` differ.

---

## Phase 9: README.md and review.csv (Stage 14, about half a day)

### README.md (PKG-2…5), in this section order

1. **Task description:** the §0 paragraph, plus why the population is not handed over.
2. **Departures:** file-by-file changes from the mined version, taken from `scratch/departures.md`.
3. **Declarations:**
   - Reward shape: binary, all-core.
   - Checks by kind.
   - `network_mode = "no-network"`.
   - Judge: none.
4. **Golden-key derivation:** the hand re-derivations.
5. **Difficulty design:** the W/H wrong readings and the rows each one changes, written before the trials.
6. **Probes and solvers:** E/B suites, decoys and degenerate rewards.
7. **Environment tests:** containment, oracle ×2, empty/symlink runs, planted files.
8. **Trial results:** 4 rewards, the classification per run, and the wrong reading each run matched.
9. **Isolation proof.**
10. **Reproduction commands.**

Every number must be read from a shipped file. Never state two numbers for one quantity (PKG-12). Describe earlier batteries qualitatively.

### review.csv

Use the **review form**. Don't hand-write it. The header is exactly `review_check,status,review_notes,change_made,what_to_record`. The expected statuses for this task:

| review_check | Expected status | Evidence to cite |
|---|---|---|
| Layer 1 · Package consistency | FIXED_AND_VERIFIED | artifacts list, deliverable names aligned, `consistency/` removed |
| Layer 1 · Clarity and scope | FIXED_AND_VERIFIED | template block removed (INS-1/13), A1–A4 ambiguities fixed |
| Layer 1 · Realism and leakage | FIXED_AND_VERIFIED | regex-shaped format doc rewritten; blind-reader result |
| Layer 2 Difficulty | FIXED_AND_VERIFIED | first battery was 4/4 → H1–H3 → final `difficulty/r1..r4` rewards |
| Layer 2 Solvability | PASS or FIXED_AND_VERIFIED | `solvability/r1` reward 1.0 |
| Layer 2 Stability | leave blank / "Turing runs this" | — |
| Layer 3 Oracle Mode | FIXED_AND_VERIFIED | oracle ×2 = 1.0 after each change; golden trajectory replaced |
| Layer 4 · Environment and files | FIXED_AND_VERIFIED | digest pin, no-network, containment search output |
| Layer 4 · Connectors, MCPs, and CLIs | **N/A** | "native non-connector task: `mcp_servers = []`, no environment/mcp/" |
| Layer 4 · Deliverables and artifact quality | FIXED_AND_VERIFIED | carriers justified (CSV register + md note + JSON totals) |
| Layer 5 · Verifier coverage and fairness | FIXED_AND_VERIFIED | incidental checks removed or promoted; forward/backward map; E/B suites |
| Layer 5 · LLM judge consistency | **N/A** | "no judge-based check; all checks deterministic" |
| Layer 5 · Reward hacking and exploitability | FIXED_AND_VERIFIED | symlink = 0, planted conftest no effect, test.sh isolation |
| Cross-trial · Calibration | leave blank / "Turing runs this" | — |

Every note names specific files, runs or checks. PASS means nothing was changed. FIXED_AND_VERIFIED rows need all five columns filled in.

---

## Phase 10: Delivery Gate, qc_report.html and submit (about 2 hours)

1. Zip the task folder alone, upload it, and run the Delivery Gate. It takes 5–10 minutes and stays silent until done; do the manual checklist while you wait.
2. Fix the findings, treating the report as advisory with a human deciding.
   - R3 (stability) is expected. Mark it reviewed with "Turing runs stability".
   - R17 means something under `evaluations/` is unnamed. Remove it.
3. Download `qc_report.html` and drop it at the task root next to `review.csv`. Re-zip and **upload as a new version of the same task**. Re-run the gate on that version.
4. **Submit** when:
   - the gate says PASS,
   - the score is at or above the floor,
   - `review.csv` is present and fully resolved,
   - this version has not been submitted before.
5. If it is **rejected**, read the pipeline findings and fix them in the bundle. Refresh `qc_report.html`, update the affected review.csv rows to FIXED_AND_VERIFIED, then upload a new version, re-run the gate and resubmit.

---

## Definition of done (all must be true)

- [ ] The oracle scores exactly **1.0**, twice, on the final checksum.
- [ ] GLM-5.2 scores **1/4 or 2/4** strict passes (3/4 may be submitted as an attempt; K1). All four rewards are reported. Every failure is MODEL-attributed with a matched wrong reading.
- [ ] `tests/verifier.json` and `tests/manifest.json` are byte-identical, and every rollout has been annotated by `annotate_rollout.py`.
- [ ] `solvability/r1` is a non-oracle reward-1.0 run, and `golden_trajectory.json` is a real passing run.
- [ ] Only core checks remain. Every check maps to exactly one instruction ask, and every ask has a check.
- [ ] There is no ambiguity, leaked answer or template residue. The instruction is about 100–150 natural words with `/app/` paths.
- [ ] The Dockerfile is pinned and copies `input/` only. `network_mode = "no-network"`, and containment is verified.
- [ ] The generator, input hashes and probe suite ship under `tests/`, and the E/B/decoy/degenerate results are in the README.
- [ ] `README.md`, `review.csv` (12 rows resolved) and `qc_report.html` are at the root.
- [ ] **No key anywhere in the zip**, and no personal path.

## Rough timeline

| Day | Phases |
|---|---|
| 1 | 0, 1, 2 |
| 2 | 3, 4 (first battery) |
| 3–4 | 5, 6 (hardening + generator + probes) |
| 4–6 | 7 (difficulty loop, usually 2–3 rounds) |
| 6–7 | 8, 9, 10 |

## Open questions for your lead

All answered and folded in above: the pass band (K1), the checks files (K2), the note checks (K4) and the `result.json` fields (K7). Step-by-step actions are in `CHECKLIST.md`.

---

## Appendix A: CMD equivalents for the Linux commands in the guides

| Guide (bash) | CMD |
|---|---|
| `source ~/.config/harbor/env` | `call "%USERPROFILE%\.config\harbor\harbor-env.cmd"` |
| `export VAR=value` | `set "VAR=value"` (this window only) |
| `"$VAR"` | `"%VAR%"` |
| `\` at the end of a line | `^` at the end of a line |
| `cat file` | `type file` |
| `cat dir/*/verifier/reward.txt` | `for /d %d in (dir\*) do @type "%d\verifier\reward.txt"` (`%%d` inside a `.cmd` file) |
| `ls` / `find . -type f` | `dir` / `dir /s /b /a-d` |
| `grep -r text .` | `findstr /s /i /c:"text" *.*` |
| `cmp a b` | `fc /b a b` |
| `sha256sum f` | `certutil -hashfile f SHA256` |
| `rm -rf dir` | `rmdir /s /q dir` |
| `cp -r a b` | `xcopy /e /i a b` or `robocopy a b /e` |
| `zip -r x.zip folder` | `tar -a -c -f x.zip folder` |
| `/tmp/harbor-jobs` | `C:\harbor-jobs` |
| `python3` | `py -3.12` (or `C:\turing\venv312\Scripts\python`) |
| `curl -w "%{http_code}"` | avoid `%{…}` in CMD; use `curl -s -i … \| findstr /b HTTP` |

**Where CMD can bite:**
- **Quoting:**
  - Single quotes don't quote in CMD, so use the config file instead of inline `--ak` JSON.
  - `<` and `>` redirect, so quote pip specifiers.
  - `%` expands variables, so avoid `%{…}` curl formats.
- **Line endings:** CRLF in `.sh` or input files breaks the container or the hashes. Keep `autocrlf=false` and LF editors.
- **Personal paths:** harbor records absolute paths. Work under `C:\turing\` and `C:\harbor-jobs`, not `C:\Users\<name>\Desktop`.
- **POSIX tools inside the container:** anything that must run *in* the image (the containment search, `ls -l` checks) goes through `docker run --rm <image> bash -c "…"` from CMD.
- **Local probes:** if a local probe hits something POSIX-only on Windows, run it in the task image instead:

  ```bat
  docker run --rm -v "%cd%":/work -w /work b53t9-check python3 tests/probe_suite.py
  ```
