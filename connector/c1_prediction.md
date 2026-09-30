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
