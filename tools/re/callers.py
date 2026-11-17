import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
"""List the bl/b call sites of a function: callers.py <addr|symbol> [...]"""
import array, bisect
f = open(common.LIB, 'rb').read()
syms = common.load_syms()
t0, t1 = 0xc6fc60, 0xc6fc60 + 0x112d1d4
words = array.array('I', f[t0:t1])
funcs = sorted((v, z, k) for k, (v, z) in syms.items() if z and t0 <= v < t1)
starts = [v for v, z, k in funcs]

def owner(pc):
    i = bisect.bisect_right(starts, pc) - 1
    if i >= 0 and funcs[i][0] <= pc < funcs[i][0] + funcs[i][1]:
        return funcs[i][2]
    return '?'

def callers(target):
    out = []
    for idx, w in enumerate(words):
        if (w & 0x7c000000) == 0x14000000:      # b / bl imm26
            imm = w & 0x3ffffff
            if imm & (1 << 25):
                imm -= 1 << 26
            pc = t0 + idx * 4
            if pc + imm * 4 == target:
                out.append((pc, 'bl' if w & 0x80000000 else 'b'))
    return out

if __name__ == '__main__':
    for a in sys.argv[1:]:
        t = syms[a][0] if a in syms else int(a, 16)
        print(f'== {a}')
        for pc, kind in callers(t):
            print(f'  {pc:#x} {kind:2} {owner(pc)[:120]}')
