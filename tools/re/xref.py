import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import struct,array,sys
f=open(common.LIB,'rb').read()
t0,t1=0xc6fc60,0xc6fc60+0x112d1d4
words=array.array('I',f[t0:t1])
lo=int(sys.argv[1],16); hi=int(sys.argv[2],16)
for idx,w in enumerate(words):
    if (w&0x9f000000)==0x90000000:
        rd=w&31; immlo=(w>>29)&3; immhi=(w>>5)&0x7ffff
        imm=((immhi<<2)|immlo)<<12
        if imm&(1<<32): imm-=(1<<33)
        pc=t0+idx*4; page=(pc&~0xfff)+imm
        if not ((lo&~0xfff)<=page<=(hi|0xfff)): continue
        for k in range(1,12):
            if idx+k>=len(words): break
            w2=words[idx+k]
            # add xd, xn, #imm
            if (w2&0xffc00000)==0x91000000 and ((w2>>5)&31)==rd:
                tgt=page+((w2>>10)&0xfff)
                if lo<=tgt<hi: print(hex(pc),'add',hex(tgt))
                break
            # ldr/str 64-bit unsigned offset
            if (w2&0xff800000) in (0xf9000000,0xf9400000) and ((w2>>5)&31)==rd:
                tgt=page+((w2>>10)&0xfff)*8
                if lo<=tgt<hi: print(hex(pc),'ldst',hex(tgt))
                break
