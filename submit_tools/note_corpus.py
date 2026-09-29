import sys, shutil, tempfile, pathlib
T=sys.argv[1]; sys.path.insert(0,T+'/tests')
from rl_world_verifiers.models import VerifierSpec, effective_weights
from rl_world_verifiers.sources.registry import SourceRegistry
from rl_world_verifiers.verifiers import verify_definition
spec=VerifierSpec.model_validate_json(open(T+'/tests/verifier.json').read()); W=effective_weights(spec.verifiers)
NOTE=[v for v in spec.verifiers if v.name.startswith('note_')]
def fails(note):
    d=pathlib.Path(tempfile.mkdtemp()); (d/'takeoff_note.md').write_text(note)
    r=SourceRegistry(d); return sorted(v.name for v in NOTE if not verify_definition(v,r,W[v.name],config=spec.config,completion_fn=None)['result']['success'])
U="\n\nC-10 and C-24 are unresolved.\n"; K="Reducers: 11. Couplers: 3.\n\n"
RC=['note_reducer_count']; CC=['note_coupler_count']; U10=['note_unresolved_C-10']; U24=['note_unresolved_C-24']
cases=[  # (label, note, expected failing checks)
 ("r1 swapped counts","We need 11 couplers and 3 reducers."+U, RC+CC),
 ("r1 zero counts, stray numbers","0 reducers and 0 couplers but 11 and 3 appear here."+U, RC+CC),
 ("r1 C-10 called resolved", K+"C-10 is resolved, C-24 unresolved.\n", U10),
 ("r1 swapped, label first","Couplers: 11. Reducers: 3."+U, RC+CC),
 ("hedged count","Reducers: 11 or 12. Couplers: 3."+U, RC),
 ("C-10 unlisted before C-24", K+"C-10 was measured on site. C-24 is unresolved.\n", U10),
 ("non-unresolved id between", K+"C-10, then C-06; C-24 is unresolved.\n", U10),
 ("count bound to couplers","We need 11 couplers and reducers for the rest. Couplers: 3."+U, RC),
 ("wrong reducer count","Reducers: 10. Couplers: 3."+U, RC),
 ("ids missing", K+"Two runs are unresolved.\n", U10+U24),
 ("id in another paragraph", K+"See C-10 and C-24.\n\nTwo runs are unresolved.\n", U10+U24),
 ("r2 not resolved yet", K+"C-10 is unresolved (not resolved yet). C-24 is unresolved (not resolved yet).\n", []),
 ("r2 cannot be resolved yet", K+"C-10 and C-24 cannot be resolved yet; both are unresolved.\n", []),
 ("r3 24 between both counts","11 of the 24 runs take reducers and 3 of the 24 runs take couplers."+U, []),
 ("r3 of the 24 runs first","Of the 24 runs, 11 take reducers and 3 take couplers."+U, []),
 ("r3 ids between label and count","Reducers (C-06, C-14, C-19): 11 needed. Couplers: 3."+U, []),
 ("r3 soft-wrapped list","We need 11 reducers and 3 couplers.\nC-10\nC-24 are unresolved.\n", []),
 ("bulleted list of ids", K+"Unresolved:\n- C-10\n- C-24\n", []),
 ("ids with parentheticals", K+"C-10 (TK-A to P1-S) and C-24 (TK-D to P6-S) are unresolved.\n", []),
 ("semicolon list", K+"C-10; C-24: unresolved.\n", []),
 ("plain words","Eleven connections need reducers and three need couplers."+U, []),
 ("non-adapter wording","Eleven of the non-adapter connections need reducers, and three need couplers."+U, []),
 ("adapters mentioned between","We need 11 connections fitted with reducers (the thread changes take adapters) and 3 with couplers."+U, []),
 ("bold counts","The register calls for **11 reducer** fittings and **3 coupler** fittings."+U, []),
 ("a further 8 adapters after","11 connections need a reducer and 3 need a coupler; a further 8 take an adapter."+U, []),
 ("reducers are needed on","Reducers are needed on 11 connections, couplers on 3."+U, []),
 ("unresolved first", K+"Two runs remain unresolved: C-10 and C-24.\n", []),
]
for r in ['r1','r2','r3','r4']:
    cases.append((f"shipped difficulty/{r}", open(f"{T}/evaluations/difficulty/{r}/artifacts/app/takeoff_note.md").read(), None))
cases.append(("shipped solvability/r1", open(f"{T}/evaluations/solvability/r1/artifacts/app/takeoff_note.md").read(), []))
bad=0
for label,note,exp in cases:
    got=fails(note)
    if exp is None: print('   ', label, '->', got or 'all note checks pass'); continue
    ok = got==sorted(exp); bad+= not ok
    print('ok ' if ok else 'BAD', label, '->', got, '' if ok else f'(expected {sorted(exp)})')
print('PROBLEMS', bad)
