import json,sys,shutil,tempfile,pathlib,csv,io
T=sys.argv[1]; sys.path.insert(0,T+'/tests')
from rl_world_verifiers.models import VerifierSpec, effective_weights
from rl_world_verifiers.sources.registry import SourceRegistry
from rl_world_verifiers.verifiers import verify_definition
spec=VerifierSpec.model_validate_json(open(T+'/tests/verifier.json').read()); W=effective_weights(spec.verifiers)
G=pathlib.Path(T+'/solution/files')
def grade(mut):
    d=pathlib.Path(tempfile.mkdtemp())
    for f in G.iterdir(): shutil.copy(f,d/f.name)
    mut(d); reg=SourceRegistry(d)
    return [v.name for v in spec.verifiers if not verify_definition(v,reg,W[v.name],config=spec.config,completion_fn=None)['result']['success']]
def edit(name,fn): return lambda d:(d/name).write_bytes(fn((d/name).read_bytes()))
reg_rows=lambda d: list(csv.reader(io.StringIO((d/'fitting_register.csv').read_text())))
def write_rows(d,rows,quote=False):
    s=io.StringIO(); csv.writer(s,quoting=csv.QUOTE_ALL if quote else csv.QUOTE_MINIMAL,lineterminator='\n').writerows(rows); (d/'fitting_register.csv').write_text(s.getvalue())
def jsonmut(fn):
    def m(d):
        j=json.loads((d/'results.json').read_text()); j=fn(j); (d/'results.json').write_text(json.dumps(j))
    return m
E={
'E3 json key order': jsonmut(lambda j: dict(reversed(list(j.items())))),
'E4 quote all csv': lambda d: write_rows(d,reg_rows(d),True),
'E5 CRLF all': lambda d: [ (d/f).write_bytes((d/f).read_bytes().replace(b'\n',b'\r\n')) for f in ('fitting_register.csv','results.json','takeoff_note.md')],
'E6 no trailing newline': edit('fitting_register.csv',lambda b:b.rstrip(b'\n')),
'E7 BOM register': edit('fitting_register.csv',lambda b:b'\xef\xbb\xbf'+b),
'E8 counts as 9.0': jsonmut(lambda j:{**j,'reducer_count':9.0,'coupler_count':2.0}),
'E9 total 124.50': edit('results.json',lambda b:b.replace(b'124.5',b'124.50')),
'E14 scratch file': lambda d:(d/'scratch.py').write_text('x=1'),
}
B={
'B1 flip C-06 kind': lambda d: write_rows(d,[r if r[0]!='C-06' else ['C-06','NONE','UNRESOLVED'] for r in reg_rows(d)]),
'B1b listing lure C-04 coupler': lambda d: write_rows(d,[r if r[0]!='C-04' else ['C-04','CP-114-N','COUPLER'] for r in reg_rows(d)]),
'B2 drop row': lambda d: write_rows(d,[r for r in reg_rows(d) if r[0]!='C-10']),
'B3 extra row': lambda d: write_rows(d,reg_rows(d)+[['C-17','NONE','COUPLER']]),
'B4 count +1': jsonmut(lambda j:{**j,'coupler_count':3}),
'B4b total incl C-03 (133.5)': jsonmut(lambda j:{**j,'total_run_ft':133.5}),
'B5 C-03 resolved via listing': lambda d: write_rows(d,[r if r[0]!='C-03' else ['C-03','RD-112-114-N','REDUCER'] for r in reg_rows(d)]),
'B6 empty register': edit('fitting_register.csv',lambda b:b''),
'B7 delete results': lambda d:(d/'results.json').unlink(),
'B8 {} results': edit('results.json',lambda b:b'{}'),
'row order swapped': lambda d: write_rows(d,[reg_rows(d)[0]]+[reg_rows(d)[2],reg_rows(d)[1]]+reg_rows(d)[3:]),
}
bad=0
for k,m in E.items(): f=grade(m); ok=not f; bad+=not ok; print('E', 'OK ' if ok else 'BAD', k, f)
for k,m in B.items(): f=grade(m); ok=bool(f); bad+=not ok; print('B', 'OK ' if ok else 'BAD', k, f)
print('PROBLEMS',bad)
