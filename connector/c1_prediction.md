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
