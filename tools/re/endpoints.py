import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import pickle,capstone,re,json
f=open(common.LIB,'rb').read()
syms=common.load_syms()
addr2={}
for k,(v,z) in syms.items(): addr2.setdefault(v,k)
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
def cstr(a):
    if not (0x1d9ce40<=a<0x1ea15d0): return None
    return f[a:f.index(b'\0',a)].decode('latin1')
res=[]
for k,(v,z) in sorted(syms.items(),key=lambda x:x[1][0]):
    m=re.match(r'_ZN6online(\d+)(\w+?)13createRequestE',k)
    if not m or z==0: continue
    n=int(m.group(1)); cls=(m.group(1)+m.group(2))[len(m.group(1)):len(m.group(1))+n]
    regs={}; strs=[]; movs=[]
    for i in md.disasm(f[v:v+z],v):
        if i.mnemonic=='adrp': regs[i.op_str.split(',')[0]]=int(i.op_str.split('#')[1],16)
        elif i.mnemonic=='add' and '#' in i.op_str:
            r=[x.strip() for x in i.op_str.split(',')]
            if r[1] in regs and len(r)>2:
                c=cstr(regs[r[1]]+int(r[2].split('#')[1],16))
                if c: strs.append(c)
        elif i.mnemonic=='mov' and re.match(r'w2, #',i.op_str): movs.append(i.op_str)
    res.append((cls,strs,movs,hex(v)))
for cls,strs,movs,a in res: print(f'{cls:40} {a} {strs} {movs}')
