import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import pickle,re,sys,subprocess,os
syms=common.load_syms()
vt={}
for k,(v,z) in syms.items():
    if k.startswith('_ZTV'): vt[v]=k
def name(addr):
    for d in (0x10,):
        k=vt.get(addr-d)
        if k: return re.sub(r'^_ZTV(N)?','',k)[:60]
    return hex(addr)
out=subprocess.run(['adb','logcat','-d','-s','RaymanDbg'],capture_output=True,text=True,env=dict(os.environ,MSYS_NO_PATHCONV='1')).stdout
for line in out.splitlines():
    m=re.search(r'(Module::\w+) this=(\w+) vt=(\w+) (.*) base=(\w+)(.*)',line)
    if not m: continue
    base=int(m.group(5),16); v=int(m.group(3),16)-base
    print(line[6:18], m.group(1).split('::')[1], m.group(2)[-6:], name(v), m.group(4), m.group(6))
