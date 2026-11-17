import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import struct,sys,pickle,os
f=open(common.LIB,'rb').read()
cache=os.path.join(common.HERE,'relas.pkl')
if os.path.exists(cache): rel=pickle.load(open(cache,'rb'))
else:
    rel={}
    rd=0x9b7890
    for k in range(0x2b4a30//24):
        off,info,add=struct.unpack_from('<QQq',f,rd+k*24)
        if info&0xffffffff==0x403: rel[off]=add
    pickle.dump(rel,open(cache,'wb'))
def v2o(v):  # data segment vaddr -> file offset
    return v-0x10000 if v>=0x23b4958 else v
def ptr(v): return rel.get(v, struct.unpack_from('<Q',f,v2o(v))[0])
def cstr(a):
    try: return f[a:f.index(b'\0',a)].decode('latin1')
    except: return '?'
base=int(sys.argv[1],16); n=int(sys.argv[2]); sz=int(sys.argv[3],16) if len(sys.argv)>3 else 0x18
for i in range(n):
    e=base+i*sz
    p=ptr(e); rest=f[v2o(e)+8:v2o(e)+sz]
    print(hex(e), repr(cstr(p)), rest.hex())
