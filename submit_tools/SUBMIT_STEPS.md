# Submit the Day 3 version: exact steps (Windows CMD)

The Day 3 version is the one whose GLM battery (`glm-4x-day3`) scored **3/4**, with its failure a genuine MODEL error.
Your work folder now holds Day 5, so we rebuild the **exact Day 3 files from git** into a separate folder, `C:\turing\submit`. The runs are valid only for the version they ran on.

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "SUB=C:\turing\submit\tech-b53-t9-water-system-fitting-takeoff"
```

---

## 1. Unpack the tools I sent

Save `submit_tools.zip` into `C:\turing\scratch\`, then:

```bat
mkdir C:\turing\tools
tar -xf C:\turing\scratch\submit_tools.zip -C C:\turing\tools
dir /b C:\turing\tools\submit_tools
```

You should see `assemble_evidence.py`, `README.md`, `REVIEW_NOTES_DRAFT.md`, `solve.sh` and `SUBMIT_STEPS.md`.

## 2. Rebuild the exact Day 3 files from git

```bat
cd /d C:\turing\work
git log --oneline
```

Find the line `... Day 3 hardening`. It should be `711f10d`; use whatever hash your line shows in place of `711f10d` below.

```bat
git archive --format=zip -o C:\turing\scratch\day3_exact.zip 711f10d tech-b53-t9-water-system-fitting-takeoff
mkdir C:\turing\submit
tar -xf C:\turing\scratch\day3_exact.zip -C C:\turing\submit
findstr /b "FROM" "%SUB%\environment\Dockerfile"
dir /b "%SUB%\environment\input"
```

- The `FROM` line must end in `@sha256:...`.
- The input list must **not** include `site_measurements.csv`. Its absence proves this is the Day 3 version.

## 3. Confirm it is the Day 3 grader

```bat
cd /d %SUB%
C:\turing\venv312\Scripts\python tests\probe_suite.py > C:\turing\scratch\probe_submit.txt
findstr /c:"PROBLEMS" C:\turing\scratch\probe_submit.txt
find /c "ok " C:\turing\scratch\probe_submit.txt
rmdir /s /q tests\__pycache__
```

You need `PROBLEMS: 0` and a count of **43**.

## 4. Put in the patched `solve.sh`

The golden trajectory will be a real GLM run in ATIF form, and the old `solve.sh` only understood the synthetic command list.

```bat
copy /y C:\turing\tools\submit_tools\solve.sh "%SUB%\solution\solve.sh"
```

## 5. Build `evaluations\` and the golden trajectory

```bat
C:\turing\venv312\Scripts\python C:\turing\tools\submit_tools\assemble_evidence.py --task "%SUB%" --difficulty-job C:\harbor-jobs\glm-4x-day3 --solvability-job C:\harbor-jobs\glm-smoke-day3
```

Read what it prints:
- The **mapping** `difficulty/r1..r4 <- trial name`, with rewards. You need 3 × 1.0 and one 0.0, `dy4QzNT`.
- `KEY LEAK CHECK: clean`. If it says FAILED, stop and tell me.
- Any `WARNING - personal Windows paths`: tell me which files.
- The checklist will show `reward.json` / `verifier_summary.json` as MISSING, because harbor doesn't write them. That's expected.

**Then annotate:**
- **If you have the team's `annotate_rollout.py`**, run it on each of the 5 run folders as its README says: `%SUB%\evaluations\difficulty\r1` ... `r4`, and `%SUB%\evaluations\solvability\r1`.
- **If you do not have it**, re-run step 5 with `--annotate` added at the end. This is my fallback, which follows the lead's description.

Re-read the checklist afterwards; every run should now say `OK`. If a run says `(no artifacts/ folder)`, tell me.

## 6. Oracle on the bundle. It must print 1.0

```bat
harbor run -p "%SUB%" -a oracle -o C:\harbor-jobs --job-name oracle-submit -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-submit\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
```

## 7. Containment check (for README section 7)

```bat
docker build -t b53t9-submit "%SUB%\environment"
docker run --rm b53t9-submit bash -c "find / \( -name solve.sh -o -name test.sh -o -name verifier.json -o -name manifest.json -o -name generate_fixture.py -o -name probe_suite.py \) -not -path '/proc/*' 2>/dev/null; echo ---; ls -d /tests /solution 2>&1; echo ---; ls /app /app/input"
```

What the output must show:
- Nothing before the first `---`.
- `No such file or directory` for `/tests` and `/solution`.
- `/app` holds only `input`, with the 6 input files.

Copy the output; it goes into the README.

## 8. README

```bat
copy /y C:\turing\tools\submit_tools\README.md "%SUB%\README.md"
notepad "%SUB%\README.md"
```

Then, in Notepad:
- Fix every line marked **CONFIRM** with your own values: the annotator you used, `oracle-submit`, the containment output from step 7, and the r1–r4 mapping from step 5.
- Delete the "Draft prepared with the trainer…" note at the top.
- Save.

## 9. `review.csv`, written by you through the review form

- Open the review form and fill the 12 rows. `REVIEW_NOTES_DRAFT.md` lists the facts; check them and write the notes in your own words. Stability and Cross-trial can be left as "Turing runs this".
- Click **Download review CSV** and save it as `%SUB%\review.csv`.

## 10. Final checks

```bat
cd /d %SUB%
dir /b
dir /b evaluations
dir /s /b *__pycache__* 2>nul
findstr /s /m /c:"%OPENAI_API_KEY%" *.*
fc /b tests\verifier.json tests\manifest.json
```

What you should see:
- `dir /b` lists `environment`, `evaluations`, `instruction.md`, `README.md`, `review.csv`, `solution`, `task.toml` and `tests`.
- `evaluations` has `difficulty` and `solvability` only.
- `__pycache__`: nothing.
- `findstr` for your key: nothing.
- `fc`: no differences.

## 11. Zip, run the Delivery Gate, add `qc_report.html`, submit

```bat
cd /d C:\turing\submit
tar -a -c -f tech-b53-t9-water-system-fitting-takeoff.zip tech-b53-t9-water-system-fitting-takeoff
tar -tf tech-b53-t9-water-system-fitting-takeoff.zip | findstr /i "glm .env __pycache__ .git"
```

The last command must print nothing. Then:

1. If you have the team's zip preflight, run it on the zip.
2. Upload the zip to the Shannon QC platform (one task per zip) and run the **Delivery Gate**. It takes 5–10 minutes.
3. Go through the findings:
   - **R3 (stability)** is expected: mark it reviewed with "Turing runs stability".
   - A **task checksum mismatch** between the bundle and the runs may appear. The golden trajectory and `solve.sh` change after the runs, as PKG-8 requires. If it appears, send it to me and ask your lead.
4. Download `qc_report.html` into `%SUB%`, re-zip (the same `tar` command), upload it **as a new version of the same task**, run the Delivery Gate again, and **Submit** that version.

Send me the Delivery Gate findings if anything other than R3 comes up.
