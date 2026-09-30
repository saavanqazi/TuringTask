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
