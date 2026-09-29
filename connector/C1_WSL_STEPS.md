# Running harbor from Linux while typing in CMD (connector tasks)

**Why:** the connector `entrypoint.sh` locks `/logs/verifier` to `root:root 700` and exits 70 if it can't. Harbor mounts `/logs/*` from its job folder. From `C:\harbor-jobs`, a Windows folder ignores chmod, so the container dies and harbor reports `HealthcheckError`. From a Linux folder (`~/harbor-jobs`) it works.

**How:** you still type every command in CMD. Each harbor command starts with `wsl -d Ubuntu-24.04 --`, which runs that one command inside Ubuntu and prints the output in your CMD window.

Do this only after step 1 (the `c1win` / `c1vol` test) showed `c1win Exited (70)`.

---

## A. Install Ubuntu (one time)

```bat
wsl -l -v
```

- If `Ubuntu-24.04` is already listed, skip to B.
- Otherwise run:

```bat
wsl --install -d Ubuntu-24.04
```

It opens an Ubuntu window and asks for a new Linux username and password; pick anything and remember the password. Then type `exit` to close that window. If Windows asks you to reboot, reboot.

## B. Connect Ubuntu to Docker Desktop (one time)

1. Open Docker Desktop → Settings → Resources → WSL integration.
2. Switch on **Ubuntu-24.04**.
3. Click **Apply & restart**.

Check it from CMD:

```bat
wsl -d Ubuntu-24.04 -- docker images
```

It must list the `connectors-harness` image you pulled; Ubuntu uses the same Docker, so there is no second 15 GB download.

## C. Install harbor inside Ubuntu (one time)

```bat
wsl -d Ubuntu-24.04 -- bash -lc "curl -LsSf https://astral.sh/uv/install.sh | sh"
wsl -d Ubuntu-24.04 -- bash -lc "~/.local/bin/uv tool install --python 3.12 harbor && ~/.local/bin/harbor --version"
```

The last line must print `0.20.0` or newer. `uv` downloads Python 3.12 by itself.

## D. Pass your key into Ubuntu without writing it anywhere (every CMD window)

Run your usual env file, then tell Windows which variables to pass through to Linux:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set WSLENV=OPENAI_API_KEY/u:OPENAI_BASE_URL/u:JUDGE_MODEL/u
wsl -d Ubuntu-24.04 -- bash -lc "echo base=$OPENAI_BASE_URL judge=$JUDGE_MODEL keylen=${#OPENAI_API_KEY}"
```

It should print your base URL, `openai/glm-5.2`, and a key length that is not 0. The key itself is not printed.

To make this automatic, add the `set WSLENV=...` line to the end of `harbor-env.cmd`.

## E. Copy the task into Ubuntu (repeat after every edit)

You keep editing and committing in `C:\turing\conn`, and copy the task into Linux before each run:

```bat
wsl -d Ubuntu-24.04 -- bash -lc "mkdir -p ~/conn ~/harbor-jobs && rm -rf ~/conn/the-meetings-still-waiting-on-a-yes && cp -r /mnt/c/turing/conn/the-meetings-still-waiting-on-a-yes ~/conn/ && ls ~/conn/the-meetings-still-waiting-on-a-yes"
```

## F. Oracle (must print 1.0)

```bat
wsl -d Ubuntu-24.04 -- bash -lc "cd ~/conn && ~/.local/bin/harbor run -p ~/conn/the-meetings-still-waiting-on-a-yes -a oracle --ve OPENAI_API_KEY=$OPENAI_API_KEY --ve OPENAI_BASE_URL=$OPENAI_BASE_URL --ve JUDGE_MODEL=$JUDGE_MODEL -o ~/harbor-jobs --job-name oracle-c1-mined -n 1 -y"
wsl -d Ubuntu-24.04 -- bash -lc "cat ~/harbor-jobs/oracle-c1-mined/*/verifier/reward.txt; echo; cat ~/harbor-jobs/oracle-c1-mined/*/exception.txt 2>/dev/null | tail -5"
```

Keep the `$` signs exactly as written: Ubuntu fills them in from the variables passed in step D.

**SEND:** both outputs.

To browse the results in Windows Explorer, open `\\wsl$\Ubuntu-24.04\home\<your-linux-user>\harbor-jobs`.

---

After the oracle prints 1.0, the probes (step 6 of `C1_STEPS.md`) run unchanged from CMD. They use plain `docker`, which works from Windows.
