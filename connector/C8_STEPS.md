# Connector task 1: round 8. Hardening 5 (exact lists, tracker reconciliation, new traps): build, probe, oracle, battery (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_harden5.zip` and `probes\probe_h5.py` into `C:\turing\scratch\` first (`probe_doors.sh` is already there). Close heavy apps before steps 2–5.

## 1. Apply and commit (14 files)

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_harden5.zip
git status --short
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
git add -A
git commit -m "Hardening 5: RSVP ledger (15 rows) and tracker fixes (8 rows) instead of counts; last answer on either channel wins; conditional yes, stand-in, cancelled meeting"
```

`git status` must show 14 `M` lines, and all three `fc` commands must say `no differences encountered`.

## 2. Build. The seed must run

```bat
docker build --progress=plain -t c1probe-img "%TASK%\environment" > C:\turing\scratch\c8_build.txt 2>&1
findstr /c:"seeded 14 messages" /c:"SEED FAILED" /c:"ERROR" C:\turing\scratch\c8_build.txt
```

It must print `seeded 14 messages, 2 meeting moves, answer times on 5 meetings and 1 cancelled meeting ...`. If it prints `SEED FAILED`, stop and send me `c8_build.txt`.

## 3. Probe what the agent sees, and that the doors stay closed

```bat
docker rm -f c1probe 2>nul
docker run -d --name c1probe c1probe-img
ping -n 91 127.0.0.1 >nul
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
docker cp C:\turing\scratch\probe_h5.py c1probe:/tmp/probe_h5.py
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker exec c1probe chmod 644 /tmp/probe_h5.py /tmp/probe_doors.sh
docker exec -u rlgymagent c1probe python3 /tmp/probe_h5.py > C:\turing\scratch\c8_probe.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c8_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh -c "ls /tmp/task-seed 2>&1; find / -xdev -name 'seed_outlook_*.py' 2>/dev/null | head -3" > C:\turing\scratch\c8_seedgone.txt 2>&1
docker rm -f c1probe
type C:\turing\scratch\c8_probe.txt
```

**What `c8_probe.txt` must show:**

Calendar:
- **Learning Time, Brainstorm: New Feature and the 2 May Weekly Pipeline Review:**
  - `lastModified` is `2026-04-24T17:..Z`;
  - every answered attendee has a real time, not `0001-01-01`.
- **Weekly Pipeline Review (2 May):**
  - Jasmine Porter `declined 2026-05-01T20:00:00Z`;
  - Jared Ellis `declined 2026-04-29T23:00:00Z`.
- **Customer Advisory Board prep (12 May):** `isCancelled=True` with `Cancelled on 4 May` in the body. If it is missing altogether, just tell me: the gym may hide cancelled meetings, which is harmless.
- **OKR Planning and the 6 May review:** the move notes, as in round 7.

Mailbox:
- `MAILBOX: 23 messages`.
- **Janice Gray's `RSVP tracker`:** all seven lines, from `OKR Planning (Thu 30 Apr): ...` to `Customer Advisory Board prep (Tue 12 May): ...`.
- **The new emails:** Jasmine's `Saturday review`, Diego's `Wednesday` and Jenna's `Wednesday's review`.

If any of these is missing or cut short, stop and send me `c8_probe.txt`: it would mean the agent can't see what the task depends on.

`c8_seedgone.txt` must say `No such file or directory`, with no file listed.

## 4. Oracle. It must be 1.0, with all 39 checks passing

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h5 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h5\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-h5\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-h5\*) do @C:\turing\venv312\Scripts\python "%TASK%\solution\verify_gold_from_oracle.py" "%d\verifier\golden_trajectory.json" "%TASK%\solution\artifact_plan.json"
```

**What you need to see:**
- `1.0`;
- `117` and `0` (39 checks, each listed 3 times);
- the line `OK: 5 meetings, 15 ledger rows, 8 tracker fixes, chase set and reply threads re-derived from the served gym`.

If any of these fails, stop and send me the output and `...\verifier\test-stdout.txt`.

## 5. The battery: exactly 4 GLM runs, two at a time

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'])" glm-c1-h5 "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 2 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-c1-h5\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-h5\*) do @if exist "%d\exception.txt" echo CRASHED %~nxd
cd /d C:\harbor-jobs
tar -a -c -f C:\turing\scratch\c8_runs.zip --exclude=agent/opencode --exclude=agent/setup --exclude=*.log glm-c1-h5 oracle-c1-h5
```

If a run crashes with exit code 137 or an out-of-memory message, re-run the battery with `-n 1` instead of `-n 2`. A crashed run is void and doesn't count.

## SEND

1. The `findstr` line from step 2.
2. `c8_probe.txt`, `c8_doors.txt` and `c8_seedgone.txt`.
3. Step 4's three results.
4. The 4 rewards from step 5, and `c8_runs.zip`. Check it for `sk-` first. The only matches should be the harmless words `task-execution` and `task-seed`.
