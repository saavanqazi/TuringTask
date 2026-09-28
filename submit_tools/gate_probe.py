import sys, shutil, tempfile, pathlib, csv, io
T=sys.argv[1]; sys.path.insert(0,T+'/tests')
from rl_world_verifiers.models import VerifierSpec, effective_weights
from rl_world_verifiers.sources.registry import SourceRegistry
from rl_world_verifiers.verifiers import verify_definition
spec=VerifierSpec.model_validate_json(open(T+'/tests/verifier.json').read()); W=effective_weights(spec.verifiers)
G=pathlib.Path(T+'/solution/files')
def grade(note=None, reg=None):
    d=pathlib.Path(tempfile.mkdtemp())
    for f in G.iterdir(): shutil.copy(f,d/f.name)
    if note is not None: (d/'takeoff_note.md').write_text(note)
    if reg is not None: (d/'fitting_register.csv').write_text(reg)
    r=SourceRegistry(d); return [v.name for v in spec.verifiers if not verify_definition(v,r,W[v.name],config=spec.config,completion_fn=None)['result']['success']]
gold_reg=(G/'fitting_register.csv').read_text()
MUST_FAIL={
 "gate: counts swapped": "We need 11 couplers and 3 reducers.\n\nC-10 and C-24 are unresolved.\n",
 "gate: zero counts + stray numbers": "0 reducers and 0 couplers but 11 and 3 appear here.\n\nC-10 and C-24 are unresolved.\n",
 "gate: C-10 called resolved": "Reducers: 11. Couplers: 3.\n\nC-10 is resolved, C-24 unresolved.\n",
 "C-10 resolved, later sentence": "Reducers: 11. Couplers: 3.\n\nUnresolved: C-24. C-10 is resolved.\n",
 "swapped, label first": "Couplers: 11. Reducers: 3.\n\nC-10 and C-24 are unresolved.\n",
 "hedged count": "Reducers: 11 or 12. Couplers: 3.\n\nC-10 and C-24 are unresolved.\n",
}
MUST_PASS={
 "gold": None,
 "plain words": "Eleven connections need reducers and three need couplers.\n\nC-10 and C-24 are unresolved.\n",
 "label first": "Connections needing a reducer: 11. Connections needing a coupler: 3.\n\nUnresolved: C-10, C-24.\n",
 "one sentence both": "We need 11 reducer fittings plus 3 couplers; the rest are adapters.\n\nC-10 and C-24 stay UNRESOLVED until measured.\n",
 "reducers are needed on": "Reducers are needed on 11 connections, couplers on 3.\n\nC-10 is unresolved. C-24 is unresolved too.\n",
 "bullets": "- Reducers: 11\n- Couplers: 3\n\n- C-10: fitting_kind `UNRESOLVED`\n- C-24: fitting_kind `UNRESOLVED`\n",
 "counts in parentheses": "Reducers (11) and couplers (3) are listed in the register.\n\nC-10 and C-24 are unresolved.\n",
}
bad=0
for k,n in MUST_FAIL.items():
    f=grade(note=n); ok=bool(f); bad+=not ok; print('FAIL-case','ok ' if ok else 'BAD',k,f)
for k,n in MUST_PASS.items():
    f=grade(note=n); ok=not f; bad+=not ok; print('PASS-case','ok ' if ok else 'BAD',k,f)
f=grade(reg=gold_reg.lower()); ok=bool(f); bad+=not ok; print('FAIL-case','ok ' if ok else 'BAD','gate: lowercase register',f)
f=grade(reg=gold_reg.replace('RD-114-1-N','rd-114-1-n')); ok=bool(f); bad+=not ok; print('FAIL-case','ok ' if ok else 'BAD','one lowercase fitting_id',f)
f=grade(reg=gold_reg.replace('ADAPTER','Adapter')); ok=bool(f); bad+=not ok; print('FAIL-case','ok ' if ok else 'BAD','mixed-case kind',f)
f=grade(reg='"connection_id","fitting_id","fitting_kind"\n'+gold_reg.split('\n',1)[1]); ok=not f; bad+=not ok; print('PASS-case','ok ' if ok else 'BAD','quoted header',f)
f=grade(reg=gold_reg.replace(',',' , ')); ok=not f; bad+=not ok; print('PASS-case','ok ' if ok else 'BAD','spaces around commas',f)
print('PROBLEMS',bad)
