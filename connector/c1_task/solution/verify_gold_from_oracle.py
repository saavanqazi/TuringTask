#!/usr/bin/env python3
"""Re-verify the === GOLD === block THROUGH THE SERVED GYM, from the oracle replay's own records.

The interpretation of each seeded email (which meeting it is about, and whether it is a yes, a no, a maybe or a
yes on a condition) and of each entry in Janice Gray's tracker is declared in artifact_plan.json; this script
checks every declared email and tracker entry is really served, from that sender, with that wording, and then
recomputes the ledger, the tracker fixes, the chase set and the reply threads from the payloads.

TASK_GEN section 3: gold is computed from the snapshot and then re-verified through the gym, and
where the two disagree the gym wins. solve.py --write-back records every tool result under
tool_execution_results, and harbor pulls the written-back file to
<trial>/verifier/golden_trajectory.json. This script recomputes the graded figures from THOSE
payloads alone - nothing is read from SQL - and exits 1 if anything differs from
solution/artifact_plan.json.

    python3 solution/verify_gold_from_oracle.py <path to replayed golden_trajectory.json> [artifact_plan.json]

It is a post-run check, not part of solve.sh, and it is deliberately agnostic about the MCP
envelope: it deep-parses every JSON-encoded string exactly as solve.py's extract_payload does.
"""
import json, sys
from collections import defaultdict
from pathlib import Path


def parse_json_strings(v, depth=0):
    if depth > 12:
        return v
    if isinstance(v, str):
        s = v.strip()
        if s and s[0] in "{[\"":
            try:
                p = json.loads(s)
            except Exception:
                return v
            return parse_json_strings(p, depth + 1) if isinstance(p, (dict, list)) else p
        return v
    if isinstance(v, list):
        return [parse_json_strings(x, depth + 1) for x in v]
    if isinstance(v, dict):
        return {k: parse_json_strings(x, depth + 1) for k, x in v.items()}
    return v


def payload_of(step):
    ter = step.get("tool_execution_results") or {}
    res = ter.get("result")
    if res is None:
        raise SystemExit(f"step {step.get('id')} has no recorded result - was the replay run with --write-back?")
    res = parse_json_strings(res)
    if isinstance(res, dict) and isinstance(res.get("content"), list) and res["content"]:
        first = res["content"][0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
    return res


def steps_by_prefix(traj, prefix):
    return [s for s in traj if str(s.get("id", "")).startswith(prefix)]


def norm_ts(t):
    return str(t or "").replace(" ", "T")[:19]


def main():
    traj = json.loads(Path(sys.argv[1]).read_text())
    plan_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("artifact_plan.json")
    plan = json.loads(plan_path.read_text())
    me = plan["acting_user_email"]
    lo, hi = plan["window"]
    bad = {}

    def mismatch(key, msg):
        print(f"MISMATCH {msg}", file=sys.stderr)
        bad[key] = True

    events = payload_of([s for s in traj if s.get("name") == "search_calendar"][0])["value"]
    mine = [e for e in events if e.get("isOrganizer") and lo <= e["start"]["dateTime"][:10] <= hi]
    run = [e for e in mine if not e.get("isCancelled")]
    # the cancelled meeting must be cancelled if the gym serves it at all
    cab = plan["cancelled"]
    for e in mine:
        if e["subject"] == cab["meeting"] and not e.get("isCancelled"):
            mismatch("cancelled", f"{cab['meeting']} is served as not cancelled")
    key_of = {e["id"]: (e["subject"], e["start"]["dateTime"][:10]) for e in run}
    # moves are keyed by subject AND start date: two meetings share the subject Weekly Pipeline Review
    moved = {}
    for mv in plan["moves"]:
        ev = next((e for e in run if (e["subject"], e["start"]["dateTime"][:10]) == (mv["meeting"], mv["start"])), None)
        note = json.dumps((ev or {}).get("body") or {}) + json.dumps((ev or {}).get("bodyPreview") or "")
        if ev is None or mv["note"] not in note or not str(ev.get("lastModifiedDateTime", "")).startswith(mv["moved_at"][:13]):
            mismatch("move", f"move of {mv['meeting']} {mv['start']} not served as declared")
            continue
        moved[key_of[ev["id"]]] = norm_ts(mv["moved_at"])
    # every answer, keyed (meeting, date, address): (time, kind, source)
    INV = {"accepted": "yes", "declined": "no", "tentativelyAccepted": "maybe"}
    answers, people = defaultdict(list), set()
    for e in run:
        for a in e.get("attendees", []):
            addr = a["emailAddress"]["address"].lower()
            if addr == me or a.get("type") != "required":
                continue
            k = key_of[e["id"]] + (addr,)
            people.add(k)
            resp = a["status"]["response"]
            if resp in INV:
                answers[k].append((norm_ts(a["status"].get("time")), INV[resp], "INVITATION"))
    # the whole mailbox the replay read
    mail = {}
    for s in traj:
        if s.get("name") == "search_email":
            for m in payload_of(s).get("value", []):
                mail[m["id"]] = m
    sender = lambda m: (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
    text_of = lambda m: json.dumps(m).lower().replace("\\u2019", "'")
    for ans in plan["email_answers"]:
        m = mail.get(ans["message_id"])
        if m is None or sender(m) != ans["from"] or ans["quote"].lower() not in text_of(m):
            mismatch("email", f"email answer {ans['message_id']} not served as declared")
            continue
        k = (ans["meeting"], ans["date"], ans["from"])
        if k not in people:
            mismatch("email", f"email answer {ans['message_id']} is about {k}, which is not a ledger row")
        answers[k].append((norm_ts(m["receivedDateTime"]), ans["answer"], "EMAIL"))
    for rel in plan["relayed"]:
        m = mail.get(rel["message_id"])
        if m is None or sender(m) != rel["from"] or sender(m) == rel["for"] or rel["quote"].lower() not in text_of(m):
            mismatch("relayed", f"relayed note {rel['message_id']} not served as declared")
    # where each person stands: drop answers that predate a move, then the latest wins
    ledger = {}
    for k in people:
        live = [x for x in answers[k] if not (k[:2] in moved and x[0] < moved[k[:2]])]
        if not live:
            ledger[k] = ("OWES_ANSWER", "NONE")
            continue
        times = sorted(x[0] for x in live)
        if len(times) > 1 and times[-1] == times[-2]:
            mismatch("tie", f"two answers at the same time for {k}")
        when, kind, src = max(live)
        ledger[k] = {"yes": ("COMING", src), "no": ("NOT_COMING", src)}.get(kind, ("OWES_ANSWER", "NONE"))
    want = {(r["meeting"], r["date"], r["attendee"]): (r["status"], r["source"]) for r in plan["ledger"]}
    if ledger != want:
        for k in sorted(set(ledger) | set(want)):
            if ledger.get(k) != want.get(k):
                mismatch("ledger", f"ledger row {k}: replay says {ledger.get(k)}, plan says {want.get(k)}")
    # Janice's tracker
    tr = plan["tracker"]
    m = mail.get(tr["message_id"])
    fixes = set()
    if m is None or sender(m) != tr["from"]:
        mismatch("tracker", "Janice's tracker not served")
    else:
        lines = [l.strip() for l in ((m.get("body") or {}).get("content") or "").replace("<br>", "\n").replace("<p>", "\n").replace("</p>", "\n").splitlines()]
        for en in tr["entries"]:
            line = next((l for l in lines if l.startswith(en["line"])), None)
            if line is None or en["says"] not in line:
                mismatch("tracker", f"tracker entry {en['line']} {en['says']} not served")
                continue
            k = (en["meeting"], en["date"], en["attendee"] or "")
            if k in ledger and ledger[k][0] != en["tracker_status"]:
                fixes.add(k + (en["tracker_status"], ledger[k][0]))
    want_fixes = {(r["meeting"], r["date"], r["attendee"], r["tracker_status"], r["status"]) for r in plan["tracker_fixes"]}
    if fixes != want_fixes:
        mismatch("fixes", f"tracker fixes: replay says {sorted(fixes ^ want_fixes)} differ")
    # write-back
    chase = sorted({k[2] for k, v in ledger.items() if v[0] == "OWES_ANSWER"})
    if chase != sorted(plan["write_back"]["chase"]):
        mismatch("chase", f"chase set {chase}")
    by_sender = defaultdict(list)
    for x in mail.values():
        if not x.get("isDraft"):
            by_sender[sender(x)].append(x)
    latest = {a: max(by_sender[a], key=lambda x: norm_ts(x.get("receivedDateTime"))) for a in chase if by_sender.get(a)}
    for a, x in latest.items():
        if plan["write_back"]["reply_on"].get(a) != x["id"]:
            mismatch("latest", f"latest email of {a} is {x['id']}")
    drafts = [s for s in traj if s.get("name") == "draft_email"]
    if len(drafts) != len(chase):
        mismatch("drafts", "draft count")
    needles = plan["write_back"]["needles"]
    covered = set()
    for s in drafts:
        p = payload_of(s)
        rcpts = sorted({(r.get("emailAddress") or {}).get("address", "").lower() for r in (p.get("toRecipients") or []) + (p.get("ccRecipients") or [])} - {me})
        text = ((p.get("subject") or "") + " " + (p.get("bodyPreview") or "") + " " + json.dumps(p.get("body") or "")).lower()
        ok = len(rcpts) == 1 and rcpts[0] in needles and all(w.lower() in text for w in needles[rcpts[0]])
        if ok and rcpts[0] in latest and p.get("conversationId") != latest[rcpts[0]].get("conversationId"):
            ok = False
        if not ok:
            mismatch("draft_content", f"draft {rcpts}: must go to one person, name their meetings and sit on their latest email")
        else:
            covered.add(rcpts[0])
    if covered != set(chase):
        mismatch("draft_people", f"drafted people {sorted(covered)}")
    if bad:
        raise SystemExit(1)
    print(f"OK: {len(run)} meetings, {len(ledger)} ledger rows, {len(fixes)} tracker fixes, chase set and reply threads re-derived from the served gym")


if __name__ == "__main__":
    main()
