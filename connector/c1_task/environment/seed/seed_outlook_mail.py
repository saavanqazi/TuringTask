#!/usr/bin/env python3
"""Build-time seed for the outlook gym (Handbook 8.1). Run once by the Dockerfile, then deleted.

Adds five inbox messages to Jack Spencer's mailbox (user 46) in the gym's synthetic
snapshot, Synthetic_db.db, which every /reset copies into the per-run database. The
build fails (non-zero exit) if the snapshot has drifted from the rows this task was
designed against, if any new id or timestamp collides with an existing row, or if the
rows are not visible afterwards. Re-running it on an already patched snapshot also fails.
"""
import json
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/gyms/outlook/app/data/Synthetic_db.db"
USER_ID = 46
ME = "jack.spencer@contoso.example"
INBOX = "AFB284B4386E878EFB2144F05C52DA"
TEMPLATE_ID = "AAMkD61867BD0A78844C3815861A41BA"  # an existing inbox-style message of his

MESSAGES = [
    {
        "id": "AAMk5D1E0A7C93B24F6E8A1C0D4B7E29",
        "conversation_id": "CONV7A2C9E41D08B53F6A1E7C2D94B30",
        "internet_message_id": "<M941.0@contoso.example>",
        "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example",
        "subject": "Discovery call prep",
        "text": "Hi Jack, I've put my notes for the discovery call in the shared folder so you have them before next month. Jack M.",
        "received": "2026-04-20 10:12:00",
    },
    {
        "id": "AAMk8B3F6D20E1A94C7B5E0F2A9C6D14",
        "conversation_id": "CONV2E9B4D17A6C05F83E2B9D1C47A68",
        "internet_message_id": "<M942.0@contoso.example>",
        "from_name": "Diego Alvarez", "from_address": "diego.alvarez@contoso.example",
        "subject": "This week",
        "text": "Hi Jack, count me in for Thursday's planning session, I'll bring the draft objectives. Still not sure about the feature brainstorm on Friday; I'll let you know once the release date firms up. Diego",
        "received": "2026-04-28 16:42:00",
    },
    {
        "id": "AAMkC4E7A19B2D6F038E5A7C1B9D2F63",
        "conversation_id": "CONV9C1F7E32B5A48D06C3F1A9E52D87",
        "internet_message_id": "<M943.0@contoso.example>",
        "from_name": "Charlotte Palmer", "from_address": "charlotte.palmer@contoso.example",
        "subject": "Friday afternoon",
        "text": "Hi Jack, sorry, I won't be able to make Friday's learning session. I'm on the vendor site visit all afternoon. Could you share the recording afterwards? Charlotte",
        "received": "2026-04-29 17:05:00",
    },
    {
        "id": "AAMkE2A9C5F71B3D48A6E0C2F7B1D594",
        "conversation_id": "CONV4F8D2A63C9E17B05D4A8F2C61E39",
        "internet_message_id": "<M944.0@contoso.example>",
        "from_name": "Jack Miller", "from_address": "jack.miller@contoso.example",
        "subject": "Friday evening",
        "text": "Hi Jack, I'll try to make the feature brainstorm on Friday but I can't promise. It depends on whether the release call runs over. Jack M.",
        "received": "2026-04-29 21:30:00",
    },
    {
        "id": "AAMk1F6B8E3A20C9D74B1F5E8A3C0D72",
        "conversation_id": "CONV6B3E9F14D2A87C50B6E3D9F18A24",
        "internet_message_id": "<M945.0@contoso.example>",
        "from_name": "Jared Ellis", "from_address": "jared.ellis@contoso.example",
        "subject": "Saturday",
        "text": "Hi Jack, turns out my Saturday is free after all, so I can make the pipeline review on the 2nd. Jared",
        "received": "2026-04-30 15:20:00",
    },
]

# The calendar rows the task was designed against: (event id, attendee address, type, response).
EXPECTED_ATTENDEES = [
    ("AE3EC3B6C974C7331A84246F23D559", "diego.alvarez@contoso.example", "required", "tentativelyAccepted"),
    ("AE3EC3B6C974C7331A84246F23D559", "jack.miller@contoso.example", "optional", "notResponded"),
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
for ev, addr, typ, resp in EXPECTED_ATTENDEES:
    row = cur.execute("SELECT attendee_type, response FROM event_attendees WHERE event_id=? AND lower(address)=?",
                      (ev, addr)).fetchone()
    if row is None or (row[0], row[1]) != (typ, resp):
        fail(f"calendar drifted: {ev} {addr} is {tuple(row) if row else None}, expected {(typ, resp)}")
if cur.execute("SELECT COUNT(*) FROM mail_folders WHERE id=? AND user_id=? AND well_known_name='inbox'",
               (INBOX, USER_ID)).fetchone()[0] != 1:
    fail("inbox folder missing")
tpl = cur.execute("SELECT * FROM messages WHERE id=?", (TEMPLATE_ID,)).fetchone()
if tpl is None:
    fail("template message missing")
tpl = dict(tpl)

# 2. collision checks
for m in MESSAGES:
    if cur.execute("SELECT 1 FROM messages WHERE id=? OR conversation_id=? OR internet_message_id=?",
                   (m["id"], m["conversation_id"], m["internet_message_id"])).fetchone():
        fail(f"id collision for {m['id']}")
    if cur.execute("SELECT 1 FROM messages WHERE user_id=? AND received_datetime LIKE ?",
                   (USER_ID, m["received"][:16] + "%")).fetchone():
        fail(f"timestamp collision at {m['received']}")

stamp_has_t = "T" in str(tpl["created_datetime"])
def ts(s):
    return s.replace(" ", "T") if stamp_has_t else s + ".000000"

# 3. insert: every column copied from the template row, then overridden
cols = list(tpl.keys())
for m in MESSAGES:
    row = dict(tpl)
    html = f"<html><body><p>{m['text']}</p></body></html>"
    row.update({
        "id": m["id"], "user_id": USER_ID, "parent_folder_id": INBOX,
        "conversation_id": m["conversation_id"], "conversation_index": 0,
        "internet_message_id": m["internet_message_id"],
        "in_reply_to_message_id": None, "forwarded_from_message_id": None,
        "subject": m["subject"], "body_preview": m["text"][:255], "body_content": html,
        "body_content_type": "html", "body_text": m["text"],
        "sender_name": m["from_name"], "sender_address": m["from_address"],
        "from_name": m["from_name"], "from_address": m["from_address"],
        "importance": "normal", "is_read": 1, "is_draft": 0, "has_attachments": 0,
        "web_link": f"https://outlook.office.com/mail/deeplink/read/{m['id']}",
        "created_datetime": ts(m["received"]), "last_modified_datetime": ts(m["received"]),
        "received_datetime": ts(m["received"]), "sent_datetime": ts(m["received"]),
    })
    cur.execute(f"INSERT INTO messages ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols])
    cur.execute("INSERT INTO message_recipients (message_id, recipient_type, name, address) VALUES (?, 'to', ?, ?)",
                (m["id"], "Jack Spencer", ME))
cur.execute("UPDATE mail_folders SET total_item_count = total_item_count + ? WHERE id=?", (len(MESSAGES), INBOX))
con.commit()

# 4. post-conditions
if cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (USER_ID,)).fetchone()[0] != 9 + len(MESSAGES):
    fail("post-check: message count")
for m in MESSAGES:
    got = cur.execute("SELECT m.parent_folder_id, m.from_address, r.address FROM messages m "
                      "JOIN message_recipients r ON r.message_id=m.id WHERE m.id=?", (m["id"],)).fetchall()
    if [tuple(g) for g in got] != [(INBOX, m["from_address"], ME)]:
        fail(f"post-check: {m['id']} not visible as expected: {[tuple(g) for g in got]}")
if cur.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    fail("integrity_check")
con.close()
print(f"seeded {len(MESSAGES)} messages into user {USER_ID}'s inbox in {DB}")
