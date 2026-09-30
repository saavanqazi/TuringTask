#!/usr/bin/env python3
"""Build-time seed for the outlook gym (Handbook 8.1). Run once by the Dockerfile, then deleted.

Patches the gym's synthetic snapshot, Synthetic_db.db, which every /reset copies into the
per-run database, for Jack Spencer (user 46):
  * seven inbox messages (some people answer meeting invitations by email, some more than once);
  * his copy of OKR Planning: a note that it was moved on 28 April, created/modified times to
    match, and response times on its attendees (two answered before the move, two after).
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

MOVE_NOTE = ("OKR Planning for Jack Spencer. Moved on 28 April: this was Wednesday 29 April 10:00; "
             "it is now Thursday 30 April 13:25.")
OKR_CREATED = "2026-04-24 17:00:00"
OKR_MODIFIED = "2026-04-28 18:00:00"   # the move (11:00 Pacific, 28 April)
# (name, address) -> response time; the responses themselves are unchanged
OKR_RESPONSE_TIMES = {
    ("Diego Alvarez", "diego.alvarez@contoso.example"): "2026-04-27 16:50:00",   # tentative
    ("Jack Henry", "jack.henry@contoso.example"): "2026-04-27 15:30:00",         # accepted, before the move
    ("Jack Spencer", "eugene.dunn@pinwheellabs.com"): "2026-04-29 09:00:00",     # accepted, after the move
    ("Isla Hughes", "eugene.dunn@pinwheellabs.com"): "2026-04-29 09:05:00",      # accepted, after the move
}

CH_CONV = "CONV9C1F7E32B5A48D06C3F1A9E52D87"
JM_CONV = "CONV4F8D2A63C9E17B05D4A8F2C61E39"
MESSAGES = [
    {"id": "AAMk5D1E0A7C93B24F6E8A1C0D4B7E29", "conversation_id": "CONV7A2C9E41D08B53F6A1E7C2D94B30",
     "internet_message_id": "<M941.0@contoso.example>", "reply_to": None,
     "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example", "subject": "Discovery call prep",
     "text": "Hi Jack, I've put my notes for the discovery call in the shared folder so you have them before next month. Jack M.",
     "received": "2026-04-20 10:12:00"},
    {"id": "AAMk8B3F6D20E1A94C7B5E0F2A9C6D14", "conversation_id": "CONV2E9B4D17A6C05F83E2B9D1C47A68",
     "internet_message_id": "<M942.0@contoso.example>", "reply_to": None,
     "from_name": "Diego Alvarez", "from_address": "diego.alvarez@contoso.example", "subject": "This week",
     "text": "Hi Jack, count me in for Wednesday's planning session, I'll bring the draft objectives. Still not sure about the feature brainstorm on Friday; I'll let you know once the release date firms up. Diego",
     "received": "2026-04-27 16:42:00"},
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
     "text": "Hi Jack, the site visit might be cancelled, so maybe I can make the learning session this afternoon after all. I'll confirm once I hear back. Charlotte",
     "received": "2026-05-01 15:05:00"},
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
okr = cur.execute("SELECT subject, user_id, is_organizer, is_cancelled, body_content FROM events WHERE id=?", (OKR,)).fetchone()
if okr is None or okr["subject"] != "OKR Planning" or okr["user_id"] != USER_ID or not okr["is_organizer"] or okr["is_cancelled"]:
    fail("OKR Planning event drifted")
if "Moved on" in (okr["body_content"] or ""):
    fail("OKR Planning already patched")
expected = {("Jack Spencer", ME, "required", "organizer"),
            ("Diego Alvarez", "diego.alvarez@contoso.example", "required", "tentativelyAccepted"),
            ("Jack Henry", "jack.henry@contoso.example", "required", "accepted"),
            ("Jack Miller", "jack.miller@contoso.example", "optional", "notResponded"),
            ("Jack Spencer", "eugene.dunn@pinwheellabs.com", "required", "accepted"),
            ("Isla Hughes", "eugene.dunn@pinwheellabs.com", "required", "accepted")}
got = {(r[0], r[1].lower(), r[2], r[3]) for r in
       cur.execute("SELECT name, address, attendee_type, response FROM event_attendees WHERE event_id=?", (OKR,))}
if got != expected:
    fail(f"OKR Planning attendees drifted: {sorted(got)}")
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
        "body_content": f"<html><body><p>{m['text']}</p></body></html>", "body_content_type": "html", "body_text": m["text"],
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

# 3b. OKR Planning: the move note, and times that place each answer before or after it
cur.execute("UPDATE events SET body_preview=?, body_content=?, body_content_type='text', created_datetime=?, last_modified_datetime=? WHERE id=?",
            (MOVE_NOTE, MOVE_NOTE, ts_like(ev_tpl, OKR_CREATED), ts_like(ev_tpl, OKR_MODIFIED), OKR))
for (name, addr), when in OKR_RESPONSE_TIMES.items():
    n = cur.execute("UPDATE event_attendees SET response_time=? WHERE event_id=? AND name=? AND lower(address)=?",
                    (ts_like(ev_tpl, when), OKR, name, addr)).rowcount
    if n != 1:
        fail(f"response time for {name} <{addr}> matched {n} rows")
con.commit()

# 4. post-conditions
if cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (USER_ID,)).fetchone()[0] != 9 + len(MESSAGES):
    fail("post-check: message count")
for m in MESSAGES:
    got = cur.execute("SELECT m.parent_folder_id, m.from_address, r.address FROM messages m "
                      "JOIN message_recipients r ON r.message_id=m.id WHERE m.id=?", (m["id"],)).fetchall()
    if [tuple(g) for g in got] != [(INBOX, m["from_address"], ME)]:
        fail(f"post-check: {m['id']} not visible as expected: {[tuple(g) for g in got]}")
if "Moved on 28 April" not in cur.execute("SELECT body_content FROM events WHERE id=?", (OKR,)).fetchone()[0]:
    fail("post-check: move note")
if cur.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    fail("integrity_check")
con.close()
print(f"seeded {len(MESSAGES)} messages and the OKR Planning move into user {USER_ID}'s data in {DB}")
