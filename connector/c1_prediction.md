# Prediction before the first GLM runs: `the-meetings-still-waiting-on-a-yes`

Written 2026-09-29, before any GLM run on this task (Handbook §2.3).

**Task version:** mined, plus fix 1. Fix 1 changes only the tool_execution check (the tools are now named), the healthcheck, and the `/opt/proxy` permissions. The instruction and the gold are unchanged.

**What the model sees:** one ranged `search_calendar` call returns all 11 events. Each event carries `isOrganizer`, attendee `type` (required/optional) and `status.response`. The whole mailbox is 9 messages.

**The instruction spells out:**
- the answer rule (no response or tentative = still owes; declined = answered);
- that optional attendees don't count;
- the draft-on-their-latest-email rule.

## Expected wrong readings (decoys already in `task.toml`)

| # | Wrong reading | Metric / check it breaks |
|---|---|---|
| W1 | Counts every event in the window, ignoring `isOrganizer` | `meetings_i_am_running` = 11; everything downstream |
| W2 | Counts the masked duplicate attendees (e.g. "Jack Spencer" at eugene.dunn@…) as other people | Nothing: all of them accepted. **Not a discriminator.** |
| W3 | Includes Jack Miller's *optional* no-response on OKR Planning | `answers_still_owed` 5 instead of 4; Diego/Jack Miller drafts still fine |
| W4 | Counts Jared Ellis's decline as owing | people 4, answers 5, a 4th draft, which fails `drafts_go_to_exactly_those_three` |
| W5 | Counts his own unanswered invitations (Performance Review, Discovery Call) | `meetings_still_owed_an_answer` |
| W6 | Treats "emailed me" as "any invited person who emailed" (Jack Henry) | `people_to_chase_who_already_emailed_me` = 2 |
| W7 | Drafts to Charlotte as a new message instead of a reply to her latest email | `charlotte_drafted_on_her_own_thread` |
| W8 | One combined draft to all three, or two drafts to Diego | the sole-recipient checks / `exactly_one_draft_per_person` |
| W9 | Sends instead of drafting (`send_email` is exposed) | `nothing_was_sent` |

## Prediction

- **Result:** the rules are all written in the prompt as field-level tests. `type` == required and `response` in {notResponded, tentativelyAccepted} are exactly the "mechanical threshold" of Handbook §2.1. So I expect **3/4 or 4/4 strict passes**.
- **Most likely failures:** W7 (the reply-on-thread mechanics of `draft_email`) and W1/W5 (`isOrganizer`).
- **What the evidence would tell us:** if the battery is 3–4/4, the task needs an interpretive discriminator (Handbook §2.2), not more rules. If failures appear on W7 only, the difficulty is tool mechanics rather than reasoning, and I'll check that it's a fair failure: the `draft_email` schema documents `reply_to_email_id`.

---

# Round 2: prediction before the battery on the hardened version (2026-09-30)

**Battery on fix 2 (`glm-c1-smoke`):** 4/4 strict passes, task_checksum `14fc64ff…`. It matched the round-1 prediction.

In all four runs the model:
- made one ranged calendar read;
- made per-person `from:` searches, used only to check whether each person had ever emailed (no email body was read);
- wrote 5/3/3/4/1 and three drafts, with Charlotte's as a reply on her thread.

The task was solvable with field-level checks alone.

**Change (hardening 1):**
- one instruction sentence: email answers count, whatever the invitation shows; a maybe is not an answer;
- five seeded inbox messages;
- new gold 5/1/2/2/2, with both drafts as replies on each person's latest email.

**Discriminators:**
- the email refers to meetings by weekday and kind ("Thursday's planning session", "Friday's learning session", "the feature brainstorm on Friday");
- firm answer versus maybe ("count me in" / "won't be able to make" versus "still not sure" / "I'll try … can't promise");
- one email carrying two answers of different strength (Diego's);
- the latest of two emails (Jack Miller's).

**Prediction: 1/4 or 2/4.** The expected failures:
- W10: the model keeps the old "has this person ever emailed" reading and never applies the email answers (3/3/4/3). This is the most likely, because the round-1 runs never read email bodies.
- W11: the model treats Jack Miller's "I'll try" as an answer (1 person / 1 answer).
- W12: the model applies Diego's "count me in" to both of his meetings (answers 1).
- W13: the model puts Jack Miller's draft on the "Discovery call prep" thread.

**How to read the result:**
- **0/4:** check that every failure is one of W10–W13 and not a tool or data problem (the probe confirms the emails are served).
- **3–4/4:** the discriminator is still mechanical, and the next lever is precision (exact lists).

---

# Round 3: prediction before the battery on hardening 2 (2026-09-30)

**Battery on hardening 1 (`glm-c1-h1`):** 4/4 strict passes, task_checksum `a6fff530…`. The oracle scored 1.0 on the same checksum.

In every run GLM:
- read the email bodies;
- mapped "Thursday's planning session" to OKR Planning;
- treated "I'll try" as a maybe;
- split Diego's email into a yes and a maybe;
- put Jack Miller's draft on his latest email.

The wording-level discriminators were too easy. My prediction of 1–2/4 was wrong.

**Change (hardening 2): a new data relation (Handbook §2.4), not another rule of the same kind.**
- **The move:** OKR Planning was moved on 28 April. Answers dated before that no longer count, on the invitation (Jack Henry, accepted 27 April) or by email (Diego's "count me in for Wednesday's planning session", 27 April).
- **Latest email wins:** Charlotte's no (29 April) is followed by a maybe (1 May), so she still owes. Jack Miller's maybe (29 April) is followed by a yes (30 April), so he has answered.
- **Draft placement:** each draft goes on the person's most recent email of *any* subject. For Charlotte that is the 21 May Privacy Impact Assessments reply, not her Learning Time emails.
- **New gold:** 5/3/3/4/3, with drafts to Diego (OKR + Brainstorm), Jack Henry (OKR) and Charlotte (Learning Time).

**Why this should bite where round 2 didn't:** it needs temporal reasoning, not reading. The model has to:
- notice the move note in the event description;
- compare each attendee's response `time` (a field every earlier run ignored) with the move time;
- compare email dates with the move time;
- order a person's emails by date, per meeting and overall.

**Prediction: 1/4 or 2/4, with 0/4 a real risk.** The expected failures:
- W14: ignores the move or the response times (2/2/2/2 figures, no Jack Henry). **This is the most likely**, since response `time` has never been read.
- W15: applies the move to invitations but not to Diego's email (answers 3, Diego's draft without OKR).
- W16: takes Charlotte's firm no instead of her later maybe (2 meetings, Jack Miller instead of Charlotte).
- W17: puts Charlotte's draft on her Learning Time thread instead of her latest email.

**How to read the result:**
- **0/4:** check each failure is W14–W17, then soften one lever. The first to soften: say in the instruction that moves are noted in the meeting's description.
- **3–4/4:** discard the task, as agreed.

---

# Round 4: prediction before the battery on hardening 3 (2026-09-30)

**Battery on hardening 2 (`glm-c1-h2`):** 4/4 strict passes, task_checksum `52921f29…`. The oracle scored 1.0 on the same checksum.

Every run solved it in 9–15 tool calls and 2.4k–5.1k completion tokens:
- it read the move note and the response times;
- it ordered the emails by date;
- it put Charlotte's draft on her 21 May email.

Every date comparison was a whole day apart (27 April versus 28 April), so no clock time or time zone ever mattered. My prediction of 1–2/4 was wrong again: GLM is strong at small-context rule application.

**Change (hardening 3): the same rules, but every comparison that decides an answer is same-day and needs a time zone conversion.** The tools show timestamps in UTC (`…Z`). The instruction says every day and time people write is Pacific, "whatever time zone a timestamp is shown in".

**The OKR Planning move:** 28 April at 11:00 Pacific. Two answers are just before it:
- Jack Henry's acceptance at 17:40Z (10:40 Pacific);
- Diego's emailed "count me in for tomorrow's planning session" at 17:52Z (10:52 Pacific). "Tomorrow" is Wednesday, the old slot.

The acceptances at 19:20Z and 19:35Z are after it.

**A second move:** the 6 May Weekly Pipeline Review moved on 1 May at 16:00 Pacific.
- Diego accepted at 22:30Z (15:30 Pacific), before the move, so he owes it again.
- The others accepted after the move (00:40Z to 01:30Z on 2 May).

**Charlotte's latest email:** sent 2026-05-01T04:30Z, which is Thursday 30 April 21:30 Pacific: "maybe I can make tomorrow's learning session after all". Tomorrow is Friday, Learning Time, and it is a maybe, so she still owes. Read by the UTC date, "tomorrow" would be Saturday.

**Fairness:** every before/after gives the same answer under UTC−7 (correct, daylight time) and UTC−8. Only reading the UTC clock time as Pacific flips it. I verified this against the seed.

**New gold:** 5/4/3/5/3.

**The wrong readings and what they produce:**

| # | Wrong reading | Figures | Draft effect |
|---|---|---|---|
| W18 | UTC clock times read as Pacific | 5/1/1/1/1 | Diego only, for the brainstorm |
| W19 | 6 May move missed | 5/3/3/4/3 | Diego's draft lacks the pipeline review |
| W20 | Charlotte's "tomorrow" by the UTC date | 5/3/2/4/2 | no Charlotte draft |
| W21 | both moves ignored | 5/2/2/2/2 | — |

All the earlier traps still apply: latest email of any subject, and "I'll try" is a maybe.

**Prediction: 1/4 or 2/4.** Each run has to make three independent time zone judgments correctly, plus spot the second move note. If GLM converts correctly about 60–70% of the time on each, a strict pass comes out around 25–40%.

**How to read the result:**
- **0/4:** check that every failure is one of W18–W21, not a tool or data problem, then soften one trap. The first to soften: Charlotte's email names "Friday" instead of "tomorrow".
- **3–4/4:** stop and discard. Three hardening rounds is the honest limit for this data.

---

# Round 5: result of hardening 3, and prediction for hardening 4 (2026-09-30)

**Battery on hardening 3 (`glm-c1-h3`):** 3/4 strict passes (1.0, 1.0, 1.0, 0.8182), task_checksum `308e0836…`. The oracle scored 1.0 on the same checksum. No crashes.

- **Time zones:** all four runs converted every UTC time correctly and found both moves. **The time zone lever did not bite.** My prediction was wrong a third time.
- **The one failure (`Q8A9PMP`) is a genuine model failure.**
  - Its searches returned every email, including Jack Henry's Frontend note and Charlotte's 21 May Privacy reply.
  - It then decided that "emailed me at some point" and "most recent email to me" meant emails *about the meetings*.
  - So it wrote `people_to_chase_who_already_emailed_me` = 2, made a new message to Jack Henry, and put Charlotte's draft on her Learning Time thread.
  - The instruction states both rules plainly. The model confused two similar-sounding rules ("latest email *about a meeting*" versus "most recent email *to me*").

**Change (hardening 4):** more traps of the one kind that actually failed, telling apart rules that look alike. The gold and checks are unchanged except Diego's thread.
- **Relayed answers don't count** (new sentence): "Only a person's own answer counts; something a colleague tells me on their behalf is not their answer."
  - Jasmine Porter (29 April, after the OKR move): "Jack Henry … says the new OKR Planning time works for him."
  - Carson Flores (Friday 1 May, 10:20 Pacific, after Charlotte's maybe): "Charlotte asked me to let you know she'll definitely be at the learning session today."

  Each is the latest word on that meeting but not the person's own, so Jack Henry and Charlotte still owe.
- **Diego's latest email** is now an unrelated 12 May "Q3 roadmap draft", so his draft goes there, not on "This week".

**Gold:** still 5/4/3/5/3. Diego's thread check now points at the roadmap conversation.

**Prediction: 1/4 or 2/4.** Three kinds of look-alike traps now have to be passed independently:
- the scope of "latest email" (Charlotte, Diego and Jack Henry placements, plus the "emailed me" count);
- relayed versus own answers (Jasmine, Carson);
- the time zone judgments.

The scope trap alone failed 1 of 4 runs.

**How to read the result:**
- **0/4:** check that every failure is W18–W23 and fair, then soften one trap (drop Diego's roadmap email first).
- **3–4/4:** stop hardening. Report the 3/4 (or 4/4) honestly and decide with the lead: the client accepts 3/4, and discarding is the alternative.

---

# Round 6: result of hardening 4, the accepted reference, and prediction for hardening 5 (2026-10-01)

**Battery on hardening 4 (`glm-c1-h4`):** 4/4 strict passes, 12–14 calls and about 3k completion tokens each. The oracle scored 1.0. No crashes.
- Every run did one ranged calendar read and one to four mail searches. Then it applied the five stated rules correctly, including both relayed notes.
- **Lesson:** with five numbers to report and every fact in two tool responses, GLM gets every rule right. More rules of the same kind will not change that.

**What the accepted reference (`the-pin-that-never-got-closed-out`) shows:**
- The gold is an exact per-item list: 11 rows, 4 labels, each row checked on its own.
- QC made the trainer disclose every hidden rule in the prompt (rounds 5–9), so the rules have to be stated.
- Its GLM battery came out 1/4.
- The hardness comes from many independently checked rows, not from secret rules.

**Change (hardening 5):** applies all five of the user's levers.
- **Exact lists instead of counts.** `metrics.json` is gone.
  - `rsvp_ledger.csv` has one row for every required attendee of every meeting he runs: 15 rows, each with a status (COMING / NOT_COMING / OWES_ANSWER) and a source (INVITATION / EMAIL / NONE). Every row is checked on its own with a whole-row regex.
  - Every attendee now matters, not just the ones who owe, so the agent has to read everyone's mail.
- **A second source to reconcile.** Janice Gray's RSVP tracker email has 13 entries. `tracker_fixes.csv` must list exactly the 8 that are wrong, with her status and the correct one. It leaves out 3 entries that agree with the ledger and 2 that are not on it: an optional attendee and a cancelled meeting.
- **Interpretive rules instead of thresholds** (all stated):
  - the last answer on either channel wins;
  - a yes that depends on something still unsettled is not an answer;
  - someone else going in your place means you are not coming;
  - a person is their email address, not their display name.
- **Decoys with the exclusion rule stated:**
  - **Cancelled meeting:** a new meeting, Customer Advisory Board prep, organised by him with three people unanswered or tentative.
  - **Display names:** five external attendees are shown as "Jack Spencer".
  - **Duplicate address:** eugene.dunn is listed twice on OKR Planning.
  - **Optional attendees** appear in Janice's tracker.
- **No hints:** dropped the "How you work is checked" paragraph and the worked examples ("tomorrow", "11:00").
- **New seeded traps:**

  | Who | Meeting | What was seeded | Correct row | Most likely wrong answer |
  |---|---|---|---|---|
  | Jasmine Porter | 2 May review | emailed yes on 30 Apr, then declined the invitation on 1 May | NOT_COMING, INVITATION | the h4 habit "email overrides the invitation" |
  | Jared Ellis | 2 May review | declined on 29 Apr, then emailed yes on 30 Apr | COMING, EMAIL | (reads both channels in time order) |
  | Diego | 6 May review | 4 May email: "works for me as long as the forecast numbers are in" | OWES_ANSWER | treating the conditional yes as an answer |
  | Jenna White | 6 May review | 5 May email: "Kenneth will cover the forecast for me" | NOT_COMING, EMAIL | reading her own note as a relayed one |

  Jenna's case also adds a fourth draft if the agent gets it wrong.
- **Gold:**
  - the 15 ledger rows and 8 fixes are in `task.toml`;
  - the same 3 drafts as before (Diego, Jack Henry, Charlotte, each on their latest email);
  - 39 checks, weight 28.75.

**Prediction: 1/4 (range 0–2).**

| Point to get right | Chance per run |
|---|---|
| 15-row enumeration | about 0.85 |
| Jasmine | about 0.75 |
| Jenna | about 0.8 |
| Diego conditional | about 0.85 |
| source column | about 0.85 |
| tracker fixes | about 0.8 |
| the older traps | about 0.9 |

The product is about 0.2 per run.

**How to read the result:**
- **0/4:** check that every failure is one of the traps above and fair, then ease one lever. In order:
  1. drop the source column;
  2. or let `tracker_fixes` include agreeing entries;
  3. or remove the cancelled meeting.
- **3–4/4:** the per-row structure did not bite; next lever is more meetings/rows.

---

# Round 7: result of hardening 5, and the rethink behind hardening 6 (2026-10-01)

**Battery on hardening 5 (`glm-c1-h5`):** 4/4 strict passes, 11–14 calls and 3–4k completion tokens each. The oracle scored 1.0 (117/0) and the gym data was served exactly as seeded.

**Why the hardening rounds kept failing:**
- Every lever so far was a **rule stated in the prompt**, applied to data that fits in **two tool responses**. GLM reads both, then applies the rules like a checklist, one row at a time.
- Per-row accuracy was essentially 100%, so more rules of the same kind, or 15 rows instead of 5 numbers, change nothing.

**The rethink (hardening 6):** keep the rules (QC requires them stated) but make the **data** hard to read correctly. Each trap needs more than looking up one row:
1. **Answers that resolve across two messages, judged in Pacific time.**
   - Diego's yes depends on "the forecast numbers … in by Tuesday night". Kenneth's note arrives at 05:40Z on 6 May, which is Tuesday 22:40 Pacific.
   - Cameron's yes depends on "the board deck … signed off by Friday". Nora's note arrives at 02:35Z on 9 May, which is Friday 19:35 Pacific.

   Read in UTC, both notes land on the next day.
2. **Quoted text.** Jack Henry's reply ("Scratch that … I won't make the vendor review") sits above his own quoted yes.
3. **An indirect reference.** "I'll be at the 2pm one on Thursday" has to be matched to the Vendor Security Review by day and time.
4. **Window edges that differ between Pacific and UTC.**
   - Customer Escalation Sync is Sunday 17 May 17:30 Pacific (18 May in UTC): in.
   - Planning Offsite Prep is Sunday 26 April 21:00 Pacific (27 April in UTC): out.

   A UTC-bounded search misses the first, and reading UTC dates keeps the second.
5. **A mailbox bigger than one page.** It holds 32 messages, but `search_email` returns 25 by default. Olivia's only email (1 April) is on the second page.
6. **Scale and the write-back:**
   - 9 meetings, 31 ledger rows and 12 tracker fixes (Janice's tracker grows to 22 entries).
   - 7 drafts, each on a different person's latest email: two are notes about other things, one from 1 April and one from the board-deck thread.
   - 67 checks.

**Prediction: 0–1/4.** Each of the cross-message and time zone traps is roughly a coin-flip-plus for a model that reads UTC dates literally. The window edge and pagination traps hit any run that takes shortcuts.

**How to read the result:**
- **0/4:** confirm every failure is one of the traps above, then ease them in this order:
  1. move Nora's note to Friday afternoon, so it is Friday in UTC too;
  2. give Kenneth's note a Tuesday UTC time;
  3. drop the source column.
- **2+/4:** the remaining lever is volume. Add a second week of meetings, so the calendar response no longer fits in one view.

---

# Round 8: result of hardening 6 (2026-10-01)

**Battery on hardening 6 (`glm-c1-h6`):** **2/4 strict passes** (1.0, 1.0, 0.0293, 0.0293). Task checksum `b35c3f8d…`. The oracle scored 1.0 (201 passed / 0 failed) and the gold verify script re-derived 9 meetings, 31 rows and 12 fixes. The probe showed every seeded item exactly as designed. No exceptions.

**The two passes (`BaFoQu9`, `EqJ6FyU`) are clean:**
- every ledger row, fix row and draft was right, so every trap (cross-message conditions in Pacific time, quoted reply, "2pm one on Thursday", window edges, 7 latest-email threads) was solved;
- 8 steps each, about 520–560k prompt tokens and 4.6–4.9k completion tokens.

**The two failures (`b9EiDKv`, `xEfZG6g`) are not wrong answers. Both are output-length cut-offs:**
- After reading the calendar and the mail, each run tried to work out all 31 rows, 22 tracker entries and 7 drafts in one turn.
- That turn hit the 32k-token reasoning limit. opencode logs `step_finish reason: "length"` with about 32,000 reasoning tokens and an empty message.
- No file was written and no draft was made, so only the "nothing sent" and trace-read checks passed (0.0293).
- Their reasoning up to the cut-off was correct; one had already listed all 12 tracker fixes.

**What this means:**
- The h6 data no longer fits in GLM's one-turn reasoning budget. Even a passing run used 31,638 reasoning tokens in its biggest turn, 362 under the limit.
- So the difficulty now comes from **volume**: an agent has to work in steps (write the ledger, then the fixes, then the drafts) rather than reason through everything at once.
- That is a real agent skill, but the failure shows up as `length`, not as a wrong row. **This has to be disclosed in review.csv and the README.** A QC reviewer may class `length` failures as a model or config limit rather than task difficulty.

**Calibration status:** 2/4 is inside the client band (1–3) and the team preference (1–2).
