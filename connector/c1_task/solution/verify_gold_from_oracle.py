#!/usr/bin/env python3
"""Re-verify the === GOLD === block THROUGH THE SERVED GYM, from the oracle replay's own records.

The interpretation of each seeded email (which meeting it is about, and whether it is a yes, a no or a maybe)
is declared in artifact_plan.json under email_answers; this script checks every declared email is really
served, from that sender, with that wording, and then recomputes everything else from the payloads.

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


def main():
    traj = json.loads(Path(sys.argv[1]).read_text())
    plan_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("artifact_plan.json")
    plan = json.loads(plan_path.read_text())
    gold, me = plan["gold"], plan["acting_user_email"]
    bad = {}
    events = payload_of([s for s in traj if s.get("name") == "search_calendar"][0])["value"]
    run = [e for e in events if e.get("isOrganizer") and not e.get("isCancelled")]
    # the move the plan declares must be what the served calendar shows
    # moves are keyed by event id: two meetings share the subject Weekly Pipeline Review
    moved = {}
    for mv in plan.get("moves", []):
        ev = next((e for e in run if e["subject"] == mv["meeting"]
                   and e["start"]["dateTime"].startswith(mv.get("start", ""))), None)
        note = json.dumps((ev or {}).get("body") or {}) + json.dumps((ev or {}).get("bodyPreview") or "")
        if ev is None or mv["note"] not in note or not str(ev.get("lastModifiedDateTime", "")).startswith(mv["moved_at"][:13]):
            print(f"MISMATCH move of {mv['meeting']} not served as declared", file=sys.stderr); bad["move"] = True
            continue
        moved[ev["id"]] = mv["moved_at"]
    # what the invitations say: not responded / tentative, or a firm answer given before a move
    pending = set()
    for e in run:
        for a in e.get("attendees", []):
            addr = a["emailAddress"]["address"].lower()
            if addr == me or a.get("type") != "required":
                continue
            resp, when = a["status"]["response"], a["status"].get("time") or ""
            # both sides are UTC ("...Z"), so a string comparison orders them correctly
            stale = e["id"] in moved and resp in ("accepted", "declined") and when < moved[e["id"]]
            if resp in ("notResponded", "tentativelyAccepted") or stale:
                pending.add((e["subject"], e["start"]["dateTime"], addr))
    # every message the replay's per-person searches returned, by sender
    mail = defaultdict(list)
    for s in traj:
        if s.get("name") == "search_email":
            for m in payload_of(s).get("value", []):
                sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "").lower()
                if all(m.get("id") != x.get("id") for x in mail[sender]):
                    mail[sender].append(m)
    by_id = {m["id"]: m for ms in mail.values() for m in ms}
    # the email answers the plan declares must be really there, from that sender, with that wording;
    # per (person, meeting) only the latest counts, and not if it predates a move of that meeting
    latest_answer = {}
    for ans in plan["email_answers"]:
        m = by_id.get(ans["message_id"])
        text = json.dumps(m or {}).lower().replace("\\u2019", "'")
        if m is None or ans["from"] not in json.dumps(m.get("from") or {}).lower() or ans["quote"].lower() not in text:
            print(f"MISMATCH email answer {ans['message_id']} not served as declared", file=sys.stderr); bad["email"] = True
            continue
        key = (ans["from"], ans["meeting"])
        if key not in latest_answer or m["receivedDateTime"] > latest_answer[key][0]:
            latest_answer[key] = (m["receivedDateTime"], ans["answer"])
    moved_by_subject = {e["subject"]: moved[e["id"]] for e in run if e["id"] in moved}
    for (who, meeting), (when, answer) in latest_answer.items():
        if meeting in moved_by_subject and when < moved_by_subject[meeting]:
            continue
        if answer in ("yes", "no"):
            pending = {p for p in pending if not (p[0] == meeting and p[2] == who)}
    owed_meetings = {(p[0], p[1]) for p in pending}
    chase = sorted({p[2] for p in pending})
    got = {"meetings_i_am_running": len(run), "meetings_still_owed_an_answer": len(owed_meetings),
           "people_to_chase": len(chase), "answers_still_owed": len(pending),
           "people_to_chase_who_already_emailed_me": len([a for a in chase if mail.get(a)])}
    for k, v in got.items():
        if gold[k] != v:
            print(f"MISMATCH {k}: replay says {v}, gold says {gold[k]}", file=sys.stderr); bad[k] = True
    if chase != sorted(plan["write_back"]["chase"]):
        print(f"MISMATCH chase set {chase}", file=sys.stderr); bad["chase"] = True
    latest = {a: max(mail[a], key=lambda m: m.get("receivedDateTime") or "") for a in chase if mail.get(a)}
    for a, m in latest.items():
        if plan["write_back"]["reply_on"].get(a) != m["id"]:
            print(f"MISMATCH latest email of {a} is {m['id']}", file=sys.stderr); bad["latest"] = True
    drafts = [s for s in traj if s.get("name") == "draft_email"]
    if len(drafts) != len(chase):
        print("MISMATCH draft count", file=sys.stderr); bad["drafts"] = True
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
            print(f"MISMATCH draft {rcpts}: must go to one person, name their meeting and sit on their latest email", file=sys.stderr); bad["draft_content"] = True
        else:
            covered.add(rcpts[0])
    if covered != set(chase):
        print(f"MISMATCH drafted people {sorted(covered)}", file=sys.stderr); bad["draft_people"] = True
    if bad:
        raise SystemExit(1)
    print("OK: organised meetings, answers from invitations and email, the chase set, who already emailed and the reply threads re-derived from the served gym")


if __name__ == "__main__":
    main()
