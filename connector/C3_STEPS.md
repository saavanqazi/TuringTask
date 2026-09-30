# Connector task 1: round 3. Startup fix, then oracle and the first GLM run (Windows CMD)

Start every CMD window with the lines below. Use your new key, placed only in `harbor-env.cmd`, and never type it in the window.

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save `c1_fix2.zip` into `C:\turing\scratch\` first.

## 1. Apply the fix (1 file) and commit

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_fix2.zip
git status --short
git add -A
git commit -m "Fix: entrypoint waits up to 240 s for the proxy (40 s was too short under cpus=2, memory 4 GB)"
```

`git status` must show exactly one line: ` M the-meetings-still-waiting-on-a-yes/environment/entrypoint.sh`.

## 2. Prove it starts under harbor's limits

```bat
docker rm -f c1cpu 2>nul
docker build -t c1probe-img "%TASK%\environment"
docker run -d --name c1cpu --cpus 2 --memory 4g c1probe-img
for /l %i in (1,1,15) do @(echo --- %i & docker ps -a --filter name=c1cpu --format "{{.Status}}" & docker exec c1cpu curl -s -m 2 http://127.0.0.1:7000/health & echo. & ping -n 11 127.0.0.1 >nul)
docker exec c1cpu sh -c "grep -m1 CRIT /run/harbor/services/supervisord.log; grep -m1 'upstream=' /run/harbor/proxy/harbor-mcp-proxy.log; grep -m1 'GET http://127.0.0.1:8014/health' /run/harbor/proxy/harbor-mcp-proxy.log; grep -m1 'public proxy listening' /run/harbor/proxy/harbor-mcp-proxy.log" > C:\turing\scratch\c3_timing.txt 2>&1
docker rm -f c1cpu
```

The status must stay `Up` all the way through, and `{"status":"ok"}` must appear by round 15 at the latest. `c3_timing.txt` then shows how many seconds the start took on your machine.

## 3. Oracle. It must print 1.0

Close heavy apps first.

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-fix2 -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-fix2\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-fix2\*) do @if exist "%d\verifier\verifier_summary.json" (findstr /c:"\"passed\": true" "%d\verifier\verifier_summary.json" | find /c /v "" & findstr /c:"\"passed\": false" "%d\verifier\verifier_summary.json" | find /c /v "")
```

You need `1.0`, then `45` and `0`.

## 4. One GLM run (smoke test)

Point your GLM config at this task:

```bat
cd /d C:\turing\scratch
C:\turing\venv312\Scripts\python -c "import json,sys; p=r'C:\turing\scratch\glm-harbor-config.json'; d=json.load(open(p)); d['job_name']=sys.argv[1]; d['tasks']=[{'path':sys.argv[2]}]; d['jobs_dir']=r'C:\harbor-jobs'; d['n_concurrent_trials']=1; v=d.setdefault('verifier',{}).setdefault('env',{}); v['JUDGE_MODEL']='openai/glm-5.2'; v['OPENAI_API_KEY']='${OPENAI_API_KEY}'; v['OPENAI_BASE_URL']='${OPENAI_BASE_URL}'; json.dump(d,open(p,'w'),indent=2); print(d['job_name'], d['tasks'], v['JUDGE_MODEL'])" glm-c1-smoke "%TASK%"
harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 -n 1 -y
```

Then read the result:

```bat
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\exception.txt" (echo CRASHED %~nxd & powershell -NoProfile -Command "Get-Content '%d\exception.txt' -Tail 8")
for /d %d in (C:\harbor-jobs\glm-c1-smoke\*) do @if exist "%d\verifier\test-stdout.txt" copy /y "%d\verifier\test-stdout.txt" C:\turing\scratch\c3_smoke_stdout.txt
```

If it crashed with `exit code 137` or an OOM message, that's memory, not the task. Tell me, and I'll give you the pre-baked-agent change.

## SEND

1. The `git status` line from step 1.
2. The 15 status lines from step 2, and `c3_timing.txt`.
3. The oracle output: `1.0`, `45 / 0`.
4. The smoke run: the reward (or crash lines), and `c3_smoke_stdout.txt`.

Before sending any output, check it contains no line with `sk-`.
