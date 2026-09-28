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

## Conflicts between the documents: decide these up front

| # | Conflict | What I recommend |
|---|---|---|
| K1 | **Pass band.** Trainer Guidelines say 5 runs and ≤50%. The brief and the Standard (Q1, 2026-09-04) say **4 runs, 1–3 of 4 passing**. The client's own script still fails a task at >2 passes. | Run 4. Aim for **1/4 or 2/4**, because 3/4 is legal but risky with the client script. |
| K2 | **Verifier file.** The brief says non-connector tasks iterate on `tests/verifier.json` and must be rewritten to `tests/manifest.json` as the last packaging step. The Standard v2 ships `tests/verifier.json` + `test_outputs.py` + `test.sh` and says "nothing else may be added". | **Ask your lead before Phase 8.** Until then, iterate on `verifier.json`. Whichever file ships, re-run the oracle afterwards. |
| K3 | **Golden trajectory.** The brief calls it the "required Oracle asset". PKG-8 says it must be a **real model run scoring 1.0, never the oracle**. The mined `solution/golden_trajectory.json` is a synthetic list of 10 `printf` commands. | Replace it with the `agent/trajectory.json` of a passing GLM run (Phase 8), and make `solve.sh`'s emit step tolerate the ATIF format. |
| K4 | **"Secondary" verifiers.** This package has no `"category": "secondary"`. It has `metadata.tag: "incidental"`, 6 of 13 checks, all on the note. | Treat `incidental` as secondary: nothing non-core ships. Each note check is either **promoted to core (made fair)** or **deleted along with its ask** (Phase 3). |
| K5 | **Oracle evidence.** The brief says ship none. The Standard says Turing adds `oracle/`. | Either way, **delete** `evaluations/oracle/` and `evaluations/nop/`. |
| K6 | **Stability.** | Ship no `stability/` folder. Delivery Gate finding R3 is expected; mark it reviewed with "Turing runs stability". |

---

## Phase 0: One-time setup on your Windows machine (about half a day)

Your screenshots show Windows. The guidelines say **the Linux path is the tested one**, so run harbor from **WSL2 Ubuntu**.

1. **Security first.** Your task folder contains a `glm.env` file holding your key. **Move it out of `tech-b53-…/` right now**, for example to `~/.config/harbor/env` in WSL, with `chmod 600`. If it gets zipped, the key ships to the client (TOML-10 and SEC-1 are both blocking). Never commit it.
2. **Docker Desktop.** Use the WSL2 backend. Check that `docker run --rm hello-world` works inside WSL.
   - This task's image is `python:3.12-slim-bookworm`, so **no `benchmark-base` / gcloud is needed**. That image is for connector tasks only.
3. **Python and harbor.** Install Python ≥ 3.12, then `uv tool install harbor`. Check that `harbor --version` is ≥ 0.20.0.
   - The vendored engine (`tests/rl_world_verifiers/*.pyc`) is **Python 3.12 bytecode**. Any local probe script must run under 3.12; 3.11 fails with "bad magic number".
4. **Environment file.** In `~/.config/harbor/env`, set `OPENAI_API_KEY`, `OPENAI_BASE_URL=http://34.41.10.8:4000/v1` and `JUDGE_MODEL=openai/glm-5.2`.
   - Test the key with the curl sanity check. Expect `200`.
   - Also set `export PYTHONUTF8=1`.
5. **GLM config.** Create `glm-harbor-config.json` (Trainer Guidelines §1.9).
   - Use `model_name: "glm/glm-5.2"` with the `reasoning_content` provider block, set `n_attempts: 4`, and set `tasks[0].path` to the task folder.
6. **Line endings.** Keep every file **LF, UTF-8, no BOM** (FIX-10). In WSL, run `git config --global core.autocrlf false`, and set your editor to LF.
   - Windows editors silently turning input files into CRLF is a real risk here.
7. **Working layout.** Use this layout, outside the task folder:

   ```
   ~/turing/
     mined/tech-b53-…/        # pristine copy: never edit (the "mined version" for PKG-2)
     work/tech-b53-…/         # the package you edit and zip
     scratch/                 # departures log, probes, decoys, job copies
   ```

   Put `work/` under git (outside the zip) so every change is diffable for the README departures section.
8. **QC platform.** Sign in to the Shannon QC platform with your `@turing-gpt-git.com` account. Check that the header shows *glm access ready*.

**Exit criteria:** hello-world works, the curl check returns 200, and `harbor --version` is ≥ 0.20.0. The key is outside the task folder and outside git.

---

## Phase 1: Intake, inventory and baseline (Stage 1, about 1 hour)

1. **Inventory (1.2).** Record `find . -type f -exec ls -l {} \;` of the mined package into `scratch/departures.md`. That list is the "mined version".
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

   ```bash
   source ~/.config/harbor/env
   harbor run -p "$TASK" -a oracle --ve OPENAI_API_KEY="$OPENAI_API_KEY" \
     --ve OPENAI_BASE_URL="$OPENAI_BASE_URL" -o /tmp/harbor-jobs \
     --job-name oracle-b53t9-mined -n 1 -y
   cat /tmp/harbor-jobs/oracle-b53t9-mined/*/verifier/reward.txt   # expect 1.0
   ```

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
   - Keep the note counts as core with a simple, tolerant pattern: label word within a sentence of the number, any order, digits or word, case-insensitive. Don't use the 700-character hedge regex.
   - Keep `note_unresolved` as core, but loosen it to "C-03 and 'unresolved' in the same paragraph".
   - Every check's `why_justification` must quote the sentence it enforces (DIS-2, VER-15).
5. **`tests/test.sh`.** Harden it:

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
   - `network_mode = "no-network"`.
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

```bash
docker ps --format '{{.Names}}'                          # budget check FIRST, every time
harbor run -c glm-harbor-config.json -n 1 -k 1 -y        # smoke: check for exception.txt, trajectory, sane reward
harbor run -c glm-harbor-config.json -n 2 -k 4 -y        # the battery (-n = (RAM_GB-4)/4, minus containers already running)
cat /tmp/harbor-jobs/<job>/*/verifier/reward.txt
```

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
  - the expected values inside `tests/verifier.json`,
  - `tests/input_hashes.json` (SHA-256 of every input, per FIX-11).

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

1. Regenerate `verifier.json` from the generator:
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
   - In a fresh container, `find / -name solve.sh -o -name verifier.json -o -name test.sh 2>/dev/null` must print nothing, and `/tests` must be absent during the agent phase.
   - Confirm that nothing under `tests/` reads `/app/input` at grade time.
4. **Security sweep (SEC-1…6).** Check for credentials, undeclared network calls, obfuscated payloads and prompt injection in inputs.
5. **Oracle ×2 → 1.0.**

---

## Phase 7: Difficulty loop (repeat until you're in the band, about 1–3 days of wall time)

```
edit (generator → regenerate) → oracle ×1 = 1.0 → probe_suite green → smoke 1 run → 4-run battery → classify → decide
```

- **Band:** 1/4 or 2/4 is the target. 3/4 is acceptable per Turing but risky at the client (K1). 4/4 means harden again (next lever). 0/4 means check fairness first: open every trajectory and confirm each failure is MODEL-attributed.
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
  tests/        verifier.json (or manifest.json — K2)  test_outputs.py  test.sh  score.py
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
- **`result.json` fields.** It must carry `"model": "GLM-5.2"`, a boolean `overall_pass`, `final_answer`, `reward` and judge provenance.
  - Harbor's native `result.json` may not have all of these. Check what the Delivery Gate reports, and ask your lead whether to add them.
- **Never include:** job-level `config.json`, `lock.json`, `job.log`, the job-root `result.json`, anything loose under `evaluations/`, `platform/`, or `stability/`.
- **Replay check (EVD-8).** Re-run `test.sh` against each `artifacts/app/`. It must reproduce the recorded reward exactly.
- **`solve.sh`.** Update the emit step for the ATIF-format golden trajectory (or copy the trajectory through as-is). Re-run the oracle: **1.0**.
- **Final hygiene.** Remove `__pycache__`, `.pytest_cache`, `.DS_Store`, backups, the `glm` env file and `.git` (PKG-1, PKG-9). Run `grep -rI "sk-\|OPENAI_API_KEY=" .` and check that it prints nothing.

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
- [ ] GLM-5.2 scores **1/4, 2/4 or 3/4** strict passes. All four rewards are reported. Every failure is MODEL-attributed with a matched wrong reading.
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

1. **K2:** do we ship `tests/verifier.json` (Standard v2) or rewrite it to `tests/manifest.json` (brief)?
2. **K1:** is 3/4 safe with the client's script, or should we stop at ≤2/4?
3. **`result.json` fields** (`"model": "GLM-5.2"`, `overall_pass`, `final_answer`, judge provenance): does harbor's output satisfy the gate as it is, or do we add the fields?
4. **Note checks:** promote to core, or drop the note-content ask? My recommendation is to promote, with tolerant matching.
