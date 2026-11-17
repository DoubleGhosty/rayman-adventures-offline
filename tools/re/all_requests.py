import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
"""Every game-server request the client can build: functions calling a GameServerRequest
constructor, with the module/action strings they use (v%u/%s/%s) and the HTTP method."""
import common, capstone, bisect, subprocess
f = open(common.LIB, 'rb').read()
syms = common.load_syms()
funcs = sorted((v, z, k) for k, (v, z) in syms.items() if z and 0xc6fc60 <= v < 0xc6fc60 + 0x112d1d4)
st = [x[0] for x in funcs]
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
def cstr(a):
    if not (0x1d9ce40 <= a < 0x1ea15d0): return None
    try: return f[a:f.index(b'\0', a)].decode('latin1')
    except Exception: return None
ctors = [v for k, (v, z) in syms.items() if 'GameServerRequestC' in k and z]
seen = set()
out = []
for c in ctors:
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'callers.py'), hex(c)], capture_output=True, text=True).stdout
    for line in r.splitlines()[1:]:
        pc = int(line.split()[0], 16)
        i = bisect.bisect_right(st, pc) - 1
        v, z, k = funcs[i]
        if v in seen: continue
        seen.add(v)
        regs = {}; strs = []
        for ins in md.disasm(f[v:v + z], v):
            if ins.mnemonic == 'adrp': regs[ins.op_str.split(',')[0]] = int(ins.op_str.split('#')[1], 16)
            elif ins.mnemonic == 'add' and '#' in ins.op_str:
                p = [x.strip() for x in ins.op_str.split(',')]
                if p[1] in regs and len(p) > 2 and '#' in p[2]:
                    s = cstr(regs[p[1]] + int(p[2].split('#')[1], 16))
                    if s and s not in strs and s not in ('sizeof', 'v%u/%s/%s'): strs.append(s)
        out.append((k, strs))
for k, s in sorted(out):
    print(k[:90], s[:8])
