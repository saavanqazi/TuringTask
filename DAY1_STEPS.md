# Day 1: exact steps (Windows CMD only)

Rules for every step:
- Use a **normal CMD** window (Start → type `cmd` → Enter), unless a step says **Admin CMD** (right-click Command Prompt → *Run as administrator*).
- Copy each command block and paste it with right-click. Run blocks one at a time and check the result before moving on.
- If a command says `'xyz' is not recognized`, close CMD, open a **new** one (so PATH refreshes), and try again.

---

## Step 1: Move the key out of the task folder (5 min)

**1.1** Create the folder for the key file, and check that the `glm.env` file is where we expect:

```bat
mkdir "%USERPROFILE%\.config\harbor"
dir "%USERPROFILE%\Desktop\TuringTask\tech-b53-t9-water-system-fitting-takeoff\glm*"
```

- If the file shows a different name (e.g. `glm` with no extension), use that exact name in 1.2 and 1.3.
- If `dir` says *The system cannot find the path specified*, your Desktop is inside OneDrive. Use `%OneDrive%\Desktop\TuringTask\...` instead of `%USERPROFILE%\Desktop\TuringTask\...` in **every** step below.

**1.2** Move the key file out of the task folder, keeping it as a backup next to the new key file:

```bat
move "%USERPROFILE%\Desktop\TuringTask\tech-b53-t9-water-system-fitting-takeoff\glm.env" "%USERPROFILE%\.config\harbor\glm.env.bak"
```

**1.3** Look at the key and copy the value between the quotes after `OPENAI_API_KEY=`:

```bat
type "%USERPROFILE%\.config\harbor\glm.env.bak"
```

**1.4** Create the key loader file:

```bat
notepad "%USERPROFILE%\.config\harbor\harbor-env.cmd"
```

Notepad asks *"Do you want to create a new file?"* → **Yes**. Paste the text below, replace `PASTE_YOUR_KEY_HERE` with your key (**no quotes**), then save with Ctrl+S and close Notepad:

```bat
@echo off
set "OPENAI_API_KEY=PASTE_YOUR_KEY_HERE"
set "GLM_API_KEY=%OPENAI_API_KEY%"
set "OPENAI_BASE_URL=http://34.41.10.8:4000/v1"
set "JUDGE_MODEL=openai/glm-5.2"
set "PYTHONUTF8=1"
echo Harbor env loaded.
```

**1.5** Test the loader:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
if defined OPENAI_API_KEY (echo KEY IS SET) else (echo KEY MISSING)
```

It should print `Harbor env loaded.` and `KEY IS SET`.

From now on, the **first line in every new CMD window** is:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
```

---

## Step 2: Install Docker, Python 3.12, Git and harbor, then test the key (1–2 hours, including reboots)

**2.1** Check what is already installed. Anything that says *not recognized* needs installing:

```bat
docker --version
py -3.12 --version
git --version
winget --version
```

**2.2** Install whatever is missing. If `winget` works, use these commands; otherwise use the website in brackets.

```bat
winget install -e --id Docker.DockerDesktop
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
```

- Docker: https://www.docker.com/products/docker-desktop/
- Python: python.org. In the installer, tick **"Add python.exe to PATH"**; the `py` launcher is included by default.
- Git: https://git-scm.com/download/win

**2.3** **Reboot** if Docker asks. Then start **Docker Desktop** from the Start menu, accept the terms, skip sign-in, and wait until it shows *Engine running*.
- If Docker says WSL needs installing or updating, open **Admin CMD** and run `wsl --update`, then restart Docker Desktop.
- This only updates Docker's engine. You never use a WSL shell.
- In Docker Desktop, go to **Settings → General** and tick *Start Docker Desktop when you sign in*.

**2.4** In a **new** CMD, check Docker:

```bat
docker run --rm hello-world
docker compose version
```

You need to see `Hello from Docker!` and a compose version.

**2.5** Install harbor:

```bat
py -3.12 -m pip install --user uv
py -3.12 -m uv tool install harbor
py -3.12 -m uv tool update-shell
```

Now **close CMD and open a new one**, then:

```bat
harbor --version
```

You need `0.20.0` or higher. If it says *not recognized*, run `set PATH=%USERPROFILE%\.local\bin;%PATH%` and try again, then tell me.

**2.6** Test the key:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
curl -s -i "%OPENAI_BASE_URL%/models" -H "Authorization: Bearer %OPENAI_API_KEY%" | findstr /b HTTP
```

- You need `HTTP/1.1 200 OK`.
- `401` means the key is wrong. Re-check step 1.4, and make sure there are no quotes or spaces around the key.
- No output at all means the proxy can't be reached from your network.

**2.7** Once the key test shows 200, delete the backup copy of the old key file:

```bat
del "%USERPROFILE%\.config\harbor\glm.env.bak"
```

---

## Step 3: Git settings, the Python 3.12 venv and editor line endings (15 min)

**3.1** Set up Git. Use your own name, and the email you use for Turing work:

```bat
git config --global core.autocrlf false
git config --global user.name "Your Name"
git config --global user.email "you@turing-gpt-git.com"
```

**3.2** Create the folders:

```bat
mkdir C:\turing\mined C:\turing\work C:\turing\scratch C:\turing\tools C:\harbor-jobs
```

**3.3** Create the Python 3.12 venv for local checks. The quotes around the version specifiers are required in CMD.

```bat
py -3.12 -m venv C:\turing\venv312
C:\turing\venv312\Scripts\python -m pip install "pydantic==2.12.5" "jsonpath-ng>=1.6,<2" "tenacity>=9.0,<10" "pytest==8.4.1"
C:\turing\venv312\Scripts\python --version
```

The last line must say `Python 3.12.x`.

**3.4** Set your editor to LF line endings. You won't edit task files today, but set this now.
- **VS Code** (install with `winget install -e --id Microsoft.VisualStudioCode` if you want it): File → Preferences → Settings, search **eol**, and set *Files: Eol* to **\n**.
- **Notepad** (Windows 10 1809+ / 11) keeps a file's existing line endings, and shows them in the bottom bar. The bar should say **Unix (LF)** for task files.

---

## Step 4: Copy the task into `mined` and `work`, then commit it (10 min)

**4.1** Copy the task twice. Robocopy prints a summary table; exit code 1 means it copied files, which is fine.

```bat
robocopy "%USERPROFILE%\Desktop\TuringTask\tech-b53-t9-water-system-fitting-takeoff" "C:\turing\mined\tech-b53-t9-water-system-fitting-takeoff" /e
robocopy "C:\turing\mined\tech-b53-t9-water-system-fitting-takeoff" "C:\turing\work\tech-b53-t9-water-system-fitting-takeoff" /e
```

**4.2** Check the folder contents, and check that no key file came along:

```bat
dir /b C:\turing\work\tech-b53-t9-water-system-fitting-takeoff
dir /s /b C:\turing\work\*glm* C:\turing\mined\*glm*
```

- The first command should list `consistency`, `environment`, `evaluations`, `solution`, `tests`, `instruction.md` and `task.toml`.
- The second must say **File Not Found**. If it lists a file, delete that file before going on.

**4.3** Save the inventory of the original package (this is the "mined version" your README describes):

```bat
dir /s /a-d C:\turing\mined\tech-b53-t9-water-system-fitting-takeoff > C:\turing\scratch\mined_inventory.txt
```

**4.4** Put the work copy under Git. `* -text` tells Git never to touch line endings, so it stores files byte for byte.

```bat
cd /d C:\turing\work
git init
(echo * -text)> .gitattributes
(echo *.zip& echo __pycache__/)> .gitignore
git add -A
git commit -m "Mined baseline, unmodified"
git log --oneline
```

You should see one commit.

---

## Step 5: GLM config file, and ask your lead for the team tools (15 min)

**5.1** Create the GLM config file:

```bat
notepad C:\turing\scratch\glm-harbor-config.json
```

Choose **Yes** to create it, paste the text below, save and close. If Notepad's *Save as* shows an Encoding box, pick **UTF-8**, not "UTF-8 with BOM".

```json
{
  "job_name": "glm-smoke-b53t9",
  "jobs_dir": "C:/harbor-jobs",
  "n_concurrent_trials": 1,
  "n_attempts": 4,
  "verifier": {
    "env": {
      "OPENAI_API_KEY": "${OPENAI_API_KEY}",
      "OPENAI_BASE_URL": "http://34.41.10.8:4000/v1",
      "JUDGE_MODEL": "openai/glm-5.2"
    }
  },
  "agents": [
    {
      "name": "opencode",
      "model_name": "glm/glm-5.2",
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "OPENAI_BASE_URL": "http://34.41.10.8:4000/v1"
      },
      "kwargs": {
        "opencode_config": {
          "provider": {
            "glm": {
              "npm": "@ai-sdk/openai-compatible",
              "name": "GLM Gateway",
              "options": {
                "baseURL": "http://34.41.10.8:4000/v1",
                "apiKey": "{env:OPENAI_API_KEY}"
              },
              "models": {
                "glm-5.2": {
                  "name": "GLM-5.2",
                  "reasoning": true,
                  "interleaved": { "field": "reasoning_content" }
                }
              }
            }
          }
        }
      }
    }
  ],
  "tasks": [
    { "path": "C:/turing/work/tech-b53-t9-water-system-fitting-takeoff" }
  ]
}
```

- Leave `${OPENAI_API_KEY}` exactly as written: harbor fills it in from your environment, so **your real key never goes into this file**.
- You won't run GLM today. This file is for Day 2.

**5.2** Check that the JSON is valid:

```bat
C:\turing\venv312\Scripts\python -m json.tool C:\turing\scratch\glm-harbor-config.json > nul && echo CONFIG OK
```

It must print `CONFIG OK`.

**5.3** Send your lead a message like this:

> Hi, for tech-b53-t9-water-system-fitting-takeoff I need the team tools: `tools/annotate_rollout.py`, the zip preflight script, and the review form link. Where can I download them?

Save the files you receive into `C:\turing\tools\`.

---

## Step 6: Oracle run and change log (1 hour, mostly waiting)

**Expect a failure the first time.** Every text file in the mined zip has Windows (CRLF) line endings, including `solution/solve.sh` and `tests/test.sh`. In Linux bash, CRLF makes `solve.sh` stop on its first line (`set: pipefail: invalid option name`) before it writes any deliverable. So this first run should score **0.0, or give no reward at all**. That is the evidence for your first fix.

**6.1** Run the oracle on the package exactly as mined. The first run builds the image, which takes a few minutes.

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-mined-crlf -n 1 -y
```

Read the result:

```bat
for /d %d in (C:\harbor-jobs\oracle-mined-crlf\*) do @if exist "%d\verifier\reward.txt" (echo REWARD: & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\oracle-mined-crlf\*) do @if exist "%d\exception.txt" echo CRASHED - see %d\exception.txt
for /d %d in (C:\harbor-jobs\oracle-mined-crlf\*) do @if exist "%d\agent\oracle.txt" type "%d\agent\oracle.txt"
```

- Write down what you see: the reward (probably 0.0 or missing), and whether `oracle.txt` shows the `pipefail` error.
- If it actually prints `1.0`, harbor fixed the line endings by itself. Note that and still do 6.2, because the inputs must be LF anyway (FIX-10).

**6.2** Convert every text file in the **work** copy to LF. Leave the `mined` copy untouched.

```bat
cd /d C:\turing\work\tech-b53-t9-water-system-fitting-takeoff
C:\turing\venv312\Scripts\python -c "import pathlib; fixed=[print('LF:', p) or p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n')) for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix != '.pyc' and b'\r\n' in p.read_bytes()]"
```

It prints one `LF: ...` line per file converted: **39 files** on the mined package. The `.pyc` engine files are skipped on purpose, because they are binary.

Run the same check again; it must now print **nothing**:

```bat
C:\turing\venv312\Scripts\python -c "import pathlib; [print('STILL CRLF:', p) for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix != '.pyc' and b'\r\n' in p.read_bytes()]"
```

**6.3** Run the oracle again with a new job name. If this is a new CMD window, first run the `call …harbor-env.cmd` and `set "TASK=…"` lines from 6.1 again.

```bat
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-lf -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-lf\*) do @if exist "%d\verifier\reward.txt" (echo REWARD: & type "%d\verifier\reward.txt")
```

It must print **1.0**. If it doesn't, send me the output of:

```bat
for /d %d in (C:\harbor-jobs\oracle-lf\*) do @type "%d\verifier\test-stdout.txt"
```

**6.4** Commit the fix:

```bat
cd /d C:\turing\work
git add -A
git commit -m "Convert all text files CRLF to LF (solve.sh/test.sh failed under bash; FIX-10)"
```

**6.5** Optional: grade the gold locally, without Docker. This is quick, and it proves your venv can run the engine.

```bat
cd /d C:\turing\work\tech-b53-t9-water-system-fitting-takeoff
set "HARBOR_TASK_WORKSPACE=%CD%\solution\files"
C:\turing\venv312\Scripts\python tests\score.py > C:\turing\scratch\baseline_gold.json
findstr /c:"reward" /c:"core_failures" C:\turing\scratch\baseline_gold.json
set "HARBOR_TASK_WORKSPACE="
```

You should see `"reward": 1.0` and an empty `core_failures`. If Python throws an error on Windows, skip this step; the harbor oracle in 6.3 is the check that counts.

**6.6** Start the change log:

```bat
notepad C:\turing\scratch\departures.md
```

Choose **Yes**, then paste this and fill in the two results:

```markdown
# Departures log: tech-b53-t9-water-system-fitting-takeoff

Mined version: file list in scratch/mined_inventory.txt (unzipped from the tracker zip, unmodified).

| # | Date | File(s) | Before (mined) | After | Why | Re-check |
|---|---|---|---|---|---|---|
| 1 | YYYY-MM-DD | every text file (39) | CRLF line endings | LF | solve.sh stops at `set -euo pipefail` under bash and writes no deliverable; test.sh continuation lines break the same way; FIX-10 requires LF | oracle-mined-crlf: <your result> -> oracle-lf: 1.0 |
```

Save and close.

---

## Step 7: Read the task yourself and work 4 connections by hand (1–2 hours)

This step is yours to do. QC checks that a human did the review, so don't skip it.

**7.1** Make CMD show special characters (dashes and so on) properly, then read each file in order. Notepad is easier for the long ones.

```bat
chcp 65001
cd /d C:\turing\work\tech-b53-t9-water-system-fitting-takeoff
type instruction.md
notepad environment\input\takeoff_rules.md
notepad environment\input\spec_sheet.md
notepad environment\input\submission_format.md
type environment\input\components.csv
type environment\input\connections.csv
type environment\input\fitting_catalog.csv
```

**7.2** Open a notes file:

```bat
notepad C:\turing\scratch\guesses.md
```

Write down every point where you had to **guess** what the author meant. Some questions to ask yourself while reading:
- In rule T2, does "every connection touching that component" mean one port (e.g. `P1-S`) or the whole pump (TJ-100, both ports)?
- In rule T8, "counted by **neither**": there are three counts. Is anything unclear there?
- In rule T5, must the catalogue row's `kind` equal the kind from T4?
- Is it said how `total_run_ft` should be written (decimals, rounding)?
- Does the instruction mention anything that doesn't exist in the files?
- Does the instruction give away any answer, such as a count or a total?

**7.3** Pull out the 4 connections to work by hand:

```bat
cd /d C:\turing\work\tech-b53-t9-water-system-fitting-takeoff\environment\input
findstr /b "C-03, C-04, C-06, C-14," connections.csv
findstr /b "TK-A, P1-S, P2-D, V2, P3-D, V3, P4-D," components.csv
```

For each connection, fill in this table in `guesses.md`. The sizes come from **spec_sheet.md** (Ctrl+F the product code), and the threads from **components.csv**.

```markdown
| conn | from port: product / role / maker size / thread | to port: product / role / maker size / thread | kind (T2 then T4) | catalogue row (T5) |
|---|---|---|---|---|
| C-03 | | | | |
| C-04 | | | | |
| C-06 | | | | |
| C-14 | | | | |
```

Things to watch for:
- **C-03:** what does the maker state for that pump's suction port?
- **C-04:** the retailer listing and the maker disagree. Which one do the rules say to use?
- **C-06:** is there a catalogue row for this pair of ends at all? If not, what do T5 and T7 say?
- **C-14:** one maker prints decimals (`1.0`). Rule T3 says how to compare.

**7.4** Compare your answers with the gold answer, and your total with the gold total:

```bat
findstr /b "C-03, C-04, C-06, C-14," ..\..\solution\files\fitting_register.csv
type ..\..\solution\files\results.json
```

Note any row where you and the gold differ, and why. That is either your mistake or a gold defect; both are worth knowing.

**7.5** Your notes live in `C:\turing\scratch`, outside git, so just keep them safe. Then check that step 7 didn't change any task file:

```bat
cd /d C:\turing\work
git status
```

It should say *nothing to commit, working tree clean*.

---

## End of Day 1: all of these must be true

- [ ] `glm.env` is gone from the task folders; the key lives only in `%USERPROFILE%\.config\harbor\harbor-env.cmd`.
- [ ] `docker run --rm hello-world` works, and `harbor --version` shows ≥ 0.20.0.
- [ ] The curl key check shows `HTTP/1.1 200 OK`.
- [ ] `C:\turing\venv312\Scripts\python --version` shows 3.12.x.
- [ ] `C:\turing\mined\...` is untouched; `C:\turing\work\...` has 2 git commits (baseline + LF).
- [ ] `glm-harbor-config.json` prints `CONFIG OK`.
- [ ] Oracle results are written down: `oracle-mined-crlf` = ______, `oracle-lf` = **1.0**.
- [ ] `departures.md` and `guesses.md` are started.
- [ ] You've asked your lead for `annotate_rollout.py`, the zip preflight and the review form.

When you're done, send me three things: the two oracle results, your `guesses.md` list, and any row where your hand-worked answer differs from the gold. We'll start Day 2 from there.
