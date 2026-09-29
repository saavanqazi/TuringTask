# Connector task 1: `the-meetings-still-waiting-on-a-yes`. Steps 1–6 (Windows CMD)

Goal of this round: set the machine up, get the task's **oracle to 1.0 on your machine exactly as mined**, and **probe the gym and its four doors as the agent user**. No task edits yet. Send me the outputs marked **SEND**.

Your machine: 95.8 GB free disk (enough; the image is about 50 GB), 16 GB RAM (tight: Docker capped at 10 GB, one trial at a time), harbor 0.23.0. Everything here is CMD; you never need a WSL terminal.

---

## 1. Cap Docker's memory at 10 GB

Your laptop has 16 GB, with about 12 GB already in use by Windows and open apps. Giving Docker all of it can freeze or kill the host (Handbook §7), so cap it at 10 GB and run one trial at a time.

Docker Desktop runs its Linux engine inside WSL2 in the background. You never open a WSL terminal: everything below is CMD. This file only sets how much memory that background engine may use.

```bat
notepad %USERPROFILE%\.wslconfig
```

Put exactly this in the file and save:

```
[wsl2]
memory=10GB
swap=8GB
```

Then:

```bat
wsl --shutdown
```

Restart Docker Desktop, wait for the whale icon to settle, then run:

```bat
docker info | findstr /c:"Total Memory" /c:"Operating System"
```

- It should show about 9.7 GiB.
- If it still shows about 15 GiB, Docker Desktop is on the Hyper-V backend and ignores `.wslconfig`. Set the memory in Docker Desktop → Settings → Resources → Memory = 10 GB instead.

**Before every build, oracle or GLM run, close Chrome, Teams and other heavy apps.**
- Each task container gets 4 GB, and all 12 gyms boot inside it.
- The runs need about 6 GB free on Windows.
- A container killed for lack of memory (exit code 137) is not a task failure. Free memory and re-run it.

## 2. Registry access and the exact image

```bat
gcloud --version
```

If it says "not recognized", install the gcloud CLI from https://cloud.google.com/sdk/docs/install#windows, then open a **new** CMD window.

```bat
gcloud auth login
gcloud auth configure-docker us-central1-docker.pkg.dev
gcloud config set project delivery-g-obi
docker pull us-central1-docker.pkg.dev/delivery-g-obi/connectors-rl-gym/connectors-harness@sha256:b1374cd8a392ea66f9a649e700a1498e8fcb03ee35776362db7cc15dc3049b89
docker images
```

- The pull is about 15 GB, so let it finish.
- If it says `denied` or `403`, stop and ask your lead for `delivery-g-obi` Artifact Registry access. Don't try to work around it.
- Never run `docker image prune -a`: it deletes this image.

## 3. Add the judge settings to your env file

Two checks in this task are graded by an LLM judge, so the verifier needs `JUDGE_MODEL`.

```bat
notepad "%USERPROFILE%\.config\harbor\harbor-env.cmd"
```

Add these two lines at the end and save:

```
set JUDGE_MODEL=openai/glm-5.2
set PYTHONUTF8=1
```

## 4. Unpack the task into its own git folder

Save the task zip as `C:\turing\scratch\meetings.zip` first.

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
mkdir C:\turing\conn
cd /d C:\turing\conn
tar -xf C:\turing\scratch\meetings.zip
git init
git config core.autocrlf false
git add -A
git commit -m "Mined connector task as downloaded"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
dir /b "%TASK%"
```

`dir` should list `consistency`, `environment`, `evaluations`, `instruction.md`, `solution`, `task.toml` and `tests`.

## 5. Oracle on the task as mined. It must print 1.0

The first build takes a while. While it waits you will see repeated `Healthcheck failed (rc=7, in_start_period=True)` lines; that is normal while the 12 gyms boot.

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-mined -n 1 -y
for /d %d in (C:\harbor-jobs\oracle-c1-mined\*) do @if exist "%d\verifier\reward.txt" type "%d\verifier\reward.txt"
for /d %d in (C:\harbor-jobs\oracle-c1-mined\*) do @if exist "%d\exception.txt" type "%d\exception.txt"
```

**SEND:** the reward line, and anything the `exception.txt` line prints.

- If there is no reward and no exception, also send the last 40 lines of `C:\harbor-jobs\oracle-c1-mined\job.log`.
- If the verifier printed a judge error, send `C:\harbor-jobs\oracle-c1-mined\<trial>\verifier\test-stdout.txt`.

## 6. Probe the four doors and the gym, as the agent user

Save the two probe files I sent (`probe_doors.sh` and `probe_mcp.py`) into `C:\turing\scratch\`.

**6a. Build and start a standalone copy of the task container:**

```bat
docker build -t c1probe-img "%TASK%\environment"
docker run -d --name c1probe c1probe-img
```

**6b. Wait until the proxy answers.** Wait about a minute, then run:

```bat
docker exec c1probe curl -s -m 3 http://127.0.0.1:7000/health
```

- Repeat every 20 seconds until it prints something like `{"status":"ok"...}`.
- If it hasn't answered after 3 minutes, send me the output of `docker logs c1probe`.

**6c. Run both probes as `rlgymagent`, not root:**

```bat
docker cp C:\turing\scratch\probe_doors.sh c1probe:/tmp/probe_doors.sh
docker cp C:\turing\scratch\probe_mcp.py c1probe:/tmp/probe_mcp.py
docker exec c1probe chmod 644 /tmp/probe_doors.sh /tmp/probe_mcp.py
docker exec -u rlgymagent c1probe sh /tmp/probe_doors.sh > C:\turing\scratch\c1_doors.txt 2>&1
docker exec -u rlgymagent c1probe python3 /tmp/probe_mcp.py > C:\turing\scratch\c1_mcp.txt 2>&1
docker exec c1probe sh -c "grep -A3 -i 'program:outlook' /etc/supervisor/conf.d/supervisord.conf; echo; ls -l /opt/proxy /gyms | head -20" > C:\turing\scratch\c1_root.txt 2>&1
```

**6d. Clean up:**

```bat
docker rm -f c1probe
```

**SEND:** the three files `c1_doors.txt`, `c1_mcp.txt` and `c1_root.txt`. Upload them, or paste them if they are short.

---

## After you send them

I will then:
1. Confirm each of the four doors is closed, or give the fix for any that is open. `/opt/proxy` being readable by the agent is likely; the fix is a Dockerfile change, with `server.py` left untouched.
2. Make the checks-only fixes found at intake:
   - the `tool_execution` check has an empty tool list and a bare 3-call floor. I'll change it to name `search_calendar`, `search_email` and `draft_email`.
   - the healthcheck gets `--max-time 3` and 150 retries.
3. Send the edited files and the oracle / smoke / battery steps.
