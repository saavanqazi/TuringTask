import json, hashlib, sys
from pathlib import Path
T = Path(sys.argv[1])
plan = json.loads((T / "solution/artifact_plan.json").read_text())
man = json.loads((T / "tests/manifest.json").read_text())
V = man["verifier_configs"]
sha = hashlib.sha256((T / "instruction.md").read_bytes()).hexdigest()
assert sha == man["instruction_sha256"]
by_type = {}
for v in V: by_type[v["verifier_type"]] = by_type.get(v["verifier_type"], 0) + 1
W = sum(v["weight"] for v in V)
def short(v):
    t = v["verifier_type"]
    if t == "file_check":
        a = v["verifier_spec"]["verifiers"][0]["assertion"]
        exp = a["expected"]
        if a["deterministic"]["comparison"] == "regex_match":
            return "full-row regex", v["description"].replace("full-row check: ", "")
        return f"{a['deterministic']['path']} {a['deterministic']['comparison']}", str(exp)
    if t == "database_state":
        return f"SQL {v['comparison_type']}", str(v["expected_value"])
    if t == "rubric_check":
        return f"LLM judge ({v['target']})", "PASS"
    return "trace", ", ".join(v.get("expected_tools", []))
rows = "\n".join(f"| {v['requirement_id']} | {v['verifier_type']} | `{v['name']}` | {short(v)[0]} | {short(v)[1].replace('|', '/')} | {v['weight']} |" for v in V)
ledger = "\n".join(f"| {r['meeting']} | {r['date']} | {r['attendee']} | {r['status']} | {r['source']} |" for r in plan["ledger"])
fixes = "\n".join(f"| {r['meeting']} | {r['date']} | {r['attendee']} | {r['tracker_status']} | {r['status']} |" for r in plan["tracker_fixes"])
owed = {}
for r in plan["ledger"]:
    if r["status"] == "OWES_ANSWER": owed.setdefault(r["attendee"], []).append(f"{r['meeting']} ({r['date']})")
drafts = "\n".join(f"| {a} | {'; '.join(owed[a])} | `{plan['write_back']['reply_on'][a]}` |" for a in plan["write_back"]["chase"])
readme = f"""# the-meetings-still-waiting-on-a-yes

An RSVP reconciliation on the Outlook gym. The agent acts as Jack Spencer. It reads every meeting he organised that starts
between 27 April and 17 May 2026 (Pacific), and works out where each required attendee stands from two places: their
invitation response and his mail. It then:
- writes a ledger of every attendee;
- lists the entries in his assistant's RSVP tracker that are wrong;
- drafts (does not send) one note to each person who still owes him an answer, each on that person's latest email;
- states its conclusion.

The rules are all stated in the prompt. The difficulty is in reading the data:
- answers that only resolve across two messages, judged in Pacific time while the tools show UTC;
- a reply whose own words reverse the yes quoted beneath it;
- a meeting referred to only by its day and time;
- window edges that differ between Pacific and UTC;
- a mailbox larger than one default page;
- nine meetings and 31 rows to keep straight.

## Connector

- **Gym:** outlook-gym on container port 8014 (streamable-http, `localhost:7000/mcp/outlook-gym`).
- **Image:** pinned by digest, `us-central1-docker.pkg.dev/delivery-g-obi/connectors-rl-gym/connectors-harness@sha256:b1374cd8a392ea66f9a649e700a1498e8fcb03ee35776362db7cc15dc3049b89`.
- **`reset_on_run = true`:** every run starts from the gym's synthetic snapshot.
- **Build-time seed (Handbook 8.1):** `environment/seed/seed_outlook_task.py` patches that snapshot and is deleted after the build. It:
  - adds 23 inbox messages;
  - marks two meetings as moved;
  - sets UTC answer times on five meetings;
  - inserts six meetings he organised (one cancelled, one just outside the window, one just inside it).

  It fails the build on drift or collision.
- **Acting identity:** Jack Spencer (user 46, `jack.spencer@contoso.example`), authenticated through `x-outlook-user-token`; tenancy header `x-database-id`.
- **Tools behind the proxy:** `search_calendar`, `search_email`, `draft_email`, `send_email`, `update_calendar`. The task needs the first three.
- **Isolation:**
  - raw state and step routes are only on a root-only unix socket;
  - the gym port answers 404 to everything but `/health`;
  - `/opt/proxy`, `/app` and `/gyms` are unreadable to the agent user `rlgymagent`.

## Deliverables

1. **`/workspace/rsvp_ledger.csv`:** header `meeting,date,attendee,status,source`, one row per meeting he runs and required attendee other than him ({len(plan['ledger'])} rows).
2. **`/workspace/tracker_fixes.csv`:** header `meeting,date,attendee,tracker_status,status`, one row per entry in Janice Gray's tracker that is on the ledger and disagrees with it ({len(plan['tracker_fixes'])} rows).
3. **Drafts, nothing sent:** {len(plan['write_back']['chase'])} drafts, one per person who owes at least one answer, each naming every meeting they owe and each a reply on that person's most recent email.
4. **Final reply** stating the conclusion and evidence.

### Ledger (gold, {len(plan['ledger'])} rows)

| meeting | date | attendee | status | source |
|---|---|---|---|---|
{ledger}

### Tracker fixes (gold, {len(plan['tracker_fixes'])} of Janice's 22 entries)

| meeting | date | attendee | tracker_status | status |
|---|---|---|---|---|
{fixes}

Janice's other entries:
- 7 agree with the ledger;
- 3 are not on it: Jack Henry is optional on the brainstorm, Customer Advisory Board prep is cancelled, and Planning Offsite Prep starts 26 April Pacific.

### Drafts (gold)

| to | owes | reply on (their latest email) |
|---|---|---|
{drafts}

## Hidden rules (all stated in the prompt; the agent must connect them to the data)

1. **Pacific, not UTC.** Response and email times come back in UTC. Days and times people write are Pacific (PDT, UTC-7).
2. **Window edges.**
   - Customer Escalation Sync (Sunday 17 May 17:30 Pacific, 18 May 00:30 UTC) is in.
   - Planning Offsite Prep (Sunday 26 April 21:00 Pacific, 27 April 04:00 UTC) is out.
   - A UTC-bounded search loses the first.
3. **The last answer on either channel wins.**
   - Jasmine Porter emailed yes for 2 May, then declined the invitation.
   - Jared Ellis declined 2 May, then emailed yes.
   - Charlotte Palmer declined the roadmap review, then emailed yes.
   - Cameron Simpson declined the debrief, then emailed yes.
4. **A conditional yes counts once its condition has happened.**
   - Diego Alvarez: "as long as the forecast numbers are in by Tuesday night". Kenneth Hall's note came at 05:40 UTC on 6 May, which is Tuesday 22:40 Pacific.
   - Cameron: "as long as the board deck is signed off by Friday". Nora Ford's note came at 02:35 UTC on 9 May, which is Friday 19:35 Pacific.
   - Read in UTC, both notes land a day late.
5. **Quoted text is older.** Jack Henry's "Scratch that … I won't make the vendor review" sits above his quoted earlier yes.
6. **Indirect reference.** Jasmine's "I'll be at the 2pm one on Thursday" is the Vendor Security Review, Thursday 7 May 14:00.
7. **Moves.** Answers given before OKR Planning (28 April 11:00 Pacific) or the 6 May pipeline review (1 May 16:00 Pacific) were moved no longer count.
8. **Someone in your place is a no; a relayed answer is not an answer.**
   - Jenna White's "Kenneth will cover the forecast for me" means she is not coming.
   - Jasmine's note for Jack Henry, Carson's note for Charlotte, and Janice's tracker are not anyone's answer.
9. **People are addresses.** Six external attendees carry the display name "Jack Spencer", and one address is listed twice.
10. **Latest email of any subject.**
    - Olivia Myers's is a 1 April risk-log note, outside the default 25-message page.
    - Nora's is the board-deck note.

## Verifiers ({len(V)})

| Req | Type | Check | How | Expected | Weight |
|---|---|---|---|---|---|
{rows}

Total weight **{W:g}**. {by_type.get('file_check',0)} file_check, {by_type.get('database_state',0)} database_state, {by_type.get('rubric_check',0)} rubric_check (LLM judge, 3-vote majority, temperature 0.0), {by_type.get('tool_execution',0)} tool_execution.

The per-row CSV checks are case-insensitive, quote-tolerant, line-anchored regexes over the whole row. The two row-count checks stop an agent that writes every possible status for every row.

## Write-back controls

| Run | own drafts naming the meetings | reply threads | recipients | drafts | sent | reward |
|---|---|---|---|---|---|---|
| gold | 7/7 | 7/7 | 7 | 7 | 2 | 1.0 |
| send instead of draft | 0/7 | 0/7 | 0 | 0 | 9 | < 1 |
| new messages instead of replies | 7/7 | 0/7 | 7 | 7 | 2 | < 1 |
| draft to Jasmine as well (her vendor-review "2pm one on Thursday" missed) | 7/7 | 7/7 | 8 | 8 | 2 | < 1 |
| write nothing | 0/7 | 0/7 | 0 | 0 | 2 | 0.0293 |

Rows other than gold and write-nothing follow from the SQL in tests/manifest.json; the write-nothing row is the observed GLM failure score.

## Oracle

The oracle scores **1.0**, with all {len(V)} verifiers passing.

The golden trajectory has {len(json.loads((T / 'solution/golden_trajectory.json').read_text()))} steps:
- 1 `search_calendar`, Pacific range;
- 1 `search_email` over the whole mailbox;
- 7 `draft_email`, each on the person's latest email.

`solution/verify_gold_from_oracle.py` re-derives every ledger row, tracker fix, recipient and reply thread from the replay's own gym payloads, and printed `OK: 9 meetings, 31 ledger rows, 12 tracker fixes …`.

## Evidence status

- **Oracle (`evaluations/oracle`):** 1.0, 201 verifier results passing and 0 failing (67 checks × 3 listings), run locally against the pinned image.
- **Stability (`evaluations/stability/repeat-01..03`):** three more oracle runs on the same task checksum; see their `verifier/reward.txt`.
- **GLM-5.2 battery (`evaluations/glm-5.2/r1..r4`):** **2/4 strict passes** (1.0, 1.0, 0.0293, 0.0293), task checksum `b35c3f8d…`.
  - **The two passes** are exact: every row, fix and draft is right, so every trap above was solved.
  - **The two failures are output-length cut-offs, not wrong answers.**
    - After reading the calendar and the mail, each run tried to work out all 31 rows, 22 tracker entries and 7 drafts in one turn.
    - That turn hit the model's 32k-token reasoning limit: the opencode log shows `step_finish reason: "length"`, about 32,000 reasoning tokens and an empty message.
    - Nothing was written, so only `nothing_was_sent` and the trace-read rubric passed (0.0293).
    - Their reasoning up to the cut-off was correct.
  - **What this means:** the task's difficulty is its volume, and a run passes when it works in steps rather than in one turn.
- **consistency/:**
  - `requirements.json`: every wrong value computed from the real oracle payloads.
  - `mutations.json`: control battery through the bundle's own engine, plus rubric validation against the judge.
  - `readers.json` and `envelope.json`: GLM-5.2 through the judge endpoint.
  - `shortcut_audit.md`: live probe.
- **instruction_sha256:** `{sha}` (matches the manifest).
"""
(T / "README.md").write_text(readme)
print(len(readme))
