# Notes for the review form (review.csv)

**This is a fact sheet, not the review.** The QC brief requires that a human writes `review.csv` through the review form.

For each row:
1. Check the facts yourself.
2. Write the notes in your own words.
3. Pick the status.

Header, which the form writes for you: `review_check,status,review_notes,change_made,what_to_record`

| review_check | Suggested status | Facts you can check and use |
|---|---|---|
| Layer 1 · Package consistency | FIXED_AND_VERIFIED | **Found:** `task.toml` had `artifacts = []`; `consistency/` and `evaluations/oracle`/`nop` were not in the allowed tree; `tests/manifest.json` was missing. **Changed:** artifacts list the 3 `/app` deliverables; those folders removed; `manifest.json` added, byte-identical to `verifier.json`. **Recheck:** deliverable names identical in `instruction.md`, `submission_format.md`, `task.toml`, `verifier.json` and `solution/files`; `fc /b` shows no differences; oracle 1.0. |
| Layer 1 · Clarity and scope | FIXED_AND_VERIFIED | **Found:** template block ("must be your final action; confirm each one exists", "Working environment") (INS-1/INS-13); relative paths; T2 "touching that component" readable two ways (C-01/C-15 flip); T8 "counted by neither" with three counts. **Changed:** instruction rewritten, about 150 words, with `/app` paths; T4 names the `component_id`; T10 "none of them"; T7 kind must equal the T6 kind. **Recheck:** probe decoy W10 (whole-product reading) fails; oracle 1.0. |
| Layer 1 · Realism and leakage | FIXED_AND_VERIFIED | **Found:** `submission_format.md` described regex behaviour and demanded "at least sixty words"; editorial hints. **Changed:** note section is 3 plain facts; word floor removed. **Checked:** no count, total or answer in the instruction; examples are placeholders (`C-00`, `XX-0-0-X`). |
| Layer 2 Difficulty | FIXED_AND_VERIFIED | **Found:** the cleaned but unhardened version passed every GLM run (too easy). **Changed:** rules Rev C, T1–T10: withdrawn runs, dated revisions in force on 2026-09-15, DN sizes, discontinued catalogue rows, size+thread per end; expected wrong readings W1–W10 declared before the battery. **Recheck:** `glm-4x-day3` → rewards in `evaluations/difficulty/r1..r4/verifier/reward.txt` = 1.0, 0.0, 1.0, 1.0 (3/4); r2 failure is MODEL (W1: TJ-150 discharge taken from the retailer listing). |
| Layer 2 Solvability | FIXED_AND_VERIFIED (or PASS) | `evaluations/solvability/r1` = GLM-5.2 run `glm-smoke-day3`, reward 1.0, not the oracle; its trajectory is also `solution/golden_trajectory.json` (the old synthetic one was replaced). |
| Layer 2 Stability | leave blank, or "Turing runs this" | — |
| Layer 3 Oracle Mode | FIXED_AND_VERIFIED | **Found:** every text file was CRLF; under plain Linux bash, `solve.sh` stops at `set -euo pipefail`. Harbor on Windows still scored 1.0, but the client replays on Linux. **Changed:** all files LF; `solve.sh` accepts the ATIF golden trajectory. **Recheck:** oracle 1.0 on `oracle-day3` and on the assembled bundle (`oracle-submit`). |
| Layer 4 · Environment and files | FIXED_AND_VERIFIED | **Changed:** base image pinned by digest; `.dockerignore` admits `input/` only; `network_mode` stays `public` (ENV-4 exception: `no-network` broke the opencode agent's setup, job `glm-smoke-day2`). **Recheck:** containment command output (paste yours); all inputs LF and hash-pinned in `tests/input_hashes.json`. |
| Layer 4 · Connectors, MCPs, and CLIs | N/A | Non-connector task: `mcp_servers = []`, no `environment/mcp/`, no connector manifest. |
| Layer 4 · Deliverables and artifact quality | PASS (or FIXED_AND_VERIFIED if you count the note contract change) | CSV register, markdown supplier note and JSON totals are realistic carriers for a homeowner's take-off; each shipped run holds the graded deliverables. |
| Layer 5 · Verifier coverage and fairness | FIXED_AND_VERIFIED | **Found:** 6 of 13 checks were incidental (not core), 2 were existence-only, and the note checks were brittle long regexes. **Changed:** 7 core checks, one per ask (header, table, figures, 2 note counts, 1 per unresolved ID), loose note matching, every `why_justification` quoting the sentence it enforces. **Recheck:** `tests/probe_suite.py` 43 cases, `PROBLEMS: 0` (8 equivalent rewrites pass, 11 breaks and 10 decoys fail on the right checks). |
| Layer 5 · LLM judge consistency | N/A | No LLM judge: every check is deterministic (regex, `table_equals`, `object_equals`). |
| Layer 5 · Reward hacking and exploitability | FIXED_AND_VERIFIED | **Changed:** `test.sh` runs from `/tests` with `python3 -I`, fixed PATH, no PYTHONPATH, `--rootdir=/tests`, no pytest cache, and writes `reward.txt` first. **Recheck:** symlinked deliverables score 0.0; an empty workspace scores 0.0; planted `conftest.py`/`sitecustomize.py` have no effect; the degenerate floor (majority class, pasted instruction, copied input) scores 0. |
| Cross-trial · Calibration | leave blank, or "Turing runs this" | — |
