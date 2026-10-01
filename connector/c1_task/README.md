# the-meetings-still-waiting-on-a-yes

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

1. **`/workspace/rsvp_ledger.csv`:** header `meeting,date,attendee,status,source`, one row per meeting he runs and required attendee other than him (31 rows).
2. **`/workspace/tracker_fixes.csv`:** header `meeting,date,attendee,tracker_status,status`, one row per entry in Janice Gray's tracker that is on the ledger and disagrees with it (12 rows).
3. **Drafts, nothing sent:** 7 drafts, one per person who owes at least one answer, each naming every meeting they owe and each a reply on that person's most recent email.
4. **Final reply** stating the conclusion and evidence.

### Ledger (gold, 31 rows)

| meeting | date | attendee | status | source |
|---|---|---|---|---|
| OKR Planning | 2026-04-30 | diego.alvarez@contoso.example | OWES_ANSWER | NONE |
| OKR Planning | 2026-04-30 | jack.henry@contoso.example | OWES_ANSWER | NONE |
| OKR Planning | 2026-04-30 | eugene.dunn@pinwheellabs.com | COMING | INVITATION |
| Learning Time | 2026-05-01 | charlotte.palmer@contoso.example | OWES_ANSWER | NONE |
| Learning Time | 2026-05-01 | edward.clark@forgeco.com | COMING | INVITATION |
| Brainstorm: New Feature | 2026-05-01 | diego.alvarez@contoso.example | OWES_ANSWER | NONE |
| Brainstorm: New Feature | 2026-05-01 | jack.miller@contoso.example | COMING | EMAIL |
| Brainstorm: New Feature | 2026-05-01 | rogers.catherine@protonmail.com | COMING | INVITATION |
| Weekly Pipeline Review | 2026-05-02 | jasmine.porter@contoso.example | NOT_COMING | INVITATION |
| Weekly Pipeline Review | 2026-05-02 | jared.ellis@contoso.example | COMING | EMAIL |
| Weekly Pipeline Review | 2026-05-02 | ava.lopez@lumendata.com | COMING | INVITATION |
| Weekly Pipeline Review | 2026-05-06 | diego.alvarez@contoso.example | COMING | EMAIL |
| Weekly Pipeline Review | 2026-05-06 | jenna.white@contoso.example | NOT_COMING | EMAIL |
| Weekly Pipeline Review | 2026-05-06 | jared.ellis@contoso.example | COMING | INVITATION |
| Weekly Pipeline Review | 2026-05-06 | kenneth.hall@pemberleybank.com | COMING | INVITATION |
| Vendor Security Review | 2026-05-07 | jack.henry@contoso.example | NOT_COMING | EMAIL |
| Vendor Security Review | 2026-05-07 | jasmine.porter@contoso.example | COMING | EMAIL |
| Vendor Security Review | 2026-05-07 | jared.ellis@contoso.example | OWES_ANSWER | NONE |
| Vendor Security Review | 2026-05-07 | olivia.myers@contoso.example | COMING | INVITATION |
| Q3 Roadmap Review | 2026-05-11 | diego.alvarez@contoso.example | COMING | INVITATION |
| Q3 Roadmap Review | 2026-05-11 | charlotte.palmer@contoso.example | COMING | EMAIL |
| Q3 Roadmap Review | 2026-05-11 | jenna.white@contoso.example | OWES_ANSWER | NONE |
| Q3 Roadmap Review | 2026-05-11 | nora.ford@contoso.example | COMING | INVITATION |
| Q3 Roadmap Review | 2026-05-11 | cameron.simpson@contoso.example | COMING | EMAIL |
| Hiring Panel Debrief | 2026-05-15 | jasmine.porter@contoso.example | COMING | INVITATION |
| Hiring Panel Debrief | 2026-05-15 | cameron.simpson@contoso.example | COMING | EMAIL |
| Hiring Panel Debrief | 2026-05-15 | olivia.myers@contoso.example | OWES_ANSWER | NONE |
| Hiring Panel Debrief | 2026-05-15 | jack.miller@contoso.example | COMING | INVITATION |
| Customer Escalation Sync | 2026-05-17 | jenna.white@contoso.example | OWES_ANSWER | NONE |
| Customer Escalation Sync | 2026-05-17 | grace.kelley@pemberleybank.com | COMING | INVITATION |
| Customer Escalation Sync | 2026-05-17 | nora.ford@contoso.example | OWES_ANSWER | NONE |

### Tracker fixes (gold, 12 of Janice's 22 entries)

| meeting | date | attendee | tracker_status | status |
|---|---|---|---|---|
| OKR Planning | 2026-04-30 | diego.alvarez@contoso.example | COMING | OWES_ANSWER |
| OKR Planning | 2026-04-30 | jack.henry@contoso.example | COMING | OWES_ANSWER |
| Learning Time | 2026-05-01 | charlotte.palmer@contoso.example | COMING | OWES_ANSWER |
| Brainstorm: New Feature | 2026-05-01 | jack.miller@contoso.example | OWES_ANSWER | COMING |
| Weekly Pipeline Review | 2026-05-02 | jasmine.porter@contoso.example | COMING | NOT_COMING |
| Weekly Pipeline Review | 2026-05-02 | jared.ellis@contoso.example | NOT_COMING | COMING |
| Weekly Pipeline Review | 2026-05-06 | jenna.white@contoso.example | COMING | NOT_COMING |
| Vendor Security Review | 2026-05-07 | jack.henry@contoso.example | COMING | NOT_COMING |
| Vendor Security Review | 2026-05-07 | jasmine.porter@contoso.example | OWES_ANSWER | COMING |
| Q3 Roadmap Review | 2026-05-11 | charlotte.palmer@contoso.example | NOT_COMING | COMING |
| Q3 Roadmap Review | 2026-05-11 | cameron.simpson@contoso.example | OWES_ANSWER | COMING |
| Hiring Panel Debrief | 2026-05-15 | cameron.simpson@contoso.example | NOT_COMING | COMING |

Janice's other entries:
- 7 agree with the ledger;
- 3 are not on it: Jack Henry is optional on the brainstorm, Customer Advisory Board prep is cancelled, and Planning Offsite Prep starts 26 April Pacific.

### Drafts (gold)

| to | owes | reply on (their latest email) |
|---|---|---|
| charlotte.palmer@contoso.example | Learning Time (2026-05-01) | `AAMkD61867BD0A78844C3815861A41BA` |
| diego.alvarez@contoso.example | OKR Planning (2026-04-30); Brainstorm: New Feature (2026-05-01) | `AAMkB7F3E1A92C6D58B0F4A7E3C9D261` |
| jack.henry@contoso.example | OKR Planning (2026-04-30) | `AAMkDDFB4210A30B7656D7D0057D2820` |
| jared.ellis@contoso.example | Vendor Security Review (2026-05-07) | `AAMk2A7F5D19C3E84B6A7F5D19C3B84E` |
| jenna.white@contoso.example | Q3 Roadmap Review (2026-05-11); Customer Escalation Sync (2026-05-17) | `AAMk4E9B6C23F8A15D7E4B9C6F23A851` |
| nora.ford@contoso.example | Customer Escalation Sync (2026-05-17) | `AAMk9E5B2D84A7F16C3E5B2D84A7C16F` |
| olivia.myers@contoso.example | Hiring Panel Debrief (2026-05-15) | `AAMkC1B1A49DD2E7AC344BA18643FFAD` |

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

## Verifiers (67)

| Req | Type | Check | How | Expected | Weight |
|---|---|---|---|---|---|
| ledger | file_check | `ledger_header` | $.header equals | ['meeting', 'date', 'attendee', 'status', 'source'] | 0.5 |
| ledger | file_check | `ledger_row_count` | $.row_count equals | 31 | 1.0 |
| ledger | file_check | `ledger_okr_diego_alvarez` | full-row regex | OKR Planning 2026-04-30, diego.alvarez@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| ledger | file_check | `ledger_okr_jack_henry` | full-row regex | OKR Planning 2026-04-30, jack.henry@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| ledger | file_check | `ledger_okr_eugene_dunn` | full-row regex | OKR Planning 2026-04-30, eugene.dunn@pinwheellabs.com is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_learning_time_charlotte_palmer` | full-row regex | Learning Time 2026-05-01, charlotte.palmer@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| ledger | file_check | `ledger_learning_time_edward_clark` | full-row regex | Learning Time 2026-05-01, edward.clark@forgeco.com is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_brainstorm_diego_alvarez` | full-row regex | Brainstorm: New Feature 2026-05-01, diego.alvarez@contoso.example is OWES_ANSWER (NONE) | 0.5 |
| ledger | file_check | `ledger_brainstorm_jack_miller` | full-row regex | Brainstorm: New Feature 2026-05-01, jack.miller@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_brainstorm_rogers_catherine` | full-row regex | Brainstorm: New Feature 2026-05-01, rogers.catherine@protonmail.com is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_pipeline_2_may_jasmine_porter` | full-row regex | Weekly Pipeline Review 2026-05-02, jasmine.porter@contoso.example is NOT_COMING (INVITATION) | 1.0 |
| ledger | file_check | `ledger_pipeline_2_may_jared_ellis` | full-row regex | Weekly Pipeline Review 2026-05-02, jared.ellis@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_pipeline_2_may_ava_lopez` | full-row regex | Weekly Pipeline Review 2026-05-02, ava.lopez@lumendata.com is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_pipeline_6_may_diego_alvarez` | full-row regex | Weekly Pipeline Review 2026-05-06, diego.alvarez@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_pipeline_6_may_jenna_white` | full-row regex | Weekly Pipeline Review 2026-05-06, jenna.white@contoso.example is NOT_COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_pipeline_6_may_jared_ellis` | full-row regex | Weekly Pipeline Review 2026-05-06, jared.ellis@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_pipeline_6_may_kenneth_hall` | full-row regex | Weekly Pipeline Review 2026-05-06, kenneth.hall@pemberleybank.com is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_vendor_security_jack_henry` | full-row regex | Vendor Security Review 2026-05-07, jack.henry@contoso.example is NOT_COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_vendor_security_jasmine_porter` | full-row regex | Vendor Security Review 2026-05-07, jasmine.porter@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_vendor_security_jared_ellis` | full-row regex | Vendor Security Review 2026-05-07, jared.ellis@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| ledger | file_check | `ledger_vendor_security_olivia_myers` | full-row regex | Vendor Security Review 2026-05-07, olivia.myers@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_q3_roadmap_diego_alvarez` | full-row regex | Q3 Roadmap Review 2026-05-11, diego.alvarez@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_q3_roadmap_charlotte_palmer` | full-row regex | Q3 Roadmap Review 2026-05-11, charlotte.palmer@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_q3_roadmap_jenna_white` | full-row regex | Q3 Roadmap Review 2026-05-11, jenna.white@contoso.example is OWES_ANSWER (NONE) | 0.5 |
| ledger | file_check | `ledger_q3_roadmap_nora_ford` | full-row regex | Q3 Roadmap Review 2026-05-11, nora.ford@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_q3_roadmap_cameron_simpson` | full-row regex | Q3 Roadmap Review 2026-05-11, cameron.simpson@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_hiring_debrief_jasmine_porter` | full-row regex | Hiring Panel Debrief 2026-05-15, jasmine.porter@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_hiring_debrief_cameron_simpson` | full-row regex | Hiring Panel Debrief 2026-05-15, cameron.simpson@contoso.example is COMING (EMAIL) | 1.0 |
| ledger | file_check | `ledger_hiring_debrief_olivia_myers` | full-row regex | Hiring Panel Debrief 2026-05-15, olivia.myers@contoso.example is OWES_ANSWER (NONE) | 0.5 |
| ledger | file_check | `ledger_hiring_debrief_jack_miller` | full-row regex | Hiring Panel Debrief 2026-05-15, jack.miller@contoso.example is COMING (INVITATION) | 0.5 |
| ledger | file_check | `ledger_escalation_sync_jenna_white` | full-row regex | Customer Escalation Sync 2026-05-17, jenna.white@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| ledger | file_check | `ledger_escalation_sync_grace_kelley` | full-row regex | Customer Escalation Sync 2026-05-17, grace.kelley@pemberleybank.com is COMING (INVITATION) | 1.0 |
| ledger | file_check | `ledger_escalation_sync_nora_ford` | full-row regex | Customer Escalation Sync 2026-05-17, nora.ford@contoso.example is OWES_ANSWER (NONE) | 1.0 |
| tracker_fixes | file_check | `tracker_fixes_header` | $.header equals | ['meeting', 'date', 'attendee', 'tracker_status', 'status'] | 0.5 |
| tracker_fixes | file_check | `tracker_fixes_row_count` | $.row_count equals | 12 | 1.0 |
| tracker_fixes | file_check | `fix_okr_diego_alvarez` | full-row regex | Janice has diego.alvarez@contoso.example as COMING on OKR Planning 2026-04-30; the ledger says OWES_ANSWER | 0.5 |
| tracker_fixes | file_check | `fix_okr_jack_henry` | full-row regex | Janice has jack.henry@contoso.example as COMING on OKR Planning 2026-04-30; the ledger says OWES_ANSWER | 0.5 |
| tracker_fixes | file_check | `fix_learning_time_charlotte_palmer` | full-row regex | Janice has charlotte.palmer@contoso.example as COMING on Learning Time 2026-05-01; the ledger says OWES_ANSWER | 0.5 |
| tracker_fixes | file_check | `fix_brainstorm_jack_miller` | full-row regex | Janice has jack.miller@contoso.example as OWES_ANSWER on Brainstorm: New Feature 2026-05-01; the ledger says COMING | 0.5 |
| tracker_fixes | file_check | `fix_pipeline_2_may_jasmine_porter` | full-row regex | Janice has jasmine.porter@contoso.example as COMING on Weekly Pipeline Review 2026-05-02; the ledger says NOT_COMING | 0.5 |
| tracker_fixes | file_check | `fix_pipeline_2_may_jared_ellis` | full-row regex | Janice has jared.ellis@contoso.example as NOT_COMING on Weekly Pipeline Review 2026-05-02; the ledger says COMING | 0.5 |
| tracker_fixes | file_check | `fix_pipeline_6_may_jenna_white` | full-row regex | Janice has jenna.white@contoso.example as COMING on Weekly Pipeline Review 2026-05-06; the ledger says NOT_COMING | 0.5 |
| tracker_fixes | file_check | `fix_vendor_security_jack_henry` | full-row regex | Janice has jack.henry@contoso.example as COMING on Vendor Security Review 2026-05-07; the ledger says NOT_COMING | 0.5 |
| tracker_fixes | file_check | `fix_vendor_security_jasmine_porter` | full-row regex | Janice has jasmine.porter@contoso.example as OWES_ANSWER on Vendor Security Review 2026-05-07; the ledger says COMING | 0.5 |
| tracker_fixes | file_check | `fix_q3_roadmap_charlotte_palmer` | full-row regex | Janice has charlotte.palmer@contoso.example as NOT_COMING on Q3 Roadmap Review 2026-05-11; the ledger says COMING | 0.5 |
| tracker_fixes | file_check | `fix_q3_roadmap_cameron_simpson` | full-row regex | Janice has cameron.simpson@contoso.example as OWES_ANSWER on Q3 Roadmap Review 2026-05-11; the ledger says COMING | 0.5 |
| tracker_fixes | file_check | `fix_hiring_debrief_cameron_simpson` | full-row regex | Janice has cameron.simpson@contoso.example as NOT_COMING on Hiring Panel Debrief 2026-05-15; the ledger says COMING | 0.5 |
| write_back_drafts | database_state | `own_draft_to_diego_alvarez_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `diego_alvarez_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_jack_henry_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `jack_henry_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_charlotte_palmer_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `charlotte_palmer_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_jared_ellis_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `jared_ellis_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_jenna_white_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `jenna_white_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_olivia_myers_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `olivia_myers_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_drafts | database_state | `own_draft_to_nora_ford_naming_their_meetings` | SQL greater_or_equal | 1 | 1.0 |
| write_back_reply_on_thread | database_state | `nora_ford_drafted_on_their_latest_email` | SQL greater_or_equal | 1 | 1.0 |
| write_back_nobody_else | database_state | `drafts_go_to_exactly_the_people_who_owe` | SQL equals | 7 | 1.0 |
| write_back_drafts | database_state | `exactly_one_draft_per_person` | SQL equals | 7 | 1.0 |
| write_back_nobody_else | database_state | `nothing_was_sent` | SQL equals | 2 | 1.0 |
| sources_read | rubric_check | `calendar_and_mailbox_were_read` | LLM judge (trace) | PASS | 0.5 |
| final_reply | rubric_check | `final_reply_states_who_owes_what` | LLM judge (final_answer) | PASS | 0.5 |
| sources_read | tool_execution | `the_calendar_and_mail_were_actually_read` | trace | search_calendar, search_email, draft_email | 0.25 |

Total weight **51.25**. 47 file_check, 17 database_state, 2 rubric_check (LLM judge, 3-vote majority, temperature 0.0), 1 tool_execution.

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

The oracle scores **1.0**, with all 67 verifiers passing.

The golden trajectory has 9 steps:
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
- **instruction_sha256:** `edbd96bc827cf108c0af694bf4037049b23f2b30b1dfc953af04022d6b3c4db9` (matches the manifest).
