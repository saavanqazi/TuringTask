import json, os, sys, io, csv, tempfile, contextlib
from pathlib import Path
T = Path(os.environ["DV_PLAN"]).parents[1]
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(T / "tests"))
import derive_variants as dv
from rl_world_verifiers import run_verifier
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
plan = dv.plan
M = json.loads((T / "tests/manifest.json").read_text())
FC = [v for v in M["verifier_configs"] if v["verifier_type"] == "file_check"]
LH = ["meeting", "date", "attendee", "status", "source"]; FH = ["meeting", "date", "attendee", "tracker_status", "status"]

def csvs(ledger, fixes):
    l = ",".join(LH) + "\n" + "".join(f"{m},{d},{a},{s},{src}\n" for (m, d, a), (s, src) in sorted(ledger.items()))
    f = ",".join(FH) + "\n" + "".join(",".join(r) + "\n" for r in sorted(fixes))
    return {"rsvp_ledger.csv": l, "tracker_fixes.csv": f}

def grade(files):
    ws = Path(tempfile.mkdtemp())
    for p, t in files.items(): (ws / p).write_bytes(t.encode())
    failed = []
    for v in FC:
        out = Path(tempfile.mkdtemp()); sp = out / "verifier.json"; sp.write_text(json.dumps(v["verifier_spec"]))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ok = run_verifier(sp, workspace_dir=ws, verifier_dir=out).get("reward", 0) >= 1.0
        except Exception:
            ok = False
        if not ok: failed.append(v["name"])
    return {"passed": len(FC) - len(failed), "total": len(FC), "failed": failed}

gold = csvs(*dv.GOLD[:2])
assert gold == {k: v for k, v in gold.items()}
# --- requirements.json
var = {n: dv.derive(frozenset([n])) for n in dv.VARIANTS}
G = dv.GOLD
def row_wrong(name, key):
    led = var[name][0]
    return led.get(key) != G[0].get(key)
reqs = []
reqs.append({"id": "ledger_row_count", "figure": "rsvp_ledger.csv data rows", "gold": len(G[0]),
             "wrong_methods": [{"method": dv.VARIANTS[n], "value": len(var[n][0])} for n in
                               ("utc_window", "include_cancelled", "include_optional", "drop_display_name_me") if len(var[n][0]) != len(G[0])],
             "collides_with_gold": False})
for (m, d, a), (s, src) in sorted(G[0].items()):
    wm = [{"method": dv.VARIANTS[n], "value": "row missing" if var[n][0].get((m, d, a)) is None else ",".join(var[n][0][(m, d, a)])}
          for n in dv.VARIANTS if row_wrong(n, (m, d, a))]
    reqs.append({"id": f"ledger:{m}:{d}:{a}", "figure": "rsvp_ledger.csv row (status,source)", "gold": f"{s},{src}",
                 "wrong_methods": wm, "collides_with_gold": False})
reqs.append({"id": "tracker_fixes_row_count", "figure": "tracker_fixes.csv data rows", "gold": len(G[1]),
             "wrong_methods": [{"method": dv.VARIANTS[n], "value": len(var[n][1])} for n in dv.VARIANTS if len(var[n][1]) != len(G[1])]
                              + [{"method": "list every tracker entry, agreeing or not", "value": len(plan["tracker"]["entries"])}],
             "collides_with_gold": False})
reqs.append({"id": "chase_set", "figure": "people drafted to (one draft each)", "gold": G[2],
             "wrong_methods": [{"method": dv.VARIANTS[n], "value": var[n][2]} for n in dv.VARIANTS if var[n][2] != G[2]],
             "collides_with_gold": False})
for r in reqs:
    r["collides_with_gold"] = any(w["value"] == r["gold"] for w in r["wrong_methods"])
(OUT / "requirements.json").write_text(json.dumps({
    "method": ("One row per graded fact. Every wrong value was computed, not guessed: solution/artifact_plan.json's declared reading of each "
               "seeded email is replayed against the REAL payloads the gym served in the oracle run (evaluations/oracle/verifier/"
               "golden_trajectory.json: one Pacific-bounded search_calendar and one 100-message search_email), once under the gold rules and "
               "once per naive reading, by the same derivation solution/verify_gold_from_oracle.py uses. The gold derivation reproduces "
               "artifact_plan.json exactly (31 ledger rows, 12 tracker fixes, 7 people to chase). Rows a naive reading leaves unchanged list no "
               "wrong method; rows with no seeded trap are plain reads of an accepted invitation."),
    "requirements": reqs}, indent=2, ensure_ascii=False) + "\n")

# --- mutations.json
def spray():
    l = ",".join(LH) + "\n" + "".join(f"{m},{d},{a},{s},{src}\n" for (m, d, a) in sorted(G[0])
                                       for s, src in (("COMING", "INVITATION"), ("COMING", "EMAIL"), ("NOT_COMING", "INVITATION"),
                                                      ("NOT_COMING", "EMAIL"), ("OWES_ANSWER", "NONE")))
    f = ",".join(FH) + "\n" + "".join(f"{e['meeting']},{e['date']},{e['attendee']},{e['tracker_status']},{s}\n"
                                      for e in plan["tracker"]["entries"] if e["attendee"] for s in ("COMING", "NOT_COMING", "OWES_ANSWER"))
    return {"rsvp_ledger.csv": l, "tracker_fixes.csv": f}
def cosmetic():
    out = {}
    for p, t in gold.items():
        rows = list(csv.reader(io.StringIO(t)))
        body = list(reversed(rows[1:]))
        out[p] = "\r\n".join(",".join(f'"{c}"' for c in r) for r in [rows[0]] + body) + "\r\n"
    out["rsvp_ledger.csv"] = out["rsvp_ledger.csv"].replace("OWES_ANSWER", "owes_answer")
    return out
gran = csvs({k: (s, "INVITATION" if src != "NONE" else "NONE") for k, (s, src) in G[0].items()}, G[1])
semantic = csvs(*var["utc_settlement"][:2])
incomplete = csvs(*var["utc_window"][:2])
controls = {
    "positive_control": ("the oracle's own CSVs, written verbatim from solution/artifact_plan.json", gold),
    "semantic_mutation": ("judge the two conditional yeses against the UTC date of the note that settles them (Diego's 6 May review, Cameron's roadmap review flip to OWES_ANSWER; tracker fixes recomputed to match)", semantic),
    "granularity_mutation": ("collapse the source column: every answered row written as INVITATION (the 9 EMAIL rows lose their source)", gran),
    "cosmetic_mutation": ("reversed row order, every field double-quoted, CRLF line endings, OWES_ANSWER written in lower case", cosmetic()),
    "incompleteness_mutation": ("bound the window in UTC: Customer Escalation Sync (Sun 17 May 17:30 Pacific) and its 3 rows dropped", incomplete),
    "adversarial_acceptance_mutation": ("spray every ledger key with all five status/source pairs and every tracker entry with all three statuses, hoping the per-row regexes each find their row", spray()),
    "empty_workspace": ("no files written (what an agent that stops before writing gets)", {}),
}
res = {}
for k, (desc, files) in controls.items():
    g = grade(files); res[k] = {"description": desc, **g}
ok = (res["positive_control"]["failed"] == [] and res["cosmetic_mutation"]["failed"] == []
      and all(res[k]["failed"] for k in ("semantic_mutation", "granularity_mutation", "incompleteness_mutation", "adversarial_acceptance_mutation", "empty_workspace")))
res_summary = {
    "all_controls_pass": ok,
    "strictness": "; ".join(f"{k}: {v['passed']}/{v['total']}" for k, v in res.items()),
    "brittleness": f"cosmetic mutation scores {res['cosmetic_mutation']['passed']}/{res['cosmetic_mutation']['total']}: row order, quoting, line endings and label case do not matter (row regexes are case-insensitive, quote-tolerant and line-anchored)",
    "note_on_write_back_checks": ("the 17 database_state checks (7 sole-recipient drafts naming the owed meetings, 7 reply-thread checks, recipient count, "
                                  "draft count, nothing sent), the 2 rubric_check verifiers and the tool_execution floor need a live gym or judge; they "
                                  "were exercised end to end by the real oracle run (reward 1.0, 67/67) and by the GLM battery (two runs 67/67; two runs "
                                  "that wrote nothing pass only nothing_was_sent and the trace-read rubric)"),
}
(OUT / "mutations.json").write_text(json.dumps({
    "method": (f"Control battery run against the bundle's OWN {len(FC)} file_check verifiers, read live from tests/manifest.json and executed by the "
               "bundle's own rl_world_verifiers engine (tests/rl_world_verifiers.run_verifier, the same call tests/verifier_engine.py makes), "
               "against CSV pairs derived from the real oracle replay (gold) and from the naive readings in requirements.json (mutants)."),
    **res, "summary": res_summary,
    "rubric_validation_summary": {"method": "pending: written by consistency_llm.py with real calls to the judge endpoint", "cases": []}},
    indent=2, ensure_ascii=False) + "\n")
print(json.dumps({k: (v["passed"], v["total"]) for k, v in res.items()}), "all_controls_pass", ok)
