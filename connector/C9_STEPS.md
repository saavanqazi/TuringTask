# Connector task 1: round 9. Hardening 6 (nine meetings, cross-message answers, window edges, seven drafts): build, probe, oracle, battery (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_harden6.zip` into `C:\turing\scratch\` first (`probe_h5.py` and `probe_doors.sh` are already there). Close heavy apps before steps 2–5.

## 1. Apply and commit (13 files)

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_harden6.zip
git status --short
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
git add -A
git commit -m "Hardening 6: nine meetings, 31 ledger rows, 12 tracker fixes, seven drafts; conditional yeses settled by later notes; quoted reply; window edges"
```

`git status` must show 13 `M` lines, and all three `fc` commands must say `no differences encountered`.

## 2. Build. The seed must run

```bat
docker build --progress=plain -t c1probe-img "%TASK%\environment" > C:\turing\scratch\c9_build.txt 2>&1
findstr /c:"seeded 23 messages" /c:"SEED FAILED" /c:"ERROR" C:\turing\scratch\c9_build.txt
```

It must print `seeded 23 messages, 2 meeting moves, answer times on 5 meetings and 6 new meetings ...`. If it prints `SEED FAILED`, stop and send me `c9_build.txt`.

## 3. Probe what the agent sees, and that the doors stay closed

```bat
docker rm -f c1probe 2>nul
docker run -d --name c1probe c1probe-img
ping -n 91 127.0.0.1 >nul
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
docker cp C:\turing\scratch\probe_h5.py c1probe:/tmp/probe_h5.py
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker exec c1probe chmod 644 /tmp/probe_h5.py /tmp/probe_doors.sh
docker exec -u rlgymagent c1probe python3 /tmp/probe_h5.py > C:\turing\scratch\c9_probe.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c9_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh -c "ls /tmp/task-seed 2>&1; find / -xdev -name 'seed_outlook_*.py' 2>/dev/null | head -3" > C:\turing\scratch\c9_seedgone.txt 2>&1
docker rm -f c1probe
type C:\turing\scratch\c9_probe.txt
```

**What `c9_probe.txt` must show:**

Calendar:
- `CALENDAR: 16 events in the window`.
- **Four new meetings, each `isCancelled=False`:**
  - Vendor Security Review on `2026-05-07T14:00`;
  - Q3 Roadmap Review on `2026-05-11T09:30`;
  - Hiring Panel Debrief on `2026-05-15T15:00`;
  - Customer Escalation Sync on `2026-05-17T17:30`.
- **Their attendees:** answer times as seeded, and `0001-01-01` only for unanswered rows.
- **Customer Advisory Board prep:** still `isCancelled=True`.
- **Planning Offsite Prep** (26 April 21:00 Pacific) must **not** appear: the probe searches from 27 April Pacific.

Mailbox:
- `MAILBOX: 32 messages`.
- **Janice Gray's `RSVP tracker`:** dated `2026-05-11T15:02:00Z`, with all eleven lines, from `OKR Planning (Thu 30 Apr)` to `Planning Offsite Prep (Sun 26 Apr)`.
- **The new notes:** Kenneth Hall's `Forecast` (`2026-05-06T05:40:00Z`), Nora Ford's `Board deck` (`2026-05-09T02:35:00Z`), and Jack Henry's `RE: Thursday's security review`, with the quoted lines starting with `>`.

If any of these is missing or cut short, stop and send me `c9_probe.txt`.

`c9_seedgone.txt` must say `No such file or directory`, with no file listed.

## 4. Oracle. It must be 1.0, with all 67 checks passing

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h6 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h6\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-h6\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-h6\*) do @C:\turing\venv312\Scripts\python "%TASK%\solution\verify_gold_from_oracle.py" "%d\verifier\golden_trajectory.json" "%TASK%\solution\artifact_plan.json"
```

**What you need to see:**
- `1.0`;
- `201` and `0` (67 checks, each listed 3 times);
- the line `OK: 9 meetings, 31 ledger rows, 12 tracker fixes, chase set and reply threads re-derived from the served gym`.

If any of these fails, stop and send me the output and `...\verifier\test-stdout.txt`.

## 5. The battery: exactly 4 GLM runs, two at a time

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'])" glm-c1-h6 "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 2 -k 4 -y
for /d %d in (C:\harbor-jobs\glm-c1-h6\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-h6\*) do @if exist "%d\exception.txt" echo CRASHED %~nxd
cd /d C:\harbor-jobs
tar -a -c -f C:\turing\scratch\c9_runs.zip --exclude=agent/opencode --exclude=agent/setup --exclude=*.log glm-c1-h6 oracle-c1-h6
```

If a run crashes with exit code 137 or an out-of-memory message, re-run the battery with `-n 1` instead of `-n 2`. A crashed run is void and doesn't count.

## SEND

1. The `findstr` line from step 2.
2. `c9_probe.txt`, `c9_doors.txt` and `c9_seedgone.txt`.
3. Step 4's three results.
4. The 4 rewards from step 5, and `c9_runs.zip`. Check it for `sk-` first. The only matches should be the harmless words `task-execution` and `task-seed`.
