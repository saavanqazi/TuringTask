# Step-by-step checklist: `tech-b53-t9-water-system-fitting-takeoff` (Windows CMD)

Tick the boxes as you go. Section numbers such as "Phase 3" refer to `ROADMAP.md`, which has the full detail and the rule IDs.
All commands are CMD. Open a new CMD window and run the `call …harbor-env.cmd` line first, every time.

---

## Day 1: Setup and first look

### A. Protect the key (5 min)
- [ ] 1. Move the `glm` env file **out of** `Desktop\TuringTask\tech-b53-…\`.
- [ ] 2. Create `%USERPROFILE%\.config\harbor\harbor-env.cmd` with your key (template in Phase 0, step 4).
- [ ] 3. Delete the old `glm` file after checking the new batch file works.

### B. Install the tools (1–2 h)
- [ ] 4. Install **Docker Desktop**, start it, and check that `docker run --rm hello-world` prints "Hello from Docker!".
- [ ] 5. Install **Python 3.12** from python.org, ticking "Add to PATH". Check with `py -3.12 --version`.
- [ ] 6. Install harbor:

   ```bat
   py -3.12 -m pip install uv
   py -3.12 -m uv tool install harbor
   harbor --version
   ```

   If `harbor` is not found, add `%USERPROFILE%\.local\bin` to PATH and open a new CMD. You need version 0.20.0 or newer.
- [ ] 7. Load the key and test it:

   ```bat
   call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
   curl -s -i "%OPENAI_BASE_URL%/models" -H "Authorization: Bearer %OPENAI_API_KEY%" | findstr /b HTTP
   ```

   It must show `200`.
- [ ] 8. Set Git line endings and create the probe venv:

   ```bat
   git config --global core.autocrlf false
   py -3.12 -m venv C:\turing\venv312
   C:\turing\venv312\Scripts\pip install "pydantic==2.12.5" "jsonpath-ng>=1.6,<2" "tenacity>=9.0,<10" "pytest==8.4.1"
   ```

- [ ] 9. In VS Code, open Settings, search "eol", and set it to `\n`.

### C. Folders (10 min)
- [ ] 10. Create the working folders:

   ```bat
   mkdir C:\turing\mined C:\turing\work C:\turing\scratch C:\harbor-jobs
   ```

- [ ] 11. Unzip the task **twice**: once into `C:\turing\mined\` (never edit this copy) and once into `C:\turing\work\` (the copy you edit).
- [ ] 12. Put the work copy under git so every change can be diffed:

   ```bat
   cd /d C:\turing\work
   git init
   (echo * -text)> .gitattributes
   git add -A
   git commit -m "mined baseline"
   ```

- [ ] 13. Create `C:\turing\scratch\glm-harbor-config.json` from Trainer Guidelines §1.9, with:
   - `"jobs_dir": "C:/harbor-jobs"`
   - `"n_attempts": 4`
   - tasks path `C:/turing/work/tech-b53-t9-water-system-fitting-takeoff`
- [ ] 14. Get `tools\annotate_rollout.py`, the zip preflight and the review form link from your lead, and save them under `C:\turing\tools\`.

### D. Baseline (30 min)
- [ ] 15. Run the oracle on the mined package, convert CRLF to LF, and run it again. The exact commands are in `DAY1_STEPS.md` step 6. The first run is expected to fail, because every file has CRLF endings; after the conversion it must print `1.0`. The basic oracle command is:

   ```bat
   call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
   set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
   harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-mined -n 1 -y
   for /d %d in (C:\harbor-jobs\oracle-mined\*) do @type "%d\verifier\reward.txt"
   ```

- [ ] 16. Start `C:\turing\scratch\departures.md`. From now on, every change gets one line: file, before, after, why.

### E. Careful read (1–2 h, you must do this yourself because QC checks that a human looked)
- [ ] 17. Read `instruction.md` and all six input files cold, and write down every guess you had to make.
- [ ] 18. Compare your guesses with ROADMAP Phase 2. Confirm A1 (T2 "component" wording), A2 ("neither"), A3 (catalogue kind) and A4 (total format).
- [ ] 19. Work 3–4 connections by hand (C-03, C-04, C-06, C-14) and check them against `solution\files\fitting_register.csv`.

---

## Day 2: Clean-up (Phase 3), then the first GLM battery (Phase 4)

### F. Edit the package (half a day)
- [ ] 20. **`instruction.md`:** rewrite it as about 100–150 natural words.
   - One sentence per input file.
   - The three deliverables as `/app/fitting_register.csv`, `/app/takeoff_note.md` and `/app/results.json`.
   - "the makers' tables govern over the retailer listing".
   - Point to `/app/input/submission_format.md` for the layout.
   - Delete everything after the first `---`.
- [ ] 21. **`submission_format.md`:** keep the header, enum literals and JSON keys. Replace the note section with three plain sentences (Phase 3, step 4) and remove "sixty words".
- [ ] 22. **`takeoff_rules.md`:** fix A1 (T2 means the `component_id` whose port is unstated), A2 ("none of them"), A3 and A4.
- [ ] 23. **`tests\verifier.json`:**
   - Delete `note_exists`, `note_prose_floor`, `note_reducer_exactly_one`, `note_coupler_exactly_one`, `register_exists` and `results_exists`.
   - Merge `register_table_trap_c03` into `register_table`.
   - Rewrite `note_reducer`, `note_coupler` and `note_unresolved` as **core** checks with loose matching (spec table in Phase 3, step 4).
   - Set every remaining `tag` to `core`.
   - Then copy it over the manifest: `copy /y tests\verifier.json tests\manifest.json`
- [ ] 24. **`tests\test.sh`:** replace it with the hardened version in Phase 3, step 5, saved with LF. Also make `score.py` treat an engine error as *errored* (exit 2), not as a fail.
- [ ] 25. **`task.toml`:**
   - Set `artifacts` to the three `/app/...` paths.
   - Set `network_mode = "no-network"`.
   - Add the reward shape: binary, all core.
- [ ] 26. **`environment\Dockerfile`:** pin the base image by digest. Get the digest with:

   ```bat
   docker pull python:3.12-slim-bookworm
   docker inspect --format "{{index .RepoDigests 0}}" python:3.12-slim-bookworm
   ```

   Also add an `environment\.dockerignore`.
- [ ] 27. Delete `consistency\`, `evaluations\oracle\` and `evaluations\nop\`.
- [ ] 28. Check line endings from inside the task folder (`cd /d C:\turing\work\tech-b53-t9-water-system-fitting-takeoff`). This should print nothing:

   ```bat
   C:\turing\venv312\Scripts\python -c "import pathlib;[print(p) for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix in ('.sh','.csv','.md','.json','.toml','.py') and b'\r\n' in p.read_bytes()]"
   ```

- [ ] 29. Run the **oracle twice** (job names `oracle-clean-1` and `oracle-clean-2`). Both must be `1.0`, then `git commit`.

### G. First GLM battery (about 2 h of waiting)
- [ ] 30. `docker ps --format "{{.Names}}"` to check the budget.
- [ ] 31. Set `job_name` to `glm-smoke`, then run `harbor run -c C:\turing\scratch\glm-harbor-config.json -n 1 -k 1 -y`. Check that there is no `exception.txt`, that `agent\trajectory.json` exists, and that the reward is sensible.
- [ ] 32. Set `job_name` to `glm-4x-v1`, then run `harbor run -c C:\turing\scratch\glm-harbor-config.json -n 2 -k 4 -y`.
- [ ] 33. Record the 4 rewards. **Expect 4/4.** Save that as evidence for the review.csv Difficulty row.
- [ ] 34. Classify any failed run as MODEL, SPEC, VERIFIER or INFRA. If a run failed because of the grader or the wording, fix that first.

---

## Days 3–4: Hardening (Phase 5) and proving the grader (Phase 6)

- [ ] 35. In the README draft, write the **expected wrong readings** W1–W5, plus the new ones, **before** any new run.
- [ ] 36. Write `tests\generate_fixture.py`, a seeded generator that writes all of these from one source:
   - the inputs,
   - `solution\files\`,
   - `verifier.json` **and** an identical `manifest.json`,
   - `input_hashes.json`.

   It must write with `newline="\n"`.
- [ ] 37. Add hardening levers **H1** (maker-table revisions with an as-of date), **H2** (discontinued / superseded catalogue rows) and **H3** (re-routed runs). Each rule is one clear sentence in `takeoff_rules.md`.
- [ ] 38. Work every trap row by hand on paper, and check it against the generated gold.
- [ ] 39. Blind-reader test: give only `instruction.md` and `input\` to a fresh GLM chat and ask what literals the files must contain. Anything it cannot know is a defect.
- [ ] 40. Write `tests\probe_suite.py` and run it. Harmless variations (E-suite) must still pass, real breaks (B-suite) must fail, and each decoy must fail only on its own rows. Also record the degenerate-submission rewards.
- [ ] 41. Spoofing checks: a symlinked deliverable scores 0, an empty workspace scores < 1, and the containment search prints nothing (command in Phase 6, step 3).
- [ ] 42. Check the two checks files match with `fc /b tests\verifier.json tests\manifest.json`, then run the oracle twice: 1.0.

---

## Days 4–6: Difficulty loop (Phase 7)

- [ ] 43. Smoke run, then the 4-run battery (a new `job_name` each round).
- [ ] 44. **1/4 or 2/4: stop.** 3/4: you may submit as an attempt. 4/4: add the next lever (H4, then H5), regenerate, re-run the oracle, re-run the 4. 0/4: check that every failure is the model's fault.
- [ ] 45. For each failed run, write one line: run, failing check, wrong reading matched, attribution.
- [ ] 46. Remember: a change to the verifier only means re-grade the old runs. A change to the instruction or inputs means all four runs must be redone.

---

## Days 6–7: Package and submit (Phases 8–10)

- [ ] 47. Copy the 4 final trial folders to `evaluations\difficulty\r1..r4`, and one 1.0 run to `evaluations\solvability\r1`.
- [ ] 48. Run `annotate_rollout.py` on all five run folders. Check that `result.json` has `"model": "GLM-5.2"` and `overall_pass`, and that `verifier\reward.json` and `verifier\verifier_summary.json` exist.
- [ ] 49. Redact the key from each `config.json`, and replace `solution\golden_trajectory.json` with the passing run's `agent\trajectory.json`. Update `solve.sh`'s emit step, then run the oracle again: 1.0.
- [ ] 50. Write `README.md`, following the section order in Phase 9.
- [ ] 51. Fill in **review.csv in the review form**: 12 rows, with statuses as in the Phase 9 table. Download it into the task root.
- [ ] 52. Clean up and check:
   - delete `__pycache__`, `.git` and `.gitattributes`;
   - key check: `findstr /s /i /m /c:"sk-" *.*` must print nothing;
   - path check: `findstr /s /i /m /c:"C:\\Users" *.*` must print nothing;
   - checks files: `fc /b tests\verifier.json tests\manifest.json` must match.
- [ ] 53. Zip the folder alone and run the zip preflight:

   ```bat
   cd /d C:\turing\work
   tar -a -c -f tech-b53-t9-water-system-fitting-takeoff.zip tech-b53-t9-water-system-fitting-takeoff
   ```

- [ ] 54. Upload to the QC platform and run the Delivery Gate. Fix the findings; mark R3 (stability) reviewed with "Turing runs this".
- [ ] 55. Download `qc_report.html` into the task root, re-zip, **upload as a new version**, and run the gate again.
- [ ] 56. **Submit** that version.
