# Connector task 1: round 5. Hardening 2: build, probe, oracle, battery (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_harden2.zip` into `C:\turing\scratch\` first. Close heavy apps before steps 2–5.

## 1. Apply and commit

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_harden2.zip
git rm -q "%TASK%\environment\seed\seed_outlook_mail.py"
git status --short
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
git add -A
git commit -m "Hardening 2: moved meeting voids earlier answers; latest email wins; draft on latest email of any subject; gold 5/3/3/4/3"
```

`git status` must show:
- 12 `M` lines: `instruction.md`, `task.toml`, `tests/manifest.json`, `environment/Dockerfile`, the 3 `_app` files and 5 `solution/` files;
- `D` for the old `seed_outlook_mail.py`;
- `??` (or `A`) for the new `seed_outlook_task.py`.

All three `fc` commands must say `no differences encountered`.

## 2. Build. The seed must run

```bat
docker build --progress=plain -t c1probe-img "%TASK%\environment" > C:\turing\scratch\c5_build.txt 2>&1
findstr /c:"seeded 7 messages" /c:"SEED FAILED" /c:"ERROR" C:\turing\scratch\c5_build.txt
```

- It must print `seeded 7 messages and the OKR Planning move into user 46's data ...`.
- If it prints `SEED FAILED: ...`, stop and send me `c5_build.txt`.

## 3. Probe: the agent sees the move and the new emails, and the doors stay closed

```bat
docker rm -f c1probe 2>nul
docker run -d --name c1probe c1probe-img
ping -n 91 127.0.0.1 >nul
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
docker cp C:\turing\scratch\probe_mcp.py c1probe:/tmp/probe_mcp.py
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker exec c1probe chmod 644 /tmp/probe_mcp.py /tmp/probe_doors.sh
docker exec -u rlgymagent c1probe python3 /tmp/probe_mcp.py > C:\turing\scratch\c5_mcp.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c5_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh -c "ls /tmp/task-seed 2>&1; find / -xdev -name 'seed_outlook_*.py' 2>/dev/null | head -3" > C:\turing\scratch\c5_seedgone.txt 2>&1
docker rm -f c1probe
findstr /c:"mail from" /c:"mail, empty query" /c:"Moved on 28 April" /c:"2026-04-27T15:30" C:\turing\scratch\c5_mcp.txt
```

**Expected mail counts:**
- `charlotte.palmer`: 3
- `diego.alvarez`: 1
- `jack.miller`: 3
- `jack.henry`: 1
- `jared.ellis`: 1
- `isla.hughes`: 0
- the whole mailbox: 16

`findstr` should also find a line containing `Moved on 28 April` and one containing `2026-04-27T15:30`, which is Jack Henry's response time. If neither appears, tell me: it would mean the calendar tool doesn't show the move, and the task would be unfair.

`c5_seedgone.txt` must say `No such file or directory`, with no file listed.

## 4. Oracle. It must be 1.0, with all 17 checks passing

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h2 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h2\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-h2\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-h2\*) do @C:\turing\venv312\Scripts\python "%TASK%\solution\verify_gold_from_oracle.py" "%d\verifier\golden_trajectory.json" "%TASK%\solution\artifact_plan.json"
```

**What you need to see:**
- `1.0`;
- `51` and `0` (17 checks, each listed 3 times);
- the line `OK: organised meetings, answers from invitations and email ...`.

If any of these fails, stop and send me:
- the output;
- `...\verifier\test-stdout.txt`.

## 5. The battery: exactly 4 GLM runs, one at a time

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'])" glm-c1-h2 "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 1 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-c1-h2\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-h2\*) do @if exist "%d\exception.txt" echo CRASHED %~nxd
cd /d C:\harbor-jobs
tar -a -c -f C:\turing\scratch\c5_runs.zip --exclude=agent/opencode --exclude=agent/setup --exclude=*.log glm-c1-h2 oracle-c1-h2
```

## SEND

1. The step 1 `git status`, and the step 2 `findstr` line.
2. `c5_mcp.txt`, `c5_doors.txt` and `c5_seedgone.txt`.
3. Step 4's three results.
4. The 4 rewards from step 5, and `c5_runs.zip`. Check it for `sk-` first.
