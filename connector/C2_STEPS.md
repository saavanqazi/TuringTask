# Connector task 1: round 2. Apply the fixes, re-prove the doors, oracle, first GLM run (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_fix1.zip` and `probe_gymport.sh` into `C:\turing\scratch\` first.

---

## 1. Apply the three fixes (5 files)

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_fix1.zip
git status --short
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
```

- `git status` must show exactly 5 `M` lines: `task.toml`, `tests/manifest.json`, `environment/Dockerfile`, `environment/_app/task.toml` and `environment/_app/tests/manifest.json`.
- All three `fc` commands must say `no differences encountered`. That confirms the `_app` mirror matches the task root.

Then commit:

```bat
git add -A
git commit -m "Fix: name the sanctioned tools in tool_execution; healthcheck --max-time 3, 150 retries; lock /opt/proxy to root:harborproxy"
```

## 2. Re-prove the doors on the rebuilt image

```bat
docker rm -f c1probe 2>nul
docker build -t c1probe-img "%TASK%\environment"
docker run -d --name c1probe c1probe-img
```

The build must finish without errors. The new `RUN` step checks its own result and fails the build if the lock didn't apply.

Wait about 30 seconds, then run this until it prints `{"status":"ok"}`:

```bat
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
```

Then run all the probes:

```bat
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker cp C:\turing\scratch\probe_gymport.sh c1probe:/tmp/probe_gymport.sh
docker exec c1probe chmod 644 /tmp/probe_doors.sh /tmp/probe_gymport.sh
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c2_doors.txt 2>&1
docker exec -u rlgymagent c1probe sh /tmp/probe_gymport.sh > C:\turing\scratch\c2_gymport.txt 2>&1
docker exec c1probe sh -c "ls -ld /opt/proxy; ls -l /opt/proxy; pgrep -a -u harborproxy | head -3; curl -s -m 3 http://127.0.0.1:7000/health" > C:\turing\scratch\c2_root.txt 2>&1
docker rm -f c1probe
```

In `c2_doors.txt`, the line that said `OPEN? /opt/proxy/server.py is readable by the agent` must now say `closed: /opt/proxy/server.py unreadable`. `c2_root.txt` must still end with `{"status":"ok"}`, which shows the proxy still starts after the lock.

## 3. Oracle on the fixed task. It must print 1.0

Close heavy apps first.

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-fix1 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-fix1\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-fix1\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
for /d %d in (C:\harbor-jobs\oracle-c1-fix1\*) do @findstr /c:"Expected tools" /c:"missing_tools" "%d\verifier\test-stdout.txt"
```

- You need `1.0`, then `45` and `0`.
- If a run ends in `HealthcheckError` again, re-run it once with job name `oracle-c1-fix1b`. It is void, not a failure.

## 4. One GLM run (smoke test)

Point your GLM config at this task. This sets the task path and job name, and makes sure the judge model reaches the verifier:

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; d['jobs_dir']=r'C:\harbor-jobs'; d.setdefault('verifier',{}).setdefault('env',{}); d['verifier']['env']['JUDGE_MODEL']='openai/glm-5.2'; d['verifier']['env']['OPENAI_API_KEY']='${OPENAI_API_KEY}'; d['verifier']['env']['OPENAI_BASE_URL']='${OPENAI_BASE_URL}'; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'], d['verifier']['env'].get('JUDGE_MODEL'))" glm-c1-smoke "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 1 -y
```

Then read the result:

```bat
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\exception.txt" (echo CRASHED %~nxd & powershell -NoProfile -Command "Get-Content '%d\exception.txt' -Tail 8")
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\verifier\test-stdout.txt" findstr /c:"\"name\"" /c:"\"passed\"" "%d\verifier\test-stdout.txt" > C:\turing\scratch\c2_smoke_checks.txt
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\artifacts" dir /s /b "%d\artifacts" | findstr /i metrics
```

- If it crashed with `exit code 137` or an OOM message, that's a memory problem, not the task. Tell me, and I'll give you the pre-baked-agent Dockerfile change.
- If it crashed for any other reason, send me the lines it printed.

---

## SEND

1. The 5-line `git status` from step 1, and the three `fc` results.
2. `c2_doors.txt`, `c2_gymport.txt` and `c2_root.txt`.
3. The oracle output: `1.0`, `45 / 0`, and the `Expected tools` line.
4. The smoke run: its reward (or crash lines), plus `c2_smoke_checks.txt`.
