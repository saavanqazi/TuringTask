"""Re-derive the ledger, tracker fixes and chase set from the REAL oracle replay payloads under the gold
rules and under each naive reading, so every wrong value in consistency/requirements.json is computed."""
import json, sys, datetime as dt
from collections import defaultdict
from pathlib import Path
import os as _o; sys.path.insert(0, str(Path(_o.environ["DV_PLAN"]).parent))
from verify_gold_from_oracle import payload_of, norm_ts

import os
traj = json.loads(Path(os.environ["DV_TRAJ"]).read_text())
plan = json.loads(Path(os.environ["DV_PLAN"]).read_text())
ME = plan["acting_user_email"]; LO, HI = plan["window"]
events = payload_of([s for s in traj if s.get("name") == "search_calendar"][0])["value"]
mail = {}
for s in traj:
    if s.get("name") == "search_email":
        for m in payload_of(s).get("value", []): mail[m["id"]] = m
sender = lambda m: (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
pac2utc = lambda s: (dt.datetime.fromisoformat(s[:19]) + dt.timedelta(hours=7)).strftime("%Y-%m-%d")
utc2pacdate = lambda z: (dt.datetime.fromisoformat(z[:19]) - dt.timedelta(hours=7)).strftime("%Y-%m-%d")
INV = {"accepted": "yes", "declined": "no", "tentativelyAccepted": "maybe"}

def derive(v=frozenset()):
    def in_window(e):
        d = pac2utc(e["start"]["dateTime"]) if "utc_window" in v else e["start"]["dateTime"][:10]
        return LO <= d <= HI
    run = [e for e in events if e.get("isOrganizer") and in_window(e) and ("include_cancelled" in v or not e.get("isCancelled"))]
    key_of = {e["id"]: (e["subject"], e["start"]["dateTime"][:10]) for e in run}
    moved = {}
    if "ignore_moves" not in v:
        for mv in plan["moves"]:
            for e in run:
                if key_of[e["id"]] == (mv["meeting"], mv["start"]): moved[key_of[e["id"]]] = norm_ts(mv["moved_at"])
    answers, people = defaultdict(list), set()
    for e in run:
        for a in e.get("attendees", []):
            addr = a["emailAddress"]["address"].lower()
            if addr == ME or a["status"]["response"] == "organizer": continue
            if a.get("type") != "required" and "include_optional" not in v: continue
            if a.get("type") == "resource": continue
            if "drop_display_name_me" in v and a["emailAddress"]["name"] == "Jack Spencer": continue
            k = key_of[e["id"]] + (addr,); people.add(k)
            r = a["status"]["response"]
            if r in INV: answers[k].append((norm_ts(a["status"].get("time")), INV[r], "INVITATION"))
    visible = mail
    if "default_page" in v:
        visible = dict(sorted(mail.items(), key=lambda kv: kv[1]["receivedDateTime"], reverse=True)[:25])
    if "invitation_only" not in v:
        for ans in plan["email_answers"]:
            m = visible.get(ans["message_id"])
            if m is None: continue
            if "indirect_unmapped" in v and ans["quote"].startswith("I'll be at the 2pm one"): continue
            kind = ans["answer"]
            if "quoted_yes" in v and ans["quote"].startswith("Scratch that"): kind = "yes"
            if "delegation_as_relay" in v and "will cover the forecast for me" in ans["quote"]: continue
            if kind == "conditional":
                sb = ans.get("settled_by"); sm = visible.get(sb["message_id"]) if sb else None
                if "conditional_never" not in v and sm is not None:
                    if "utc_settlement" in v:
                        ok = sm["receivedDateTime"][:10] <= utc2pacdate(sb["deadline"])
                    else:
                        ok = norm_ts(sm["receivedDateTime"]) <= norm_ts(sb["deadline"])
                    kind = "yes" if ok else "maybe"
                else:
                    kind = "maybe"
            k = (ans["meeting"], ans["date"], ans["from"])
            t = norm_ts(m["receivedDateTime"])
            if "email_overrides" in v: t = "9999" + t
            answers[k].append((t, kind, "EMAIL"))
        if "relayed_counts" in v:
            for rel in plan["relayed"]:
                m = visible.get(rel["message_id"])
                if m: answers[(rel["meeting"], rel["date"], rel["for"])].append((norm_ts(m["receivedDateTime"]), "yes", "EMAIL"))
    ledger = {}
    for k in people:
        live = [x for x in answers[k] if not (k[:2] in moved and x[0].replace("9999", "") < moved[k[:2]])]
        if not live: ledger[k] = ("OWES_ANSWER", "NONE"); continue
        _, kind, src = max(live)
        ledger[k] = {"yes": ("COMING", src), "no": ("NOT_COMING", src)}.get(kind, ("OWES_ANSWER", "NONE"))
    fixes = set()
    for en in plan["tracker"]["entries"]:
        k = (en["meeting"], en["date"], en["attendee"] or "")
        if k in ledger and ledger[k][0] != en["tracker_status"]: fixes.add(k + (en["tracker_status"], ledger[k][0]))
    chase = sorted({k[2] for k, s in ledger.items() if s[0] == "OWES_ANSWER"})
    return ledger, fixes, chase

GOLD = derive()
gl = {(r["meeting"], r["date"], r["attendee"]): (r["status"], r["source"]) for r in plan["ledger"]}
assert GOLD[0] == gl and len(GOLD[1]) == len(plan["tracker_fixes"]) and GOLD[2] == sorted(plan["write_back"]["chase"]), "gold mismatch"
VARIANTS = {
    "utc_window": "bound the window by UTC dates (or search it with UTC bounds): Customer Escalation Sync (Sun 17 May 17:30 Pacific) falls out, Planning Offsite Prep (Sun 26 Apr 21:00 Pacific) falls in",
    "utc_settlement": "judge 'by Tuesday night' / 'by Friday' against the UTC date of the settling note (Kenneth 6 May 05:40Z, Nora 9 May 02:35Z read as Wednesday / Saturday)",
    "conditional_never": "treat a conditional yes as never an answer, even after its condition has happened",
    "quoted_yes": "take Jack Henry's quoted 'count me in' under his 6 May reply as his latest word on the vendor review",
    "indirect_unmapped": "fail to map Jasmine's 'the 2pm one on Thursday' to the Vendor Security Review",
    "email_overrides": "let any email answer override the invitation whatever their times (the old 'email wins' habit)",
    "invitation_only": "read only the invitation responses and ignore every email",
    "relayed_counts": "count Jasmine's note for Jack Henry and Carson's note for Charlotte as their answers",
    "delegation_as_relay": "read Jenna's 'Kenneth will cover the forecast for me' as a relayed note rather than her own no",
    "ignore_moves": "ignore the two move notes, so answers given before a meeting moved still count",
    "include_cancelled": "keep the cancelled Customer Advisory Board prep",
    "include_optional": "keep optional attendees",
    "drop_display_name_me": "drop every attendee whose display name is 'Jack Spencer' as if it were him",
    "default_page": "read the mailbox with one default 25-message page, so the oldest 7 messages (the late-April answers, Olivia's only email) are never seen",
}
if __name__ == "__main__":
  out = {}
  for name, desc in VARIANTS.items():
      led, fx, ch = derive(frozenset([name]))
      diff_rows = sorted({k for k in set(led) | set(GOLD[0]) if led.get(k) != GOLD[0].get(k)})
      out[name] = {"method": desc, "ledger_rows": len(led), "ledger_rows_wrong_or_missing_or_extra": len(diff_rows),
                   "affected": [f"{m} {d} {a}: gold {GOLD[0].get((m,d,a))} -> {led.get((m,d,a))}" for m, d, a in diff_rows],
                   "tracker_fix_rows": len(fx), "tracker_fix_rows_differing": len(fx ^ GOLD[1]),
                   "chase": ch, "chase_differs": ch != GOLD[2]}
  print(json.dumps({"gold": {"ledger_rows": len(GOLD[0]), "tracker_fix_rows": len(GOLD[1]), "chase": GOLD[2]}, "variants": out}, indent=1))
