import json,sys,shutil,tempfile,pathlib,os
T=sys.argv[1]; sys.path.insert(0,T+'/tests')
from rl_world_verifiers.models import VerifierSpec, effective_weights
from rl_world_verifiers.sources.registry import SourceRegistry
from rl_world_verifiers.verifiers import verify_definition
spec=VerifierSpec.model_validate_json(open(T+'/tests/verifier.json').read()); W=effective_weights(spec.verifiers)
def grade(note):
    d=pathlib.Path(tempfile.mkdtemp()); 
    for f in ('fitting_register.csv','results.json'): shutil.copy(T+'/solution/files/'+f,d/f)
    (d/'takeoff_note.md').write_bytes(note.encode())
    reg=SourceRegistry(d); fails=[]
    for v in spec.verifiers:
        if not verify_definition(v,reg,W[v.name],config=spec.config,completion_fn=None)['result']['success']: fails.append(v.name)
    return fails
PASS={
'gold': open(T+'/solution/files/takeoff_note.md').read(),
'plain': "Nine connections need reducers and two need couplers.\n\nC-03 is unresolved: the pump maker gives no suction size.\n",
'reverse+digits': "Reducers needed: 9. Couplers needed: 2.\n\nThe run C-03 stays UNRESOLVED until the port is measured.\n",
'unresolved first': "We need 9 reducer fittings, plus 2 couplers.\n\nUnresolved for now: C-03, pending a measurement of the suction port.\n",
'crlf+bom': "﻿Reducers: 9.\r\nCouplers: 2.\r\n\r\nC-03 is unresolved.\r\n",
'bullets': "- reducer count: 9\n- coupler count: 2\n\n- C-03 (fitting_kind `UNRESOLVED`)\n",
'9.0': "There are 9.0 reducer connections. Couplers: 2.\n\nC-03: unresolved.\n",
}
FAIL={
'wrong reducer 8': "Eight connections need reducers and two need couplers.\n\nC-03 is unresolved.\n",
'wrong coupler 3': "Nine reducers. 3 couplers.\n\nC-03 is unresolved.\n",
'reducer num other sentence': "We need reducers. The total is 9. Two couplers.\n\nC-03 is unresolved.\n",
'no unresolved id': "Nine reducers, two couplers.\n\nOne connection is unresolved.\n",
'id other paragraph': "Nine reducers, two couplers. C-03 is odd.\n\nOne connection is unresolved.\n",
'other id between': "Nine reducers, two couplers.\n\nC-03 and C-05 are listed; C-05 is unresolved.\n",
'C-09 as nine': "Reducers C-09 only. Two couplers.\n\nC-03 is unresolved.\n",
'19 reducers': "19 reducers. Two couplers.\n\nC-03 is unresolved.\n",
'empty': "",
}
bad=0
for k,n in PASS.items():
    f=grade(n); ok=not f; bad+= not ok; print('PASS-case', 'OK ' if ok else 'BAD', k, f)
for k,n in FAIL.items():
    f=grade(n); ok=bool(f); bad+= not ok; print('FAIL-case', 'OK ' if ok else 'BAD', k, f)
print('PROBLEMS:',bad)
