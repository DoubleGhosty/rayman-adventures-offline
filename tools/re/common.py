"""Shared paths/caches for the reverse-engineering helpers (run from anywhere)."""
import os, pickle, struct
HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', '..', 'binaries', 'libuaf_original.so')
SYMS = os.path.join(HERE, 'syms.pkl')

def load_syms():
    """{mangled_name: (vaddr, size)} from .dynsym (cached in syms.pkl)."""
    if os.path.exists(SYMS):
        return pickle.load(open(SYMS, 'rb'))
    f = open(LIB, 'rb').read()
    dynsym, dynstr, n = 0x90330, 0x330c78, 0x2a0948 // 24
    syms = {}
    for i in range(n):
        name, info, other, shndx, val, size = struct.unpack_from('<IBBHQQ', f, dynsym + i * 24)
        if val:
            o = dynstr + name
            syms[f[o:f.index(b'\0', o)].decode('latin1')] = (val, size)
    pickle.dump(syms, open(SYMS, 'wb'))
    return syms
