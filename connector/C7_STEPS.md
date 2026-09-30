# Connector task 1: round 7. Hardening 4 (relayed answers, Diego's latest email): build, probe, oracle, battery (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_harden4.zip` into `C:\turing\scratch\` first (`probe_calendar.py`, `probe_mcp.py` and `probe_doors.sh` are already there). Close heavy apps before steps 2–5.

## 1. Apply and commit (11 files)

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_harden4.zip
git status --short
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
git add -A
git commit -m "Hardening 4: relayed answers do not count; Diego's latest email is the 12 May roadmap note"
```

`git status` must show 11 `M` lines, and all three `fc` commands must say `no differences encountered`.

## 2. Build. The seed must run

```bat
docker build --progress=plain -t c1probe-img "%TASK%\environment" > C:\turing\scratch\c7_build.txt 2>&1
findstr /c:"seeded 10 messages and 2 meeting moves" /c:"SEED FAILED" /c:"ERROR" C:\turing\scratch\c7_build.txt
```

If it prints `SEED FAILED`, stop and send me `c7_build.txt`.

## 3. Probe what the agent sees, and that the doors stay closed

```bat
docker rm -f c1probe 2>nul
docker run -d --name c1probe c1probe-img
ping -n 91 127.0.0.1 >nul
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
docker cp C:\turing\scratch\probe_calendar.py c1probe:/tmp/probe_calendar.py
docker cp C:\turing\scratch\probe_mcp.py c1probe:/tmp/probe_mcp.py
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker exec c1probe chmod 644 /tmp/probe_calendar.py /tmp/probe_mcp.py /tmp/probe_doors.sh
docker exec -u rlgymagent c1probe python3 /tmp/probe_calendar.py > C:\turing\scratch\c7_calendar.txt 2>&1
docker exec -u rlgymagent c1probe python3 /tmp/probe_mcp.py > C:\turing\scratch\c7_mcp.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c7_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh -c "ls /tmp/task-seed 2>&1; find / -xdev -name 'seed_outlook_*.py' 2>/dev/null | head -3" > C:\turing\scratch\c7_seedgone.txt 2>&1
docker rm -f c1probe
type C:\turing\scratch\c7_calendar.txt
findstr /c:"mail from" /c:"mail, empty query" C:\turing\scratch\c7_mcp.txt
```

**What `c7_calendar.txt` must show:**
- **OKR Planning:** the body `Moved on 28 April at 11:00 Pacific ...`. Jack Henry at `2026-04-28T17:40:00Z`, and the two `eugene.dunn` rows at `19:20` and `19:35`.
- **Weekly Pipeline Review (06 May):** the body `... Moved on 1 May at 16:00 Pacific ...`. Diego at `2026-05-01T22:30:00Z`, and the others on `2026-05-02`.

If the move notes or the times don't show up this way, stop and tell me: it would mean the agent can't see what the task depends on.

**Expected mail counts:**
- `charlotte.palmer`: 3
- `diego.alvarez`: 2
- `jack.miller`: 3
- `jack.henry`: 1
- `jared.ellis`: 1
- `isla.hughes`: 0
- the whole mailbox: 19

## 4. Oracle. It must be 1.0, with all 17 checks passing

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h4 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h4\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-h4\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-h4\*) do @C:\turing\venv312\Scripts\python "%TASK%\solution\verify_gold_from_oracle.py" "%d\verifier\golden_trajectory.json" "%TASK%\solution\artifact_plan.json"
```

**What you need to see:**
- `1.0`;
- `51` and `0`;
- the line `OK: organised meetings, answers from invitations and email ...`.

If any of these fails, stop and send me the output and `...\verifier\test-stdout.txt`.

## 5. The battery: exactly 4 GLM runs, one at a time

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'])" glm-c1-h4 "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 1 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-c1-h4\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-h4\*) do @if exist "%d\exception.txt" echo CRASHED %~nxd
cd /d C:\harbor-jobs
tar -a -c -f C:\turing\scratch\c7_runs.zip --exclude=agent/opencode --exclude=agent/setup --exclude=*.log glm-c1-h4 oracle-c1-h4
```

## SEND

1. The `findstr` line from step 2.
2. `c7_calendar.txt`, `c7_mcp.txt`, `c7_doors.txt` and `c7_seedgone.txt`.
3. Step 4's three results.
4. The 4 rewards from step 5, and `c7_runs.zip`. Check it for `sk-` first.
