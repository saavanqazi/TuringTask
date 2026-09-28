import marshal, sys, types
from pathlib import Path
src_root, pyc_root = Path(sys.argv[1]), Path(sys.argv[2])
def norm(co):
    consts = tuple(norm(c) if isinstance(c, types.CodeType) else c for c in co.co_consts)
    return (co.co_name, co.co_code, consts, co.co_names, co.co_varnames, co.co_argcount,
            co.co_kwonlyargcount, co.co_posonlyargcount, co.co_flags, co.co_freevars, co.co_cellvars)
same = diff = 0
for pyc in sorted(pyc_root.rglob("*.pyc")):
    rel = pyc.relative_to(pyc_root).with_suffix(".py")
    py = src_root / rel
    if not py.exists():
        print("NO SOURCE", rel); diff += 1; continue
    a = marshal.loads(pyc.read_bytes()[16:])
    b = compile(py.read_text(encoding="utf-8"), str(py), "exec", dont_inherit=True, optimize=0)
    if norm(a) == norm(b): same += 1
    else: print("DIFFERS", rel); diff += 1
print("identical:", same, "different/missing:", diff)
