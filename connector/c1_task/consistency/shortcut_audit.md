# Shortcut audit - the-meetings-still-waiting-on-a-yes

Everything below comes from calls made against the task's own built image, as the non-root agent user, through the
same agent-facing MCP interface a real agent uses (`http://127.0.0.1:7000/mcp/outlook-gym`, streamable-http).
The calls were made by `connector/probes/probe_h5.py` (round 9 probe), and by the oracle replay whose payloads are kept in
`evaluations/oracle/verifier/golden_trajectory.json`. The tool catalogue behind the proxy is `search_calendar`,
`search_email`, `draft_email`, `send_email`, `update_calendar`.

## The natural path

9 gym calls:
- 1 `search_calendar` over 27 April - 17 May 2026, bounded in Pacific time, with `top` >= 16;
- 1 `search_email` over the whole mailbox, with `top` >= 32;
- 7 `draft_email` calls, one per person who owes an answer, each with `reply_to_email_id` set to that person's latest email.

This is `solution/golden_trajectory.json`. The oracle replayed it to reward 1.0 (67/67), and
`solution/verify_gold_from_oracle.py` re-derived every ledger row, tracker fix, recipient and reply thread from the
replay's own payloads. Agents commonly split the mail reads into per-sender `from:` searches; the two passing GLM runs
used 3-4 mail searches and the same 7 drafts.

## Why neither read can be skipped

- **The calendar is the only source of the population and of invitation answers.**
  - The probe returned 16 events in the Pacific window. 10 are organised by him, one of them cancelled.
  - The rows also carry each required attendee's response and UTC response time.
  - No mail message lists the attendees. Janice's tracker covers 19 of the 31 rows and is wrong on 12 of them.
- **The mailbox is the only source of email answers, of the two notes that settle conditional yeses, and of each person's latest email.**
  - 9 of the 31 rows are decided by an email.
  - The 7 drafts must each sit on a specific message.

## Shortcuts that look available and are not

- **Searching the calendar in UTC.** Customer Escalation Sync starts Sunday 17 May 17:30 Pacific, which is 18 May 00:30 UTC.
  - A search bounded at `2026-05-17T23:59:59Z` does not return it, so 3 ledger rows and Jenna's and Nora's drafts are lost.
  - Planning Offsite Prep (Sunday 26 April 21:00 Pacific, 27 April 04:00 UTC) comes back from a UTC-bounded search and must be excluded.
- **One default mailbox page.** `search_email` returns 25 messages unless `top` is set, and the mailbox holds 32.
  - The default page misses the 7 oldest messages, including Olivia Myers's only email (1 April).
  - Her draft has to sit on that email.
- **Reading the tracker instead of the sources.** 12 of Janice's 22 entries disagree with where people actually stand; 3 more are not on the ledger.
- **Trusting the invitation.** 9 rows are settled by an email (whatever the invitation shows), and Jasmine Porter's 2 May row by an invitation answer that came after her email.

## No shorter path exists

- The ledger needs both reads. Each draft's thread needs the mail read.
- `send_email` and `update_calendar` are reachable through the proxy, but nothing in the task needs them. Using `send_email` breaks the `nothing_was_sent` check.
- The minimum is 1 + 1 + 7 = 9 calls, so a run with fewer gym calls cannot have produced the 7 required drafts.
