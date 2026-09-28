# Day 2: exact steps (Windows CMD only)

Today you do three things: install the cleaned-up package, prove the oracle still scores 1.0, and run the first GLM battery.
I built and tested `day2_package.zip` against the real grading engine (Python 3.12). What's inside is listed at the bottom.

Start every new CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\work\tech-b53-t9-water-system-fitting-takeoff"
```

---

## Step 1: Put the Day 2 package in place (5 min)

**1.1** Save `day2_package.zip` (the file I sent) into `C:\turing\scratch\`. Check it's there:

```bat
dir C:\turing\scratch\day2_package.zip
```

**1.2** Replace the work copy with it. Your old version is safe in git, so nothing is lost.

```bat
cd /d C:\turing\work
rmdir /s /q tech-b53-t9-water-system-fitting-takeoff
tar -xf C:\turing\scratch\day2_package.zip
dir /b tech-b53-t9-water-system-fitting-takeoff
```

The `dir` must show exactly these five entries: `environment`, `instruction.md`, `solution`, `task.toml` and `tests`. The `consistency` and `evaluations` folders are gone on purpose.

**1.3** See what changed compared with your last commit:

```bat
git status --short
```

- `D` lines are deleted files: everything under `consistency/` and `evaluations/`.
- `M` lines are modified files: `instruction.md`, `task.toml`, `submission_format.md`, `takeoff_rules.md`, `score.py`, `test.sh` and `verifier.json`.
- `??` lines are new files: `environment/.dockerignore` and `tests/manifest.json`.

If any **other** file shows as `M`, stop and send me the list.

**1.4** Confirm there are no CRLF files and that the two checks files are identical:

```bat
cd /d %TASK%
C:\turing\venv312\Scripts\python -c "import pathlib; [print('STILL CRLF:', p) for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix != '.pyc' and b'\r\n' in p.read_bytes()]"
fc /b tests\verifier.json tests\manifest.json
```

The first command must print nothing. The second must say `FC: no differences encountered`.

---

## Step 2: Pin the Docker base image (5 min)

The Dockerfile says `FROM python:3.12-slim-bookworm`, which is a tag that can change over time. Pinning it to a digest makes the build repeatable (ENV-3).

**2.1** Get the digest of the image you have:

```bat
docker pull python:3.12-slim-bookworm
for /f "delims=" %i in ('docker inspect --format "{{index .RepoDigests 0}}" python:3.12-slim-bookworm') do set "DIGEST=%i"
echo %DIGEST%
```

It prints something like `python@sha256:1a2b3c...` (64 hex characters after `sha256:`).

**2.2** Write it into the Dockerfile. This keeps LF endings and prints the new `FROM` line:

```bat
C:\turing\venv312\Scripts\python -c "import pathlib,sys; p=pathlib.Path(r'%TASK%\environment\Dockerfile'); d=sys.argv[1].split('@')[1]; s=p.read_bytes().replace(b'FROM python:3.12-slim-bookworm\n', b'FROM python:3.12-slim-bookworm@'+d.encode()+b'\n'); p.write_bytes(s); print([l for l in s.decode().splitlines() if l.startswith('FROM')])" %DIGEST%
```

It must print `['FROM python:3.12-slim-bookworm@sha256:...']`. If it prints the line **without** `@sha256`, send me the output of `echo %DIGEST%`.

---

## Step 3: Oracle twice; both must be 1.0 (about 20 min, because the first build is slow)

```bat
cd /d %TASK%
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-day2-1 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-day2-1\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
harbor run -p "%TASK%" -a oracle -o C:\harbor-jobs --job-name oracle-day2-2 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-day2-2\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
```

Both must print **1.0**. The first run rebuilds the image, because the Dockerfile changed.

If harbor shows an **error before running**, e.g. about `network_mode` or `artifacts` in `task.toml`, copy the whole error and send it to me. Those are the two new settings in `task.toml`, and your harbor version decides whether it accepts them.

If a run scores below 1.0, send me the verifier output:

```bat
for /d %d in (C:\harbor-jobs\oracle-day2-1\*) do @type "%d\verifier\test-stdout.txt"
```

---

## Step 4: Commit and update the change log (10 min)

```bat
cd /d C:\turing\work
git add -A
git commit -m "Day 2 clean-up: instruction, rules, all-core checks, harness, toml, pinned base"
git log --oneline
```

You should now see 3 commits.

Open the log (`notepad C:\turing\scratch\departures.md`), paste these rows under row 1, then save:

```markdown
| 2 | 2026-09-28 | instruction.md | Template block ("must be your final action; confirm each one exists", "Working environment"), relative input/ paths | 142-word natural request, one line per input file, deliverables as /app/... paths | INS-1, INS-13, INS-15 | oracle-day2-1/2 = 1.0 |
| 3 | 2026-09-28 | environment/input/takeoff_rules.md | T2 "every connection touching that component"; T5 silent on kind; T8 "counted by neither" | T2 names the port (component_id), other ports of the product unaffected; T5 row kind must equal the T4 kind; T8 "none of them" | Ambiguities G1-G3 from guesses.md | oracle 1.0; gold unchanged |
| 4 | 2026-09-28 | environment/input/submission_format.md | Regex-style note rules, "at least sixty words", total format loose | Note section = three plain checked facts; word floor removed; total stated as the exact sum; /app paths | Realism, INS-12, G4 | note probes 16/16 correct |
| 5 | 2026-09-28 | tests/verifier.json | 13 checks, 6 incidental (note_exists, note_prose_floor, note_reducer, note_reducer_exactly_one, note_coupler, note_coupler_exactly_one), 2 existence-only, C-03 split into its own check | 6 core checks: register_header, register_table (all 16 rows incl. C-03), results_figures, note_reducer_count, note_coupler_count, note_unresolved_C-03; loose note matching; every why_justification quotes the sentence it enforces | Only core ships (K4); VER-21, VER-26, O14 | gold 6/6; equivalence 8/8 pass; breaking 11/11 fail on the right check |
| 6 | 2026-09-28 | tests/manifest.json | absent | byte-identical copy of verifier.json | Upload validator needs it (lead ruling K2) | fc /b: no differences |
| 7 | 2026-09-28 | tests/score.py | Two-tier core + incidental weights; engine errors counted as fails | Binary reward; an errored check is listed separately and exits 2 | HAR-2, HAR-6 | gold 1.0, empty 0.0 |
| 8 | 2026-09-28 | tests/test.sh | cd /app, bare python3, no rootdir, reward.txt missing if score.py crashed | reward.txt pre-written as 0; runs from /tests with /usr/local/bin/python3 -I, fixed PATH, no PYTHONPATH, --rootdir=/tests, -p no:cacheprovider; exit 2 when a check errors | HAR-1, HAR-6, HAR-9, EXP-8 | gold 1.0, empty 0.0, symlinked deliverables 0.0, planted conftest.py/sitecustomize.py no effect |
| 9 | 2026-09-28 | task.toml | artifacts = [], network_mode = "public" | artifacts = the three /app paths; network_mode = "no-network"; metadata.reward_shape declared | TOML-4, ENV-4, HAR-2 | oracle 1.0 |
| 10 | 2026-09-28 | environment/Dockerfile, environment/.dockerignore | Base image by tag; no .dockerignore | Base pinned by digest; .dockerignore admits input/ only | ENV-3, ENV-8 | oracle 1.0 |
| 11 | 2026-09-28 | consistency/, evaluations/oracle/, evaluations/nop/ | Present (mining-tool output; evaluations contained a personal Windows path) | Removed | PKG-1, EVD-1, TOML-10 | not in tree |
```

---

## Step 5: First GLM battery (about 1–2 hours of waiting)

This measures difficulty **before** hardening. Expect 4/4 passes; that result becomes evidence for the Difficulty row of `review.csv`.

**5.1** Ask your lead one question first:

> Does harbor's `network_mode = "no-network"` still let the opencode agent reach the GLM proxy? It's set on this non-connector task per ENV-4.

If you can't get an answer, the smoke run below will tell us. An agent that can't reach the model fails at setup, or on its first model call.

**5.2** Budget check. How many containers are already running?

```bat
docker ps --format "{{.Names}}"
```

**5.3** Smoke run: 1 attempt. Open `notepad C:\turing\scratch\glm-harbor-config.json`, change `"job_name"` to `"glm-smoke-day2"`, then save. Then run:

```bat
cd /d C:\turing\scratch
harbor run -c glm-harbor-config.json -n 1 -k 1 -y
for /d %d in (C:\harbor-jobs\glm-smoke-day2\*) do @if exist "%d\verifier\reward.txt" (echo REWARD: & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-smoke-day2\*) do @if exist "%d\exception.txt" (echo CRASHED: & type "%d\exception.txt")
for /d %d in (C:\harbor-jobs\glm-smoke-day2\*) do @if exist "%d\agent\trajectory.json" echo trajectory OK
```

- If you see `AgentSetupTimeoutError`, re-run with `--agent-setup-timeout-multiplier 3` added.
- **If it crashes with a network, connection or DNS error**, switch the task to `public` for now and re-run the smoke test:

  ```bat
  C:\turing\venv312\Scripts\python -c "import pathlib; p=pathlib.Path(r'%TASK%\task.toml'); p.write_bytes(p.read_bytes().replace(b'network_mode = \"no-network\"', b'network_mode = \"public\"')); print([l for l in p.read_text().splitlines() if 'network_mode' in l])"
  ```

  Then **tell me**, so we can record it as an ENV-4 exception and ask your lead.

**5.4** The 4-run battery. Use `-n 2` for 16 GB RAM, or `-n 3` for 32 GB. Change `"job_name"` to `"glm-4x-day2"` in the config, save, then run:

```bat
cd /d C:\turing\scratch
harbor run -c glm-harbor-config.json -n 2 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-4x-day2\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-4x-day2\*) do @if exist "%d\exception.txt" echo CRASHED: %~nxd
```

**5.5** For any run below 1.0, show which checks failed:

```bat
for /d %d in (C:\harbor-jobs\glm-4x-day2\*) do @if exist "%d\verifier\score.json" (echo === %~nxd & findstr /c:"core_failures" /c:"errored" "%d\verifier\score.json")
```

---

## Send me

1. Step 1.3: the `git status --short` output.
2. Step 2.2: the printed `FROM` line.
3. Step 3: both oracle rewards.
4. Step 5: the smoke result, and the 4 battery rewards with any `core_failures`.

From those I'll classify each run and write the Day 3 hardening changes: dated revisions of the makers' tables, discontinued catalogue rows, and re-routed runs.

---

## What's in `day2_package.zip` (tested before sending)

| Check | Result |
|---|---|
| Gold answer | 1.0, 6/6 checks, 14/14 pytest checks |
| Empty workspace | 0.0 |
| Deliverables replaced by symlinks | 0.0 |
| Planted `/app/conftest.py` + `sitecustomize.py` | No effect (gold still 1.0) |
| 8 harmless variations: reordered JSON keys, all-quoted CSV, CRLF, no trailing newline, BOM, `9.0`, `124.50`, an extra scratch file | All still 1.0 |
| 11 real mistakes: flipped kind, retailer-listing trap on C-04 and C-03, dropped row, extra row, count +1, total including C-03, empty/missing/`{}` files, swapped rows | Each fails on the right check |
| Note probes: 7 good notes (paraphrased, reversed, words or digits, bullets, CRLF+BOM) | All pass |
| Note probes: 9 bad notes (wrong number, number in another sentence, `C-09` or `19` mistaken for 9, missing ID, ID in another paragraph, another ID in between, empty) | All fail |
