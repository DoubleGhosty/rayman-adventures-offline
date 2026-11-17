import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
"""List (field name, serializer call) pairs of an ITF SerializeImpl function, recursively."""
import pickle,capstone,re,sys
f=open(common.LIB,'rb').read()
syms=common.load_syms()
addr2={}
for k,(v,z) in syms.items(): addr2.setdefault(v,k)
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
def cstr(a):
    if not (0x1d9ce40<=a<0x1ea15d0): return None
    return f[a:f.index(b'\0',a)].decode('latin1')
def short(k):
    k=re.sub(r'_ZN3ITF17CSerializerObject','CSO::',k)
    m=re.search(r'Serialize(\w+?)I(.*)',k)
    return k[:110]
def fields(addr,size,depth=0,seen=None):
    seen=seen or set()
    if addr in seen or depth>4: return
    seen.add(addr)
    regs={}; last=None
    for i in md.disasm(f[addr:addr+size],addr):
        if i.mnemonic=='adrp': regs[i.op_str.split(',')[0]]=int(i.op_str.split('#')[1],16)
        elif i.mnemonic=='add' and '#' in i.op_str:
            r=[x.strip() for x in i.op_str.split(',')]
            if r[1] in regs and len(r)>2 and r[0]=='x1':
                c=cstr(regs[r[1]]+int(r[2].split('#')[1],16))
                if c is not None: last=c
        elif i.mnemonic in('bl','b') and i.op_str.startswith('#'):
            t=int(i.op_str[1:],16); k=addr2.get(t,hex(t))
            if 'Serialize' in k or 'Container' in k:
                typ=re.sub(r'.*?(Serialize\w*?)(I|E).*?(N?\d+)?','\1',k)
                tn=re.findall(r'N6online(\d+)(\w+)',k)
                tname=''
                if tn: n=int(tn[-1][0]); tname=tn[-1][1][:n]
                base=re.search(r'is_base_typeIT_|SerializeExtI(\w)',k)
                print('  '*depth+f'{last!s:28} {k[:120]}')
                # recurse into online::X::SerializeImpl / Serialize if present
                if tname:
                    for kk,(vv,zz) in syms.items():
                        if kk.startswith(f'_ZN6online{len(tname)}{tname}13SerializeImpl') and zz:
                            fields(vv,zz,depth+1,seen)
                last=None
if __name__=='__main__':
    a=sys.argv[1]
    v,z=syms[a] if a in syms else (int(a,16),int(sys.argv[2],16))
    fields(v,z)
