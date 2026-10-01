#!/usr/bin/env python3
"""Build-time seed for the outlook gym (Handbook 8.1). Run once by the Dockerfile, then deleted.

Patches the gym's synthetic snapshot, Synthetic_db.db, which every /reset copies into the
per-run database, for Jack Spencer (user 46):
  * fourteen inbox messages: people answering meeting invitations by email (some more than once,
    one with a yes that depends on something unsettled, one sending someone in their place), two
    colleagues relaying someone else's answer, his assistant's RSVP tracker, and mail about other things;
  * his copies of OKR Planning and of the 6 May Weekly Pipeline Review: a note that each was moved
    (with the Pacific time of the move), created/modified times to match;
  * UTC response times on the attendees of all five meetings he runs in the window (so an answer on the
    invitation can be ordered against an email), Jasmine Porter's decline of the 2 May Weekly Pipeline
    Review, and created/modified times on the three unmoved meetings that predate every answer;
  * one more meeting he organised and then cancelled (Customer Advisory Board prep, 12 May).
Every before/after is the same whether Pacific time is taken as UTC-7 (correct, daylight time) or
UTC-8; it only flips if the UTC clock time is read as if it were Pacific.
The build fails (non-zero exit) if the snapshot has drifted from the rows this task was
designed against, if any new id or timestamp collides, or if the rows are not visible
afterwards. Re-running it on an already patched snapshot also fails.
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/gyms/outlook/app/data/Synthetic_db.db"
USER_ID = 46
ME = "jack.spencer@contoso.example"
INBOX = "AFB284B4386E878EFB2144F05C52DA"
TEMPLATE_ID = "AAMkD61867BD0A78844C3815861A41BA"  # Charlotte's existing message; also her latest (21 May)
JACK_HENRY_MSG = "AAMkDDFB4210A30B7656D7D0057D2820"
OKR = "AE3EC3B6C974C7331A84246F23D559"
WPR6 = "AE0B85738C75DE79357B3C2BCF0910"
WPR2 = "AE59394F0B3DD5862F926865364621"
LT = "AEEC8DE4AA60FE12696483F21D7BCC"
BS = "AEE3F39B45109EF1AA29F2F9C5D6F9"
CAB = "AE7C2F19B4D03E86A5C1F7B92D4E68"   # new: organised by him, then cancelled
VSR = "AE4B8D2F61C93A05E7B1D4F82C6A93"   # new: Vendor Security Review, Thu 7 May
Q3R = "AE9F3C7A15D82E64B0C9F3A71D5E28"   # new: Q3 Roadmap Review, Mon 11 May
HPD = "AE2D6A9E43F17C85B2D6A9E43C17F5"   # new: Hiring Panel Debrief, Fri 15 May
CES = "AE7E1B5C98A24D36F7E1B5C98D24A3"   # new: Customer Escalation Sync, Sun 17 May 17:30 Pacific = 18 May UTC
POP = "AE5A9D3B27E61F48C5A9D3B27F61E4"   # new: Planning Offsite Prep, Sun 26 Apr 21:00 Pacific = 27 April UTC (outside)

# event id -> (subject, body, created UTC, modified UTC = the move, {(name, address): response time UTC})
MOVES = {
    OKR: ("OKR Planning",
          "OKR Planning for Jack Spencer. Moved on 28 April at 11:00 Pacific: this was Wednesday 29 April 10:00; "
          "it is now Thursday 30 April 13:25.",
          "2026-04-24 17:00:00", "2026-04-28 18:00:00", {
              ("Jack Spencer", "jack.spencer@contoso.example"): "2026-04-24 17:00:00",   # organizer
              ("Diego Alvarez", "diego.alvarez@contoso.example"): "2026-04-27 16:50:00",  # tentative
              ("Jack Henry", "jack.henry@contoso.example"): "2026-04-28 17:40:00",        # accepted 10:40 PDT: before
              ("Jack Spencer", "eugene.dunn@pinwheellabs.com"): "2026-04-28 19:20:00",    # accepted 12:20 PDT: after
              ("Isla Hughes", "eugene.dunn@pinwheellabs.com"): "2026-04-28 19:35:00",     # accepted 12:35 PDT: after
          }),
    WPR6: ("Weekly Pipeline Review",
           "Weekly Tuesday 10:00 review of active opportunities, forecast call, and at-risk deals. Moved on 1 May at "
           "16:00 Pacific: this week's was Tuesday 5 May 10:00; it is now Wednesday 6 May 08:00.",
           "2026-04-24 17:30:00", "2026-05-01 23:00:00", {
               ("Jack Spencer", "jack.spencer@contoso.example"): "2026-04-24 17:30:00",    # organizer
               ("Diego Alvarez", "diego.alvarez@contoso.example"): "2026-05-01 22:30:00",  # accepted 15:30 PDT: before
               ("Jenna White", "jenna.white@contoso.example"): "2026-05-02 00:40:00",      # accepted 17:40 PDT: after
               ("Jared Ellis", "jared.ellis@contoso.example"): "2026-05-02 01:15:00",      # accepted 18:15 PDT: after
               ("Jack Spencer", "kenneth.hall@pemberleybank.com"): "2026-05-02 01:30:00",  # accepted 18:30 PDT: after
           }),
}

# the three meetings that were never moved: created/modified before every answer, and a UTC time on each
# answer; (name, address) -> (response or None to keep it, time)
UNMOVED = {
    LT: ("Learning Time", "2026-04-24 17:10:00", {
        ("Jack Spencer", "jack.spencer@contoso.example"): (None, "2026-04-24 17:10:00"),
        ("Jack Spencer", "edward.clark@forgeco.com"): (None, "2026-04-27 15:00:00"),
    }),
    BS: ("Brainstorm: New Feature", "2026-04-24 17:20:00", {
        ("Jack Spencer", "jack.spencer@contoso.example"): (None, "2026-04-24 17:20:00"),
        ("Diego Alvarez", "diego.alvarez@contoso.example"): (None, "2026-04-27 18:00:00"),    # tentative
        ("Jack Henry", "jack.henry@contoso.example"): (None, "2026-04-27 19:10:00"),          # optional
        ("Jack Miller", "jack.miller@contoso.example"): (None, "2026-04-28 20:00:00"),        # tentative, then two emails
        ("Jack Spencer", "rogers.catherine@protonmail.com"): (None, "2026-04-27 21:00:00"),
        ("Isla Hughes", "rebecca.jackson@live.com"): (None, "2026-04-28 16:30:00"),           # optional
    }),
    WPR2: ("Weekly Pipeline Review", "2026-04-24 17:30:00", {
        ("Jack Spencer", "jack.spencer@contoso.example"): (None, "2026-04-24 17:30:00"),
        ("Jasmine Porter", "jasmine.porter@contoso.example"): ("declined", "2026-05-01 20:00:00"),  # after her emailed yes
        ("Jared Ellis", "jared.ellis@contoso.example"): (None, "2026-04-29 23:00:00"),        # declined, before his emailed yes
        ("Jack Miller", "jack.miller@contoso.example"): (None, "2026-04-28 15:00:00"),        # optional
        ("Jack Spencer", "ava.lopez@lumendata.com"): (None, "2026-04-28 16:00:00"),
    }),
}

# a meeting he organised in the window and then cancelled; attendees (name, address, type, response, time)
# meetings he organised that the snapshot does not have; every column is copied from OKR Planning's row, then
# overridden. Attendees are (name, address, type, response, UTC time or None for an unanswered row).
NEW_EVENTS = [
    {"id": CAB, "subject": "Customer Advisory Board prep", "cancelled": True,
     "body": "Customer Advisory Board prep for Jack Spencer. Cancelled on 4 May: we will cover this at the June offsite instead.",
     "start": "2026-05-12 17:00:00", "end": "2026-05-12 17:45:00", "created": "2026-04-24 18:00:00", "modified": "2026-05-04 16:00:00",
     "ical_uid": "c4b7e2a9-5d13-4f86-a0c2-7e9b1d3f5a64@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-04-24 18:00:00"),
         ("Jack Miller", "jack.miller@contoso.example", "required", "notResponded", None),
         ("Jenna White", "jenna.white@contoso.example", "required", "notResponded", None),
         ("Charlotte Palmer", "charlotte.palmer@contoso.example", "required", "tentativelyAccepted", "2026-04-27 16:20:00"),
     ]},
    {"id": VSR, "subject": "Vendor Security Review", "cancelled": False,
     "body": "Vendor Security Review for Jack Spencer: threat model and questionnaire for the new payments vendor.",
     "start": "2026-05-07 21:00:00", "end": "2026-05-07 21:45:00", "created": "2026-05-01 17:00:00", "modified": "2026-05-01 17:00:00",
     "ical_uid": "5e8a1c47-b2d9-4f03-9e6a-1c7d4b2f8a35@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-05-01 17:00:00"),
         ("Jack Henry", "jack.henry@contoso.example", "required", "accepted", "2026-05-04 18:00:00"),
         ("Jasmine Porter", "jasmine.porter@contoso.example", "required", "notResponded", None),
         ("Jared Ellis", "jared.ellis@contoso.example", "required", "tentativelyAccepted", "2026-05-04 20:00:00"),
         ("Olivia Myers", "olivia.myers@contoso.example", "required", "accepted", "2026-05-05 15:00:00"),
         ("Carson Flores", "carson.flores@contoso.example", "optional", "accepted", "2026-05-04 16:00:00"),
     ]},
    {"id": Q3R, "subject": "Q3 Roadmap Review", "cancelled": False,
     "body": "Q3 Roadmap Review for Jack Spencer: walk through the Q3 roadmap with the board deck numbers.",
     "start": "2026-05-11 16:30:00", "end": "2026-05-11 17:30:00", "created": "2026-05-01 17:10:00", "modified": "2026-05-01 17:10:00",
     "ical_uid": "a3f6d9b2-7c41-4e85-b0d3-6f2a9c5e1b74@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-05-01 17:10:00"),
         ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "accepted", "2026-05-06 17:00:00"),
         ("Charlotte Palmer", "charlotte.palmer@contoso.example", "required", "declined", "2026-05-07 16:00:00"),
         ("Jenna White", "jenna.white@contoso.example", "required", "notResponded", None),
         ("Nora Ford", "nora.ford@contoso.example", "required", "accepted", "2026-05-06 18:30:00"),
         ("Cameron Simpson", "cameron.simpson@contoso.example", "required", "tentativelyAccepted", "2026-05-07 22:00:00"),
         ("Janice Gray", "janice.gray@contoso.example", "optional", "accepted", "2026-05-02 15:00:00"),
     ]},
    {"id": HPD, "subject": "Hiring Panel Debrief", "cancelled": False,
     "body": "Hiring Panel Debrief for Jack Spencer: decisions on the three security engineer finalists.",
     "start": "2026-05-15 22:00:00", "end": "2026-05-15 22:45:00", "created": "2026-05-01 17:20:00", "modified": "2026-05-01 17:20:00",
     "ical_uid": "d71b4e95-3a08-4c62-8f1e-9b5c2a7d4e16@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-05-01 17:20:00"),
         ("Jasmine Porter", "jasmine.porter@contoso.example", "required", "accepted", "2026-05-08 16:00:00"),
         ("Cameron Simpson", "cameron.simpson@contoso.example", "required", "declined", "2026-05-11 14:00:00"),
         ("Olivia Myers", "olivia.myers@contoso.example", "required", "notResponded", None),
         ("Jack Miller", "jack.miller@contoso.example", "required", "accepted", "2026-05-08 15:00:00"),
     ]},
    {"id": CES, "subject": "Customer Escalation Sync", "cancelled": False,
     "body": "Customer Escalation Sync for Jack Spencer: Pemberley Bank escalation, before Monday's renewal call.",
     "start": "2026-05-18 00:30:00", "end": "2026-05-18 01:00:00", "created": "2026-05-01 17:30:00", "modified": "2026-05-01 17:30:00",
     "ical_uid": "8c2e5f71-d946-4b3a-a7e0-3d1f8b6c9a52@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-05-01 17:30:00"),
         ("Jenna White", "jenna.white@contoso.example", "required", "notResponded", None),
         ("Jack Spencer", "grace.kelley@pemberleybank.com", "required", "accepted", "2026-05-12 19:00:00"),
         ("Nora Ford", "nora.ford@contoso.example", "required", "tentativelyAccepted", "2026-05-12 20:00:00"),
     ]},
    {"id": POP, "subject": "Planning Offsite Prep", "cancelled": False,
     "body": "Planning Offsite Prep for Jack Spencer.",
     "start": "2026-04-27 04:00:00", "end": "2026-04-27 04:30:00", "created": "2026-04-20 17:00:00", "modified": "2026-04-20 17:00:00",
     "ical_uid": "f4a7c2d8-1e95-4b06-93c7-5a8e2d1f6b39@contoso.example",
     "attendees": [
         ("Jack Spencer", ME, "required", "organizer", "2026-04-20 17:00:00"),
         ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "notResponded", None),
         ("Olivia Myers", "olivia.myers@contoso.example", "required", "notResponded", None),
     ]},
]

TRACKER = ("Hi Jack, here is my RSVP tracker for your meetings as of this morning.\n"
           "OKR Planning (Thu 30 Apr): Diego Alvarez - coming; Jack Henry - coming (Jasmine passed it on); Eugene Dunn - coming.\n"
           "Learning Time (Fri 1 May): Charlotte Palmer - coming (Carson let me know).\n"
           "Brainstorm: New Feature (Fri 1 May): Diego Alvarez - no answer yet; Jack Miller - no answer yet; Jack Henry - coming.\n"
           "Weekly Pipeline Review (Sat 2 May): Jasmine Porter - coming; Jared Ellis - not coming.\n"
           "Weekly Pipeline Review (Wed 6 May): Diego Alvarez - coming; Jenna White - coming; Jared Ellis - coming.\n"
           "Vendor Security Review (Thu 7 May): Jack Henry - coming; Jasmine Porter - no answer yet; Olivia Myers - coming.\n"
           "Q3 Roadmap Review (Mon 11 May): Charlotte Palmer - not coming; Cameron Simpson - no answer yet; Jenna White - no answer yet.\n"
           "Hiring Panel Debrief (Fri 15 May): Cameron Simpson - not coming; Olivia Myers - no answer yet.\n"
           "Customer Advisory Board prep (Tue 12 May): Jack Miller - no answer yet.\n"
           "Planning Offsite Prep (Sun 26 Apr): Diego Alvarez - no answer yet.\n"
           "Janice")

CH_CONV = "CONV9C1F7E32B5A48D06C3F1A9E52D87"
JM_CONV = "CONV4F8D2A63C9E17B05D4A8F2C61E39"
JH_CONV = "CONV5E3B8D16F2A49C07E3B8D16F2C49"
MESSAGES = [
    {"id": "AAMk5D1E0A7C93B24F6E8A1C0D4B7E29", "conversation_id": "CONV7A2C9E41D08B53F6A1E7C2D94B30",
     "internet_message_id": "<M941.0@contoso.example>", "reply_to": None,
     "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example", "subject": "Discovery call prep",
     "text": "Hi Jack, I've put my notes for the discovery call in the shared folder so you have them before next month. Jack M.",
     "received": "2026-04-20 10:12:00"},
    {"id": "AAMk8B3F6D20E1A94C7B5E0F2A9C6D14", "conversation_id": "CONV2E9B4D17A6C05F83E2B9D1C47A68",
     "internet_message_id": "<M942.0@contoso.example>", "reply_to": None,
     "from_name": "Diego Alvarez", "from_address": "diego.alvarez@contoso.example", "subject": "This week",
     "text": "Hi Jack, count me in for tomorrow's planning session, I'll bring the draft objectives. Still not sure about the feature brainstorm on Friday; I'll let you know once the release date firms up. Diego",
     "received": "2026-04-28 17:52:00"},
    {"id": "AAMkC4E7A19B2D6F038E5A7C1B9D2F63", "conversation_id": CH_CONV,
     "internet_message_id": "<M943.0@contoso.example>", "reply_to": None,
     "from_name": "Charlotte Palmer", "from_address": "charlotte.palmer@contoso.example", "subject": "Friday afternoon",
     "text": "Hi Jack, sorry, I won't be able to make Friday's learning session. I'm on the vendor site visit all afternoon. Could you share the recording afterwards? Charlotte",
     "received": "2026-04-29 17:05:00"},
    {"id": "AAMkE2A9C5F71B3D48A6E0C2F7B1D594", "conversation_id": JM_CONV,
     "internet_message_id": "<M944.0@contoso.example>", "reply_to": None,
     "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example", "subject": "Friday evening",
     "text": "Hi Jack, I'll try to make the feature brainstorm on Friday but I can't promise. It depends on whether the release call runs over. Jack M.",
     "received": "2026-04-29 21:30:00"},
    {"id": "AAMk1F6B8E3A20C9D74B1F5E8A3C0D72", "conversation_id": "CONV6B3E9F14D2A87C50B6E3D9F18A24",
     "internet_message_id": "<M945.0@contoso.example>", "reply_to": None,
     "from_name": "Jared Ellis", "from_address": "jared.ellis@contoso.example", "subject": "Saturday",
     "text": "Hi Jack, turns out my Saturday is free after all, so I can make the pipeline review on the 2nd. Jared",
     "received": "2026-04-30 15:20:00"},
    {"id": "AAMk7C2E9A41F3B06D8E2A5C9F1B7D30", "conversation_id": JM_CONV,
     "internet_message_id": "<M946.0@contoso.example>", "reply_to": "AAMkE2A9C5F71B3D48A6E0C2F7B1D594",
     "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example", "subject": "RE: Friday evening",
     "text": "Good news, the release call has moved to Monday, so count me in for the feature brainstorm on Friday. Jack M.",
     "received": "2026-04-30 17:10:00"},
    {"id": "AAMk3B9D5F28A1C74E0B6D3F8A2C5E91", "conversation_id": CH_CONV,
     "internet_message_id": "<M947.0@contoso.example>", "reply_to": "AAMkC4E7A19B2D6F038E5A7C1B9D2F63",
     "from_name": "Charlotte Palmer", "from_address": "charlotte.palmer@contoso.example", "subject": "RE: Friday afternoon",
     "text": "Hi Jack, the site visit might be cancelled, so maybe I can make tomorrow's learning session after all. I'll confirm once I hear back. Charlotte",
     "received": "2026-05-01 04:30:00"},
    {"id": "AAMk9E4A1C73B5D20F8A6C4E1B9D3F57", "conversation_id": "CONV1D8A5F29C3E74B06A9D2F5C81E47",
     "internet_message_id": "<M948.0@contoso.example>", "reply_to": None,
     "from_name": "Jasmine Porter", "from_address": "jasmine.porter@contoso.example", "subject": "OKR Planning",
     "text": "Hi Jack, I bumped into Jack Henry this morning - he says the new OKR Planning time works for him. Jasmine",
     "received": "2026-04-29 16:10:00"},
    {"id": "AAMk6A2D8F15C9B34E7A0D6F2C8B4E13", "conversation_id": "CONV8E3B1D74A6F29C05B8E1D4A73F92",
     "internet_message_id": "<M949.0@contoso.example>", "reply_to": None,
     "from_name": "Carson Flores", "from_address": "carson.flores@contoso.example", "subject": "Learning session",
     "text": "Hi Jack, Charlotte asked me to let you know she'll definitely be at the learning session today. Carson",
     "received": "2026-05-01 17:20:00"},
    {"id": "AAMkB7F3E1A92C6D58B0F4A7E3C9D261", "conversation_id": "CONV3F9C6A18E2B57D04F7A3C9E16B58",
     "internet_message_id": "<M950.0@contoso.example>", "reply_to": None,
     "from_name": "Diego Alvarez", "from_address": "diego.alvarez@contoso.example", "subject": "Q3 roadmap draft",
     "text": "Hi Jack, the Q3 roadmap draft is in the shared folder. Comments welcome before Friday. Diego",
     "received": "2026-05-12 16:05:00"},
    {"id": "AAMk2C8F4A61D9E37B05C2F8A4D16E93", "conversation_id": "CONV5A1E8C42F7D39B06A1E5C8F42D71",
     "internet_message_id": "<M951.0@contoso.example>", "reply_to": None,
     "from_name": "Jasmine Porter", "from_address": "jasmine.porter@contoso.example", "subject": "Saturday review",
     "text": "Hi Jack, count me in for Saturday's pipeline review, I'll bring the partner numbers. Jasmine",
     "received": "2026-04-30 18:34:00"},
    {"id": "AAMkF5B2D9E64A1C38F0B5D2E9A47C16", "conversation_id": "CONV7D4A1F85C2E96B03D7A4F1C85E29",
     "internet_message_id": "<M952.0@contoso.example>", "reply_to": None,
     "from_name": "Diego Alvarez", "from_address": "diego.alvarez@contoso.example", "subject": "Wednesday",
     "text": "Hi Jack, Wednesday's pipeline review works for me as long as the forecast numbers are in by Tuesday night. Diego",
     "received": "2026-05-04 17:03:00"},
    {"id": "AAMk9A3D7F52B1E84C6A9D3F7B52E1C4", "conversation_id": "CONV6E2B9D53A8F14C07E6B2D9A53F84",
     "internet_message_id": "<M954.0@contoso.example>", "reply_to": None,
     "from_name": "Janice Gray", "from_address": "janice.gray@contoso.example", "subject": "RSVP tracker",
     "text": TRACKER,
     "received": "2026-05-11 15:02:00"},
    {"id": "AAMk4E9B6C23F8A15D7E4B9C6F23A851", "conversation_id": "CONV2B7E4A96D1F38C05B2E7A4D96F13",
     "internet_message_id": "<M953.0@contoso.example>", "reply_to": None,
     "from_name": "Jenna White", "from_address": "jenna.white@contoso.example", "subject": "Wednesday's review",
     "text": "Hi Jack, I'm at the customer offsite all day Wednesday, so Kenneth will cover the forecast for me at the pipeline review. Jenna",
     "received": "2026-05-05 20:07:00"},
    {"id": "AAMk3E7C1A95D2B48F6E3C1A95D2F48B", "conversation_id": "CONV9B4F2D68E1A73C05B9F2D68E1C73",
     "internet_message_id": "<M955.0@pemberleybank.com>", "reply_to": None,
     "from_name": "Kenneth Hall", "from_address": "kenneth.hall@pemberleybank.com", "subject": "Forecast",
     "text": "Hi Jack, the forecast numbers are in the shared folder now. Kenneth",
     "received": "2026-05-06 05:40:00"},
    {"id": "AAMk6D2A9F4E81B3C07D6A2F9E4B81C3", "conversation_id": JH_CONV,
     "internet_message_id": "<M956.0@contoso.example>", "reply_to": None,
     "from_name": "Jack Henry", "from_address": "jack.henry@contoso.example", "subject": "Thursday's security review",
     "text": "Hi Jack, count me in for the vendor security review on Thursday. Jack H.",
     "received": "2026-05-04 17:15:00"},
    {"id": "AAMk8F1B6D37A2E94C0F8B6D37A2C94E", "conversation_id": JH_CONV,
     "internet_message_id": "<M957.0@contoso.example>", "reply_to": "AAMk6D2A9F4E81B3C07D6A2F9E4B81C3",
     "from_name": "Jack Henry", "from_address": "jack.henry@contoso.example", "subject": "RE: Thursday's security review",
     "text": "Scratch that - a customer call has landed on Thursday afternoon, so I won't make the vendor review. Jasmine can cover the threat model for me.\n\n> From: Jack Henry\n> Sent: Monday, 4 May 2026 10:15\n> Hi Jack, count me in for the vendor security review on Thursday. Jack H.",
     "received": "2026-05-06 16:40:00"},
    {"id": "AAMk5C9E3B71F4A26D8C5E3B71F4D26A", "conversation_id": "CONV1E6A3C95B7F28D04E1A3C95B7D28",
     "internet_message_id": "<M958.0@contoso.example>", "reply_to": None,
     "from_name": "Jasmine Porter", "from_address": "jasmine.porter@contoso.example", "subject": "Thursday",
     "text": "Hi Jack, I'll be at the 2pm one on Thursday, and I'll bring the questionnaire answers. Jasmine",
     "received": "2026-05-05 18:12:00"},
    {"id": "AAMk2A7F5D19C3E84B6A7F5D19C3B84E", "conversation_id": "CONV4C8E1A73D5B96F02C8E1A73D5F96",
     "internet_message_id": "<M959.0@contoso.example>", "reply_to": None,
     "from_name": "Jared Ellis", "from_address": "jared.ellis@contoso.example", "subject": "Thursday clash",
     "text": "Hi Jack, Thursday's 2pm clashes with a dentist appointment I'm trying to move. I'll know by this evening and let you know then. Jared",
     "received": "2026-05-06 19:25:00"},
    {"id": "AAMk7B3D9F25E1C64A0B3D9F25E1A64C", "conversation_id": "CONV8D2B6F49A3E15C07D2B6F49A3C15",
     "internet_message_id": "<M960.0@contoso.example>", "reply_to": None,
     "from_name": "Cameron Simpson", "from_address": "cameron.simpson@contoso.example", "subject": "Monday's roadmap review",
     "text": "Hi Jack, I can do Monday's roadmap review as long as the board deck is signed off by Friday. Cameron",
     "received": "2026-05-07 23:20:00"},
    {"id": "AAMk1D8A4C62F9B35E7D8A4C62F9E35B", "conversation_id": "CONV3A7D5B18E6C42F09A7D5B18E6F42",
     "internet_message_id": "<M961.0@contoso.example>", "reply_to": None,
     "from_name": "Charlotte Palmer", "from_address": "charlotte.palmer@contoso.example", "subject": "Monday",
     "text": "Hi Jack, I've moved my flight, so I can join Monday's 9:30 after all. Charlotte",
     "received": "2026-05-08 21:05:00"},
    {"id": "AAMk9E5B2D84A7F16C3E5B2D84A7C16F", "conversation_id": "CONV6F1C9E27B4D58A03F1C9E27B4A58",
     "internet_message_id": "<M962.0@contoso.example>", "reply_to": None,
     "from_name": "Nora Ford", "from_address": "nora.ford@contoso.example", "subject": "Board deck",
     "text": "Hi Jack, the board deck was signed off this evening. Nora",
     "received": "2026-05-09 02:35:00"},
    {"id": "AAMk4F2E8B51D6A93C7F2E8B51D6C93A", "conversation_id": "CONV2D9A6E35C8F17B04D9A6E35C8B17",
     "internet_message_id": "<M963.0@contoso.example>", "reply_to": None,
     "from_name": "Cameron Simpson", "from_address": "cameron.simpson@contoso.example", "subject": "Friday's debrief",
     "text": "Hi Jack, ignore my decline for Friday's debrief - I mixed it up with another panel. I'll be there. Cameron",
     "received": "2026-05-12 17:10:00"},
]


def fail(msg):
    print(f"SEED FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

# 1. drift checks: the snapshot must be the one this task was designed on
if cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (USER_ID,)).fetchone()[0] != 9:
    fail("user 46 does not have the expected 9 messages (snapshot drifted or already patched)")
if cur.execute("SELECT email FROM users WHERE id=?", (USER_ID,)).fetchone()[0] != ME:
    fail("user 46 is not Jack Spencer")
if cur.execute("SELECT COUNT(*) FROM mail_folders WHERE id=? AND user_id=? AND well_known_name='inbox'",
               (INBOX, USER_ID)).fetchone()[0] != 1:
    fail("inbox folder missing")
jh = cur.execute("SELECT from_address FROM messages WHERE id=? AND user_id=?", (JACK_HENRY_MSG, USER_ID)).fetchone()
if jh is None or jh[0] != "jack.henry@contoso.example":
    fail("Jack Henry's message missing")
EXPECTED_ATTENDEES = {
    OKR: {("Jack Spencer", ME, "required", "organizer"),
          ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "tentativelyAccepted"),
          ("Jack Henry", "jack.henry@contoso.example", "required", "accepted"),
          ("Jack Miller", "jack.miller@contoso.example", "optional", "notResponded"),
          ("Jack Spencer", "eugene.dunn@pinwheellabs.com", "required", "accepted"),
          ("Isla Hughes", "eugene.dunn@pinwheellabs.com", "required", "accepted")},
    WPR6: {("Jack Spencer", ME, "required", "organizer"),
           ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "accepted"),
           ("Jenna White", "jenna.white@contoso.example", "required", "accepted"),
           ("Jared Ellis", "jared.ellis@contoso.example", "required", "accepted"),
           ("Jack Spencer", "kenneth.hall@pemberleybank.com", "required", "accepted")},
    LT: {("Jack Spencer", ME, "required", "organizer"),
         ("Charlotte Palmer", "charlotte.palmer@contoso.example", "required", "notResponded"),
         ("Jack Spencer", "edward.clark@forgeco.com", "required", "accepted")},
    BS: {("Jack Spencer", ME, "required", "organizer"),
         ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "tentativelyAccepted"),
         ("Jack Henry", "jack.henry@contoso.example", "optional", "accepted"),
         ("Jack Miller", "jack.miller@contoso.example", "required", "tentativelyAccepted"),
         ("Jack Spencer", "rogers.catherine@protonmail.com", "required", "accepted"),
         ("Isla Hughes", "rebecca.jackson@live.com", "optional", "tentativelyAccepted")},
    WPR2: {("Jack Spencer", ME, "required", "organizer"),
           ("Jasmine Porter", "jasmine.porter@contoso.example", "required", "accepted"),
           ("Jared Ellis", "jared.ellis@contoso.example", "required", "declined"),
           ("Jack Miller", "jack.miller@contoso.example", "optional", "accepted"),
           ("Jack Spencer", "ava.lopez@lumendata.com", "required", "accepted")},
}
SUBJECTS = {**{k: v[0] for k, v in MOVES.items()}, **{k: v[0] for k, v in UNMOVED.items()}}
for ev_id, subject in SUBJECTS.items():
    ev = cur.execute("SELECT subject, user_id, is_organizer, is_cancelled, body_content FROM events WHERE id=?", (ev_id,)).fetchone()
    if ev is None or ev["subject"] != subject or ev["user_id"] != USER_ID or not ev["is_organizer"] or ev["is_cancelled"]:
        fail(f"{subject} event {ev_id} drifted")
    if "Moved on" in (ev["body_content"] or "") or "Cancelled on" in (ev["body_content"] or ""):
        fail(f"{subject} already patched")
    got = {(r[0], r[1].lower(), r[2], r[3]) for r in
           cur.execute("SELECT name, address, attendee_type, response FROM event_attendees WHERE event_id=?", (ev_id,))}
    if got != EXPECTED_ATTENDEES[ev_id]:
        fail(f"{subject} attendees drifted: {sorted(got)}")
tpl = cur.execute("SELECT * FROM messages WHERE id=?", (TEMPLATE_ID,)).fetchone()
if tpl is None or tpl["from_address"] != "charlotte.palmer@contoso.example":
    fail("template message missing")
tpl = dict(tpl)
ev_tpl = cur.execute("SELECT created_datetime FROM events WHERE id=?", (OKR,)).fetchone()[0]

# 2. collision checks
for m in MESSAGES:
    if cur.execute("SELECT 1 FROM messages WHERE id=? OR internet_message_id=?", (m["id"], m["internet_message_id"])).fetchone():
        fail(f"id collision for {m['id']}")
    if m["reply_to"] is None and cur.execute("SELECT 1 FROM messages WHERE conversation_id=?", (m["conversation_id"],)).fetchone():
        fail(f"conversation collision for {m['conversation_id']}")
    if cur.execute("SELECT 1 FROM messages WHERE user_id=? AND received_datetime LIKE ?",
                   (USER_ID, m["received"][:16] + "%")).fetchone():
        fail(f"timestamp collision at {m['received']}")


for ne in NEW_EVENTS:
    if cur.execute("SELECT 1 FROM events WHERE id=? OR ical_uid=?", (ne["id"], ne["ical_uid"])).fetchone():
        fail(f"{ne['subject']}: id or iCalUId collision")
    if cur.execute("SELECT 1 FROM events WHERE user_id=? AND subject=?", (USER_ID, ne["subject"])).fetchone():
        fail(f"{ne['subject']}: subject already present")


def ts_like(sample, s):
    return s.replace(" ", "T") if "T" in str(sample) else s + ".000000"


# 3a. messages: every column copied from the template row, then overridden
cols = list(tpl.keys())
for m in MESSAGES:
    row = dict(tpl)
    row.update({
        "id": m["id"], "user_id": USER_ID, "parent_folder_id": INBOX,
        "conversation_id": m["conversation_id"], "conversation_index": 0 if m["reply_to"] is None else 1,
        "internet_message_id": m["internet_message_id"],
        "in_reply_to_message_id": m["reply_to"], "forwarded_from_message_id": None,
        "subject": m["subject"], "body_preview": m["text"][:255],
        "body_content": "<html><body><p>" + m["text"].replace("\n", "<br>\n") + "</p></body></html>", "body_content_type": "html", "body_text": m["text"],
        "sender_name": m["from_name"], "sender_address": m["from_address"],
        "from_name": m["from_name"], "from_address": m["from_address"],
        "importance": "normal", "is_read": 1, "is_draft": 0, "has_attachments": 0,
        "web_link": f"https://outlook.office.com/mail/deeplink/read/{m['id']}",
        "created_datetime": ts_like(tpl["created_datetime"], m["received"]),
        "last_modified_datetime": ts_like(tpl["created_datetime"], m["received"]),
        "received_datetime": ts_like(tpl["created_datetime"], m["received"]),
        "sent_datetime": ts_like(tpl["created_datetime"], m["received"]),
    })
    cur.execute(f"INSERT INTO messages ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [row[c] for c in cols])
    cur.execute("INSERT INTO message_recipients (message_id, recipient_type, name, address) VALUES (?, 'to', ?, ?)",
                (m["id"], "Jack Spencer", ME))
cur.execute("UPDATE mail_folders SET total_item_count = total_item_count + ? WHERE id=?", (len(MESSAGES), INBOX))

# 3b. the two moved meetings: the move note, and times that place each answer before or after it
for ev_id, (subject, note, created, modified, times) in MOVES.items():
    cur.execute("UPDATE events SET body_preview=?, body_content=?, body_content_type='text', created_datetime=?, "
                "last_modified_datetime=?, response_status_time=? WHERE id=?",
                (note[:512], note, ts_like(ev_tpl, created), ts_like(ev_tpl, modified), ts_like(ev_tpl, created), ev_id))
    for (name, addr), when in times.items():
        n = cur.execute("UPDATE event_attendees SET response_time=? WHERE event_id=? AND name=? AND lower(address)=?",
                        (ts_like(ev_tpl, when), ev_id, name, addr)).rowcount
        if n != 1:
            fail(f"{subject}: response time for {name} <{addr}> matched {n} rows")

# 3c. the unmoved meetings: created/modified before every answer, a time on each answer, Jasmine's decline
for ev_id, (subject, created, times) in UNMOVED.items():
    cur.execute("UPDATE events SET created_datetime=?, last_modified_datetime=?, response_status_time=? WHERE id=?",
                (ts_like(ev_tpl, created), ts_like(ev_tpl, created), ts_like(ev_tpl, created), ev_id))
    for (name, addr), (resp, when) in times.items():
        if resp is None:
            n = cur.execute("UPDATE event_attendees SET response_time=? WHERE event_id=? AND name=? AND lower(address)=?",
                            (ts_like(ev_tpl, when), ev_id, name, addr)).rowcount
        else:
            n = cur.execute("UPDATE event_attendees SET response=?, response_time=? WHERE event_id=? AND name=? AND lower(address)=?",
                            (resp, ts_like(ev_tpl, when), ev_id, name, addr)).rowcount
        if n != 1:
            fail(f"{subject}: response time for {name} <{addr}> matched {n} rows")

# 3d. the new meetings: every column copied from OKR Planning's row, then overridden
ev_tpl_row = dict(cur.execute("SELECT * FROM events WHERE id=?", (OKR,)).fetchone())
att_tpl = dict(cur.execute("SELECT * FROM event_attendees WHERE event_id=? ORDER BY id LIMIT 1", (OKR,)).fetchone())
un = cur.execute("SELECT response_time FROM event_attendees WHERE response='notResponded' LIMIT 1").fetchone()
next_id = cur.execute("SELECT MAX(id) FROM event_attendees").fetchone()[0] + 1
for ne in NEW_EVENTS:
    ev_row = dict(ev_tpl_row)
    ev_row.update({
        "id": ne["id"], "subject": ne["subject"], "body_preview": ne["body"][:512],
        "body_content": ne["body"], "body_content_type": "text",
        "start_datetime": ts_like(ev_tpl, ne["start"]), "end_datetime": ts_like(ev_tpl, ne["end"]),
        "is_cancelled": 1 if ne["cancelled"] else 0, "is_organizer": 1, "series_master_id": None, "recurrence": None,
        "ical_uid": ne["ical_uid"], "transaction_id": None,
        "web_link": f"https://outlook.office.com/calendar/item/{ne['id']}",
        "online_meeting_join_url": None, "online_meeting_conference_id": None,
        "response_status": "organizer", "response_status_time": ts_like(ev_tpl, ne["created"]),
        "created_datetime": ts_like(ev_tpl, ne["created"]),
        "last_modified_datetime": ts_like(ev_tpl, ne["modified"]),
    })
    ev_cols = list(ev_row.keys())
    cur.execute(f"INSERT INTO events ({', '.join(ev_cols)}) VALUES ({', '.join('?' for _ in ev_cols)})", [ev_row[c] for c in ev_cols])
    for name, addr, kind, resp, when in ne["attendees"]:
        row = dict(att_tpl)
        row.update({"id": next_id, "event_id": ne["id"], "attendee_type": kind, "name": name, "address": addr,
                    "response": resp, "proposed_new_time": None,
                    # unanswered rows copy the time column of one of the gym's own unanswered rows
                    "response_time": ts_like(ev_tpl, when) if when else (un[0] if un else None)})
        next_id += 1
        a_cols = list(row.keys())
        cur.execute(f"INSERT INTO event_attendees ({', '.join(a_cols)}) VALUES ({', '.join('?' for _ in a_cols)})",
                    [row[c] for c in a_cols])
con.commit()

# 4. post-conditions
if cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (USER_ID,)).fetchone()[0] != 9 + len(MESSAGES):
    fail("post-check: message count")
for m in MESSAGES:
    got = cur.execute("SELECT m.parent_folder_id, m.from_address, r.address FROM messages m "
                      "JOIN message_recipients r ON r.message_id=m.id WHERE m.id=?", (m["id"],)).fetchall()
    if [tuple(g) for g in got] != [(INBOX, m["from_address"], ME)]:
        fail(f"post-check: {m['id']} not visible as expected: {[tuple(g) for g in got]}")
for ev_id, (subject, note, *_rest) in MOVES.items():
    if cur.execute("SELECT body_content FROM events WHERE id=?", (ev_id,)).fetchone()[0] != note:
        fail(f"post-check: move note on {subject}")
if cur.execute("SELECT response FROM event_attendees WHERE event_id=? AND lower(address)='jasmine.porter@contoso.example'",
               (WPR2,)).fetchone()[0] != "declined":
    fail("post-check: Jasmine Porter's decline")
for ne in NEW_EVENTS:
    got = cur.execute("SELECT is_cancelled, is_organizer, user_id FROM events WHERE id=?", (ne["id"],)).fetchone()
    if got is None or tuple(got) != (1 if ne["cancelled"] else 0, 1, USER_ID):
        fail(f"post-check: {ne['subject']}")
    if cur.execute("SELECT COUNT(*) FROM event_attendees WHERE event_id=?", (ne["id"],)).fetchone()[0] != len(ne["attendees"]):
        fail(f"post-check: {ne['subject']} attendees")
if cur.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    fail("integrity_check")
con.close()
print(f"seeded {len(MESSAGES)} messages, {len(MOVES)} meeting moves, answer times on {len(MOVES) + len(UNMOVED)} meetings "
      f"and {len(NEW_EVENTS)} new meetings into user {USER_ID}'s data in {DB}")
