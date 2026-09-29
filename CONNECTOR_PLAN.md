# Connector tasks: what changes and the plan (Windows CMD)

Sources:
- *Connector Tasks Foundation Guidelines*: Trainer Guidelines, Local Setup, Onboarding, the Handbook (§1–§14), the Common Issues playbook, and Tips & Tricks.
- *Connector Onboarding Deck*.
- The 16 Sep demonstration notes.

Section numbers like §3.1 refer to the Handbook.

---

## 1. What is different

| | Non-connector (Day 3 task) | Connector |
|---|---|---|
| **Data** | Static files in `environment/input/` | A live **gym** (Slack, Snowflake, Supabase, GitHub, Linear, Notion, …): a FastAPI service over SQLite, with synthetic company data already seeded. The agent reaches it only through **MCP tools**. |
| **Agent's job** | Read files, compute, write deliverables | Call tools to find the data, write a deliverable, and often **change the service** (revoke, post, deploy, update) |
| **What is graded** | Files in `/app` | Files in **`/workspace`**, plus the **gym's database state** (`gym_step_state` checks), plus the **tool-call trajectory** (`tool_execution` checks). There may also be LLM-judge rubric items. |
| **Checks file** | `tests/verifier.json` | `tests/manifest.json` + `tests/rubric.toml` (+ `verifier_engine.py`) |
| **Environment** | `python:3.12-slim@sha256`, `input/` | `connectors-harness` / `benchmark-base` image (private, ~15 GB download, ~50 GB on disk); `entrypoint.sh`; `mcp/proxy/server.py` on **localhost:7000**; seed scripts; an `_app/` mirror of the task root; 3 users (`rlgymagent`, `gym`, `mcproxy`) |
| **task.toml** | `mcp_servers = []` | `[[metadata.mcp_servers_extended]]`, `[agent] user = "rlgymagent"`, `environment_mode = "shared"`, timeouts 4800/1500, `allow_internet = true`, a **required** `[environment.healthcheck]` (curl `--max-time 3`, `retries = 150`), and metadata blocks for INTENT / HIDDEN RULES / GOLD / DECOYS |
| **Reference solution** | `solve.sh` copies gold files | `solve.py` calls the gym's tools the way an agent would, and derives the figures at run time |
| **Signature defect** | Brittle prose checks (what we fought for 4 gate rounds) | The **proxy bypass (P-C1)**: one SQL `SELECT` through `/raw/{gym}/state` answers everything, and a verifier that grades only the deliverable pays full reward. It was found in 12 of 28 audited tasks. |
| **Where difficulty comes from** | Shape of the fixture data (withdrawn runs, revisions in force…) | **Interpretation** of the service's data (roles granted to roles, a load that "succeeded" but lost rows, a first deploy vs a later one), and a sanctioned workflow that really has to be performed. **Not** more rules, and not more data. |
| **Run time** | ~8 s oracle | 12 gyms boot in every container (30–40 s); 5–6 min per GLM trial; ~1 GB of job output per trial |

**Carries over unchanged:**
- the 4-run battery;
- strict pass = exactly 1.0;
- the band;
- oracle = 1.0 before any battery;
- a non-oracle solvability run;
- the forward and backward pass;
- predicting before hardening;
- evidence freshness (a battery counts only for the version it ran on);
- `review.csv` / `qc_report.html` / `evaluations/` packaging.

Our probe-suite habit also carries over. It becomes a **gold re-derivation script**: it re-computes every gold figure from the seeded gym and exits non-zero on any decoy/gold collision (Handbook §2.2, "Ship the harness").

**Never convert a task from one family to the other.** Renaming `verifier.json` to `manifest.json`, or adding `_app/` to a native task, is a packaging defect.

---

## 2. The rules that decide acceptance

- **Band:** 1/4 or 2/4 strict passes. 3/4 is accepted by the client but is the weakest place to sit; 4/4 is rejected; 0/4 only with a clean non-oracle solvability run and varied failure reasons.
- **Run exactly 4 attempts.** Report all 4 rewards, never the mean.
- **Order of work:** close the surface → re-measure → only then tune difficulty. "Too easy" is usually an open back door.
- **Four doors, all closed, proven as `rlgymagent` inside the running container:**
  1. the state route `GET /raw/{gym}/state?verify_queries=…`;
  2. the step route `POST /raw/{gym}/step`;
  3. the gym's own port (e.g. 8025 Snowflake, 8027 Supabase), which must answer 401/404;
  4. **files on disk**: the gym SQLite database, `/opt/proxy`, seed SQL. If the agent can read these, the other three doors don't matter.

  Probing as root proves nothing.
- **Grade the workflow:** add a `tool_execution` check that **names** the sanctioned tools, never an empty `expected_tools` list. The instruction must say the answers come from the connector. Don't require call order, a first call, or a minimum call count unless the instruction states it (P-C5). The oracle and every correct run must pass it (P-C9).
- **The judge needs a rubric:** if `rubric.toml` has zero items, no judge may gate the score (P-C4).
- **Every declared score bucket needs at least one check** (P-C7). No duplicate or implied checks, and the headline question must outweigh format checks (P-C8).
- **Silent corpus loss:** run the gold's query path **through the MCP tool** and confirm it returns the whole corpus the gold uses. Tool defaults (archived or private rows, bots) can hide rows.
- **`server.py` ships byte-identical to the reference.** The converter matches it by file hash. Some proxy designs also need the 11-line bootstrap anchor (12-space indent). Identify the proxy design first (~2,051, ~1,002 or ~821 lines).
- **Stability:** `harbor trial regrade` refuses under `shared` mode. Disclose the gap in `review.csv`; never fabricate repeats.
- **Migration sweep after any answer change.** Update all of these, then re-sync `_app/`:
  - `instruction.md`;
  - `manifest.json`: expected values, the prose of every `why_justification`, and `instruction_sha256`;
  - `rubric.toml`;
  - the `task.toml` metadata (GOLD / DECOYS / HIDDEN RULES);
  - `solution/`: `solve.py`, `final_answer`, `golden_trajectory`;
  - `README`;
  - `review.csv`.

---

## 3. The plan, phase by phase

**What runs where:** I can't run Docker, pull the gym image or reach the gym from here. You run the builds, probes and harbor jobs in CMD and paste me the output. I do everything that is reading, deciding, editing and scripting.

### Phase 0: one-time setup (before you claim a task)

1. **Access:** set up Cloudflare / Context-Aware Access with your Turing account. If you're blocked, post your email in the thread. The GCP project `delivery-g-obi` must be enabled for you.
2. **Pull the image once:**
   ```bat
   gcloud auth login
   gcloud auth configure-docker us-central1-docker.pkg.dev
   docker pull us-central1-docker.pkg.dev/delivery-g-obi/data-obi-rl-gym/benchmark-base:latest
   ```
   Never run `docker image prune -a`: it deletes this 15 GB image. The task's Dockerfile names the exact image to pull.
3. **Resources:**
   - disk: 64 GB free;
   - Docker VM memory: 16 GB if the host allows;
   - one trial at a time, or `-n 2` at most;
   - pass `--override-memory-mb 4096` on connector trials;
   - clean `C:\harbor-jobs` after each battery (~1 GB per trial).
4. **Env file:** add `set JUDGE_MODEL=openai/glm-5.2` and `set PYTHONUTF8=1` to `harbor-env.cmd`. The GLM config needs a `verifier.env` block passing `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `JUDGE_MODEL` to the verifier, so rubric checks are judged.
5. `harbor --version` must be 0.20.0 or newer.

### Phase 1: intake (15–30 min)

- Unzip and confirm the family from the files: `manifest.json`, `rubric.toml`, `_app/`, `mcp/proxy/server.py`, `mcp_servers_extended`.
- Send me the zip. I'll inventory it:
  - the gym;
  - the proxy design and its line count;
  - whether the anchor is present;
  - the `task.toml` settings against Handbook §1.4;
  - the manifest's buckets and checks;
  - the rubric items;
  - the judge config;
  - the gold;
  - the declared hidden rules and decoys;
  - `instruction_sha256`;
  - whether `_app/` matches the root.

### Phase 2: cold read and mapping (30–45 min)

- **Cold read** `instruction.md` with the gold hidden, and list every ask.
- **Forward pass** (every ask → a check) and **backward pass** (every check → the sentence that creates it). Remove or disclose anything untraceable (P-C5).
- Keep only `core` checks, but look before deleting: a `process` entry may be the only judged item.
- Check P-C4 (judge without a rubric), P-C7 (empty buckets) and P-C8 (duplicates and weighting).

### Phase 3: first oracle (30–60 min, the first build is slow)

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1 -n 1 -y
```

- `Healthcheck failed (rc=7, in_start_period=True)` while it boots is normal.
- Read `verifier\test-stdout.txt`, not `ctrf.json`.
- The oracle must be exactly 1.0. If the gold is right and a check rejects it, fix the check, never the gold.

### Phase 4: probe the live gym (Handbook §3.2)

Run these in the running container as the agent user (`docker exec -u rlgymagent …`):

1. Does the tenant database exist after reset?
2. What are the row counts of the tables the gold uses?
3. Can the agent reach each fact through a live `tools/call`?
4. Does a single call answer the task? If so, it's a lookup, not a task.

I'll write the exact commands for your task's gym.

### Phase 5: close the four doors (30–60 min)

Probe every door as `rlgymagent`:

```bat
docker exec -u rlgymagent <ctr> sh -c "curl -s \"http://localhost:7000/raw/<gym>/state?verify_queries=SELECT%201\"; curl -s -o /dev/null -w %{http_code} http://localhost:<gymport>/; ls -l /opt/proxy /gyms"
```

Every door must be refused. Fixes are in the entrypoint and Dockerfile, never in `server.py`:
- **Locked files:** directory permissions on `/opt/proxy` and `/gyms`.
- **State route:** gate it on a key readable only by root, and make it fail closed.
- **Step route:** gate it on the connector's tool allowlist.
- **Gym port:** turn on the gym's own auth. Client mode depends on the gym: on Snowflake it drops the whole database router; on Supabase it only gates the docs URLs.

Also add the fair `tool_execution` check, if the proxy design records a trace. Then re-run the oracle.

A latent route is a finding even if no run used it.

### Phase 6: measure (~35 min) and read the runs (30–45 min)

1. **Smoke run:** 1 GLM run.
2. **Battery:** exactly 4 runs:
   ```bat
   harbor run -c glm-harbor-config.json --agent-setup-timeout-multiplier 3 --override-memory-mb 4096 -n 2 -k 4 -y
   ```
3. **Read all 4 trajectories.** Classify each failure as one of:
   - a genuine model failure;
   - a verifier defect;
   - an instruction mismatch;
   - an infra problem;
   - a connector problem;
   - a judge error;
   - an ambiguous seed.

Only genuine model failures count as difficulty. A crash, or a missing `trajectory.json`, is void: replace the run. An agent timeout counts as a result.

### Phase 7: harden if needed (1–3 h per round)

1. **Write the prediction first:** which wrong answer we expect, and on which records.
2. **Use one lever**, preferably:
   - **Interpretation:** a policy the model must connect to a field, not `field >= N`.
   - **Precision:** exact sorted lists instead of counts.
   - **A coupled discriminator:** one rule that reads two fields together.
   - **Pin every fork:** where two rules both match a record, state which governs.
3. **Seed only if the baked data lacks the relation.** The seed runs at build time, with build-time assertions that fail the build on drift, and no answer words in the seeded text.
4. **Run the migration sweep** (Section 2), sync `_app/`, re-run the oracle, then re-run the battery.

Keep going until the battery is 1/4 or 2/4.

### Phase 8: package and QC (30–60 min)

1. **Build the package:**
   - `evaluations/difficulty/r1..r4` from the final battery;
   - `evaluations/solvability/r1`: a non-oracle run at 1.0, never the oracle;
   - the golden trajectory promoted from a full-reward run;
   - `README.md`;
   - `review.csv`.
2. **`review.csv` rules:**
   - exactly **14 rows + header, 5 columns**, byte-exact names;
   - `Layer 4 · Connectors, MCPs, and CLIs` must be **filled, not N/A** (the curl probe results go here);
   - Stability discloses the regrade gap;
   - both fold-ins are required: Rollout reasoning goes under Layer 2 Difficulty, and Failure attribution under Cross-trial · Calibration;
   - Cross-trial · Calibration ends with `Verdict: approve.` (or `change.` / `block.`);
   - `change_made` is empty on every PASS row;
   - the notes are a history.
3. **QC Pass 1:** the `/connector-task-reviewer` skill or `unified_qc.py`.
4. **QC Pass 2:** a fresh session verifies Pass 1.
5. **Upload:** upload → Delivery Gate / Harbor Check → add `qc_report.html` → re-zip from the sanitized tree → upload as a new version → submit.

---

## 4. Our Day 3 kit, adapted for connector tasks

| Day 3 tool | Connector version |
|---|---|
| `tests/probe_suite.py` (65 cases) | A gold re-derivation script over the seeded gym. It checks decoy/gold collisions, and replays wrong readings against the manifest checks. |
| `note_corpus.py` | The same idea for rubric or prose checks: must-pass and must-fail answers. |
| `assemble_evidence.py` | Same job. The deliverables live under `/workspace`, and it must also keep proxy/trace evidence, not only the deliverables. |
| Containment check (`find / -name solve.sh`) | The four-door probe as `rlgymagent`, plus `_app/` vs root `diff -r`. |
| `before_inputs.txt` hashes | `instruction_sha256` in the manifest, plus `task_checksum` in every `result.json`. |

---

## 5. Contradictions between the documents: ask your lead

1. **Runs and band:**
   - the Trainer Guidelines say 4 runs, pass rate ≤ 50%;
   - the Local Setup section says 5 runs and the *mean reward*;
   - the Handbook and playbook say exactly 4 runs, strict passes, 1–2/4.

   **We follow the Handbook.**
2. **Base image:** the guidelines say `benchmark-base:latest`, but the demo and Handbook say `connectors-harness@sha256`. Use whatever the task's Dockerfile pins.
3. **The 11-line anchor:**
   - the Handbook says it is a block inside `server.py` `bootstrap()`, and only some proxy designs carry it;
   - the demo describes it as a YAML block in the task file.

   Check it against the task's actual design.
4. **A P-C1 probe that returns a row:** it's an open question whether to hold the task, or ship it with the stopgap `tool_execution` check until the proxy image is fixed.
5. **Removing `[metadata.verifier_judge]`** when `rubric.toml` is empty needs the lead's OK.
6. **QC tool:** `unified_qc.py` vs the `/connector-task-reviewer` skill. The demo says QC v2 is used for both families.

---

## 6. What to send me with the task

1. The task zip, as downloaded from the tracker.
2. The output of:
   ```bat
   docker images
   harbor --version
   ```
   plus your free disk space and RAM.
3. After Phase 3: the oracle's `reward.txt` and `test-stdout.txt`.
