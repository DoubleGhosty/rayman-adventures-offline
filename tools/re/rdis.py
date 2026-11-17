import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import pickle,capstone,sys
f=open(common.LIB,'rb').read()
syms=common.load_syms()
addr2={}
for k,(v,s) in syms.items(): addr2.setdefault(v,k)
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
def cstr(a):
    if not (0x1d9ce40<=a<0x1ea15d0): return None
    return f[a:f.index(b'\0',a)][:80].decode('latin1')
def dis(a,n):
    regs={}
    for i in md.disasm(f[a:a+n],a):
        t=''
        if i.mnemonic in ('bl','b') and i.op_str.startswith('#'): t=addr2.get(int(i.op_str[1:],16),'')[:110]
        if i.mnemonic=='adrp': regs[i.op_str.split(',')[0]]=int(i.op_str.split('#')[1],16)
        if i.mnemonic=='add' and '#' in i.op_str:
            r=i.op_str.split(','); src=r[1].strip()
            if src in regs and len(r)>2 and '#' in r[2]:
                c=cstr(regs[src]+int(r[2].split('#')[1],16))
                if c is not None: t=repr(c)
        print(f'  {i.address:#x}: {i.mnemonic} {i.op_str} {t}')
if __name__=='__main__':
    a=sys.argv[1]
    if a in syms: v,s=syms[a]
    else:
        v=int(a,16); s=int(sys.argv[2],16)
    if len(sys.argv)>2 and a in syms: s=int(sys.argv[2],16)
    dis(v,s)
