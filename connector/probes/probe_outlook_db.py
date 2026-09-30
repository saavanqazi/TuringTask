"""probe_outlook_db.py - run AS ROOT in a throwaway container (authoring only, never shipped):
  docker exec c1probe python3 /tmp/probe_outlook_db.py
Shows where the outlook gym keeps its seed data, the schema of the tables the task uses, and
Jack Spencer's (user 46) mailbox in full, so a seed patch can be designed against the real rows."""
import glob, os, sqlite3

print("== outlook gym files")
for pat in ("/gyms/outlook/*", "/gyms/outlook/app/*", "/gyms/outlook/app/data/*", "/gyms/outlook/app/data/*/*",
            "/gyms/outlook/mcp_databases/*"):
    for p in sorted(glob.glob(pat))[:40]:
        try:
            print(f"  {os.path.getsize(p):>12}  {p}")
        except OSError:
            print("  ?", p)
seeds = [p for p in glob.glob("/gyms/outlook/**/*", recursive=True)
         if p.endswith((".sql", ".db", ".sqlite", ".sqlite3")) and "mcp_databases" not in p]
print("== seed-like files:", seeds[:30])

dbs = sorted(glob.glob("/gyms/outlook/mcp_databases/*.db"), key=os.path.getmtime)
target = dbs[-1] if dbs else next((p for p in seeds if p.endswith(".db")), None)
print("== database inspected:", target)
con = sqlite3.connect(target)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)
for t in ("users", "messages", "message_recipients", "mail_folders", "events", "event_attendees", "calendars"):
    if t in tables:
        sql = cur.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"\n-- {t} ({n} rows)\n{sql}")
print("\n== user 46")
print(cur.execute("SELECT * FROM users WHERE id=46").fetchall())
print("\n== every message owned by user 46 (mailbox), newest first")
cols = [r[1] for r in cur.execute("PRAGMA table_info(messages)")]
want = [c for c in ("id", "conversation_id", "parent_folder_id", "subject", "from_address", "from_name", "is_draft",
                    "is_read", "received_date_time", "sent_date_time", "in_reply_to_message_id", "body_content") if c in cols]
order = "received_date_time" if "received_date_time" in cols else "id"
for row in cur.execute(f"SELECT {', '.join(want)} FROM messages WHERE user_id=46 ORDER BY {order} DESC"):
    d = dict(zip(want, row))
    if "body_content" in d and d["body_content"]:
        d["body_content"] = d["body_content"][:220]
    print(d)
if "message_recipients" in tables:
    print("\n== recipients of user 46's messages")
    for row in cur.execute("SELECT r.message_id, r.recipient_type, r.address FROM message_recipients r JOIN messages m ON m.id=r.message_id WHERE m.user_id=46 LIMIT 60"):
        print(row)
print("\n== mail folders of user 46")
if "mail_folders" in tables:
    fcols = [r[1] for r in cur.execute("PRAGMA table_info(mail_folders)")]
    print(fcols)
    print(cur.execute("SELECT * FROM mail_folders WHERE user_id=46").fetchall()[:20])
