# Connector task 1: round 4. Hardening 1: build, probe, oracle, battery (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_harden1.zip` into `C:\turing\scratch\` first. Close heavy apps before steps 2–5.

## 1. Apply and commit (13 files)

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_harden1.zip
git status --short
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
git add -A
git commit -m "Hardening 1: email answers count (instruction); 5 seeded inbox messages; gold 5/1/2/2/2, both drafts reply on latest email"
```

`git status` must show:
- 12 `M` lines: `instruction.md`, `task.toml`, `tests/manifest.json`, `environment/Dockerfile`, the 3 `_app` files and 5 files in `solution/`;
- 1 `??` line: `environment/seed/`.

All three `fc` commands must say `no differences encountered`.

## 2. Build. The seed must run

```bat
docker build --progress=plain -t c1probe-img "%TASK%\environment" > C:\turing\scratch\c4_build.txt 2>&1
findstr /c:"seeded 5 messages" /c:"SEED FAILED" /c:"ERROR" C:\turing\scratch\c4_build.txt
```

- It must print `seeded 5 messages into user 46's inbox ...`.
- If it prints `SEED FAILED: ...`, stop and send me `c4_build.txt`. The seed script refuses to patch a gym database that differs from the one the task was designed on.

## 3. Probe: the new emails are served to the agent, and the doors stay closed

```bat
docker rm -f c1probe 2>nul
docker run -d --name c1probe c1probe-img
ping -n 91 127.0.0.1 >nul
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
docker cp C:\turing\scratch\probe_mcp.py c1probe:/tmp/probe_mcp.py
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker exec c1probe chmod 644 /tmp/probe_mcp.py /tmp/probe_doors.sh
docker exec -u rlgymagent c1probe python3 /tmp/probe_mcp.py > C:\turing\scratch\c4_mcp.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c4_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh -c "ls /tmp/task-seed 2>&1; find / -xdev -name 'seed_outlook_mail.py' 2>/dev/null | head -3" > C:\turing\scratch\c4_seedgone.txt 2>&1
docker rm -f c1probe
findstr /c:"mail from" /c:"mail, empty query" /c:"list of" C:\turing\scratch\c4_mcp.txt
```

**Expected mail counts:**
- `charlotte.palmer`: 2
- `diego.alvarez`: 1
- `jack.miller`: 2
- `jack.henry`: 1
- `jared.ellis`: 1
- `isla.hughes`: 0
- the whole mailbox: 14

`c4_seedgone.txt` must say `No such file or directory`, with no file listed: the seed script is gone from the image.

## 4. Oracle. It must be 1.0, with all 15 checks passing

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h1 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h1\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-h1\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-h1\*) do @C:\turing\venv312\Scripts\python "%TASK%\solution\verify_gold_from_oracle.py" "%d\verifier\golden_trajectory.json" "%TASK%\solution\artifact_plan.json"
```

**What you need to see:**
- `1.0`;
- `45` and `0`;
- a line starting `OK: organised meetings, answers from invitations and email ...`. That line re-derives the whole gold from what the gym really served in this run.

If any of these fails, stop and send me:
- the output;
- `...\verifier\test-stdout.txt`.

## 5. The battery: exactly 4 GLM runs, one at a time

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'])" glm-c1-h1 "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 1 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-c1-h1\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-h1\*) do @if exist "%d\exception.txt" echo CRASHED %~nxd
cd /d C:\harbor-jobs
tar -a -c -f C:\turing\scratch\c4_runs.zip --exclude=agent/opencode --exclude=agent/setup --exclude=*.log glm-c1-h1 oracle-c1-h1
```

It takes about 30–40 minutes.

## SEND

1. The `git status` lines from step 1, and the `findstr` line from step 2.
2. `c4_mcp.txt`, `c4_doors.txt` and `c4_seedgone.txt`.
3. Step 4's three results.
4. The 4 rewards from step 5, and `c4_runs.zip`. Check it for `sk-` first.
