"""consistency_llm.py - the LLM-backed consistency evidence, run on the trainer's machine with the project judge endpoint.

Writes into <task>/consistency/:
  readers.json   - four readers given ONLY instruction.md report goal / population / decision rule / deliverables;
  envelope.json  - three differently-instructed writers turn the findings (prose, never a ready CSV) into the two CSVs,
                   each rendering scored by the bundle's OWN file_check verifiers through tests/rl_world_verifiers;
  mutations.json - fills rubric_validation_summary: each rubric_check run against gold and adversarial evidence with the
                   engine's own _judge_rubric system prompt (read from tests/verifier_engine.py), 3 votes, majority.

Needs OPENAI_API_KEY, OPENAI_BASE_URL and JUDGE_MODEL (harbor-env.cmd sets them) and pydantic, jsonpath-ng, tenacity.
    python consistency_llm.py <task dir> <one passing GLM trial dir>
"""
import ast, contextlib, io, json, os, re, sys, tempfile, urllib.request, hashlib
from pathlib import Path

TASK, TRIAL = Path(sys.argv[1]), Path(sys.argv[2])
CONS = TASK / "consistency"
INSTR = (TASK / "instruction.md").read_text(encoding="utf-8")
PLAN = json.loads((TASK / "solution/artifact_plan.json").read_text(encoding="utf-8"))
MAN = json.loads((TASK / "tests/manifest.json").read_text(encoding="utf-8"))
MODEL = os.environ["JUDGE_MODEL"].split("/", 1)[1] if os.environ["JUDGE_MODEL"].startswith("openai/") else os.environ["JUDGE_MODEL"]
URL = os.environ["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions"
KEY = os.environ["OPENAI_API_KEY"]


def chat(system, user, temperature, max_tokens=12000):
    body = json.dumps({"model": MODEL, "temperature": temperature, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=600) as r:
                msg = json.loads(r.read())["choices"][0]["message"]
            text = msg.get("content") or ""
            if text.strip():
                return text
        except Exception as e:
            print("  retry after", type(e).__name__, file=sys.stderr)
    raise SystemExit("judge endpoint gave no usable answer")


def first_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    s = text.find("{")
    dec = json.JSONDecoder()
    while s != -1:
        try:
            return dec.raw_decode(text[s:])[0]
        except ValueError:
            s = text.find("{", s + 1)
    return None


# ---------------------------------------------------------------- readers
PERSONAS = {
    "new executive assistant on their first day": 0.7,
    "QA engineer who reads every sentence literally": 0.7,
    "busy project manager skimming before a meeting": 0.7,
    "data analyst who will have to build the CSV files": 0.7,
}
READ_SYS = "You read task requests carefully and report exactly what they ask for. You have no access to any data."
READ_USER = ("You are a {p}. Read the request below - it is all you have; you cannot see the calendar, the mailbox or any "
             "answer key. Reply with ONLY a JSON object with these keys:\n"
             '"goal": one or two sentences;\n"population": exactly which meetings and which people the ledger covers;\n'
             '"decision_rule": how to decide each person\'s status and source;\n"deliverables": every file and every write-back asked for;\n'
             '"ambiguities": a list of anything you could read two ways (empty list if none);\n'
             '"unstated_requirements": a list of anything you think would be graded but is not written down (empty list if none).\n\n'
             "REQUEST:\n{instr}")
readings = []
for p, temp in PERSONAS.items():
    print("reader:", p)
    j = first_json(chat(READ_SYS, READ_USER.format(p=p, instr=INSTR), temp)) or {}
    j["reader"] = p
    readings.append(j)
def has(j, *words):
    t = json.dumps(j).lower()
    return all(w.lower() in t for w in words)
checks = {
    "population: organised, window 27 April-17 May, cancelled excluded, required attendees other than him, by address":
        [has(r.get("population", ""), "organi", "27 april", "17 may", "cancel", "required") for r in readings],
    "deliverables: rsvp_ledger.csv, tracker_fixes.csv, drafts (not sent)":
        [has(r.get("deliverables", ""), "rsvp_ledger.csv", "tracker_fixes.csv", "draft") for r in readings],
    "decision rule: latest answer on either channel, moves, conditional, relayed":
        [has(r.get("decision_rule", ""), "last", "moved", "depend") for r in readings],
}
(CONS / "readers.json").write_text(json.dumps({
    "method": (f"Four readers, each given ONLY instruction.md (no corpus, gold or verifiers), asked in one shot for goal, population, "
               f"decision rule, deliverables, ambiguities and unstated requirements. Model {os.environ['JUDGE_MODEL']} through the project "
               f"judge endpoint, temperature 0.7, four personas. Run against the shipped instruction.md."),
    "instruction_sha256": hashlib.sha256((TASK / "instruction.md").read_bytes()).hexdigest(),
    "readings": readings,
    "result": {
        "keyword_agreement": {k: f"{sum(v)}/{len(v)}" for k, v in checks.items()},
        "residual_ambiguities": [{"reader": r["reader"], "item": a} for r in readings for a in (r.get("ambiguities") or [])],
        "unstated_requirements_flagged_by_readers": [{"reader": r["reader"], "item": a} for r in readings for a in (r.get("unstated_requirements") or [])],
        "note": "keyword_agreement is a mechanical check of each reading; residual items are quoted verbatim for the reviewer to judge.",
    }}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# ---------------------------------------------------------------- envelope
sys.path.insert(0, str(TASK / "tests"))
from rl_world_verifiers import run_verifier
FC = [v for v in MAN["verifier_configs"] if v["verifier_type"] == "file_check"]
def grade(files):
    ws = Path(tempfile.mkdtemp())
    for p, t in files.items():
        (ws / p).write_bytes(t.encode("utf-8"))
    failed = []
    for v in FC:
        out = Path(tempfile.mkdtemp()); sp = out / "verifier.json"; sp.write_text(json.dumps(v["verifier_spec"]))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ok = run_verifier(sp, workspace_dir=ws, verifier_dir=out).get("reward", 0) >= 1.0
        except Exception:
            ok = False
        if not ok:
            failed.append(v["name"])
    return failed
WORD = {"COMING": "is coming", "NOT_COMING": "is not coming", "OWES_ANSWER": "still owes an answer"}
SRC = {"INVITATION": "going by their answer on the invitation", "EMAIL": "going by their email", "NONE": "with no answer that counts"}
prose = ["Findings for each meeting he runs (meeting subject exactly as on the calendar, Pacific start date):"]
for r in PLAN["ledger"]:
    prose.append(f"- On {r['meeting']} starting {r['date']}, {r['attendee']} {WORD[r['status']]}, {SRC[r['source']]}.")
prose.append("Janice's tracker entries that disagree with the findings:")
for r in PLAN["tracker_fixes"]:
    prose.append(f"- For {r['meeting']} on {r['date']}, she has {r['attendee']} as {r['tracker_status']}, but they {WORD[r['status']]}.")
spec = INSTR[INSTR.index("Write /workspace/rsvp_ledger.csv"):INSTR.index("Then draft a note")]
WRITERS = {"V1 terse": 0.2, "V2 verbose": 0.9, "V3 report-style": 0.6}
STYLE = {"V1 terse": "Be terse.", "V2 verbose": "Explain briefly what you did before the files.",
         "V3 report-style": "Write a short report heading, then the files."}
renderings = []
for name, temp in WRITERS.items():
    print("writer:", name)
    text = chat("You turn findings into the files a request asks for.",
                f"{STYLE[name]} Using the findings below, produce the two files the specification asks for. Give each file in its own "
                f"fenced code block whose first line is the file's header.\n\nSPECIFICATION:\n{spec}\nFINDINGS:\n" + "\n".join(prose),
                temp, max_tokens=16000)
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
    files = {}
    for b in blocks:
        if b.startswith("meeting,date,attendee,status,source"):
            files["rsvp_ledger.csv"] = b
        elif b.startswith("meeting,date,attendee,tracker_status,status"):
            files["tracker_fixes.csv"] = b
    failed = grade(files)
    renderings.append({"rendering": name, "temperature": temp,
                       "csv_first_two_lines": "\n".join(files.get("rsvp_ledger.csv", "").splitlines()[:2]),
                       "verifiers_passed": len(FC) - len(failed), "verifiers_total": len(FC), "failed": failed})
(CONS / "envelope.json").write_text(json.dumps({
    "method": (f"Three renderings of the SAME findings (31 ledger rows, 12 tracker fixes) by three differently-instructed writers "
               f"(terse / verbose / report-style, temperatures 0.2 / 0.9 / 0.6), model {os.environ['JUDGE_MODEL']} through the project judge "
               f"endpoint, given the findings in prose plus the instruction's own file specification - never a ready-made CSV. Each "
               f"rendering is scored by the bundle's OWN {len(FC)} file_check verifiers (tests/manifest.json) through tests/rl_world_verifiers."),
    "renderings": renderings,
    "result": {"renderings": len(renderings), "all_score_full": all(not r["failed"] for r in renderings),
               "per_rendering": [f"{r['rendering']}: {r['verifiers_passed']}/{r['verifiers_total']}" for r in renderings]}},
    indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# ---------------------------------------------------------------- rubric validation
src = (TASK / "tests/verifier_engine.py").read_text(encoding="utf-8")
SYSTEM = None
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "_judge_rubric":
        for n in ast.walk(node):
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "system_prompt":
                SYSTEM = ast.literal_eval(n.value)
assert SYSTEM, "could not read _judge_rubric's system prompt"
def clip(value, limit):
    text = json.dumps(value, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    head = limit // 3
    return text[:head] + f"… [{len(text) - limit} chars clipped] …" + text[-(limit - head):]
def trace_calls(path):
    t = json.loads(path.read_text(encoding="utf-8"))
    calls = []
    for s in t.get("steps", []):
        res = (s.get("observation") or {}).get("results") or []
        for i, tc in enumerate(s.get("tool_calls") or []):
            name = tc.get("function_name", "")
            if "outlook-gym" not in name:
                continue
            r = res[i] if len(res) == len(s["tool_calls"]) else {}
            calls.append({"name": name.split("_", 1)[1] if name.startswith("outlook-gym_") else name,
                          "args": tc.get("arguments"), "tool_execution_results": r.get("content"), "ok": True})
    return calls
def trace_evidence(calls):
    per = max(200, min(4000, 200000 // max(1, len(calls))))
    return json.dumps([{"name": c["name"], "args": c["args"], "accepted_by_gym": c["ok"],
                        **({"result": clip(c["tool_execution_results"], per)} if c["tool_execution_results"] else {})} for c in calls], indent=2)
def judge(rubric, label, evidence):
    user = f"Rubric (atomic — judge on its own):\n{rubric}\n\n{label}:\n{evidence}\n\nReturn your verdict as JSON."
    votes, why = [], ""
    for _ in range(3):
        j = first_json(chat(SYSTEM, user, 0.0, max_tokens=8000)) or {}
        votes.append(str(j.get("verdict", "")).upper()); why = why or j.get("motivation", "")
    return ("PASS" if votes.count("PASS") >= 2 else "FAIL"), why, votes
RUB = {v["name"]: v for v in MAN["verifier_configs"] if v["verifier_type"] == "rubric_check"}
calls = trace_calls(TRIAL / "agent/trajectory.json")
TL = ("Tool-call trace (each entry is one call the agent made and the result it received back, clipped to a per-call budget; a "
      "missing 'result' means the call returned nothing) — accepted_by_gym=false means the gym REJECTED the call and nothing "
      "changed; such a call proves nothing")
cases = [
    ("calendar_and_mailbox_were_read", "gold_passing_glm_trace", "expected_pass", TL, trace_evidence(calls)),
    ("calendar_and_mailbox_were_read", "adversarial_mailbox_never_read", "expected_fail", TL,
     trace_evidence([c for c in calls if "search_email" not in c["name"]])),
    ("calendar_and_mailbox_were_read", "adversarial_calendar_never_read", "expected_fail", TL,
     trace_evidence([c for c in calls if "search_calendar" not in c["name"]])),
    ("final_reply_states_who_owes_what", "gold_final_answer", "expected_pass", "AI assistant final answer",
     (TASK / "solution/final_answer.md").read_text(encoding="utf-8")),
    ("final_reply_states_who_owes_what", "adversarial_steps_only", "expected_fail", "AI assistant final answer",
     "I searched the calendar and the mailbox, wrote rsvp_ledger.csv and tracker_fixes.csv, and created the drafts."),
    ("final_reply_states_who_owes_what", "adversarial_empty", "expected_fail", "AI assistant final answer", ""),
]
out = []
for check, case, expect, label, ev in cases:
    print("rubric:", check, case)
    verdict, why, votes = judge(RUB[check]["rubric"], label, ev)
    out.append({"check": check, "case": case, "expectation": expect, "verdict": verdict, "votes": votes, "motivation": why,
                "as_expected": (verdict == "PASS") == (expect == "expected_pass")})
m = json.loads((CONS / "mutations.json").read_text(encoding="utf-8"))
m["rubric_validation_summary"] = {
    "method": (f"Real calls to the judge endpoint ({os.environ['JUDGE_MODEL']}, temperature 0.0, 3 votes, majority) with "
               f"tests/verifier_engine.py's _judge_rubric system prompt read from the file, each rubric_check's own rubric read from "
               f"tests/manifest.json, and gold or adversarial evidence (the trace of passing GLM trial {TRIAL.name}, the same trace with "
               f"one source's calls removed, solution/final_answer.md, a steps-only reply, an empty reply)."),
    "cases": out, "all_as_expected": all(c["as_expected"] for c in out)}
(CONS / "mutations.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("readers:", {k: f"{sum(v)}/{len(v)}" for k, v in checks.items()})
print("envelope:", [f"{r['rendering']}: {r['verifiers_passed']}/{r['verifiers_total']}" for r in renderings])
print("rubric cases as expected:", sum(c["as_expected"] for c in out), "/", len(out))
