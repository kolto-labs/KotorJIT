import pefile, struct, re, sys
from capstone import *
P='/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image'
pe=pefile.PE(P); IB=0x400000
img=pe.get_memory_mapped_image()
md=Cs(CS_ARCH_X86,CS_MODE_32); md.detail=False
TEXT=(0x401000,0x401000+0x33c000)
def rd(va,n): return img[va-IB:va-IB+n]
def u32(va): return struct.unpack('<I',rd(va,4))[0]
def f32(va): return struct.unpack('<f',rd(va,4))[0]
def cstr(va):
    b=rd(va,256); return b[:b.index(0)].decode('latin1')
def findstr(s):
    out=[]; pat=s.encode()+b'\0'
    for m in re.finditer(re.escape(pat), img):
        if m.start()==0 or img[m.start()-1]==0: out.append(m.start()+IB)
    return out
def xrefs(va):
    pat=struct.pack('<I',va); out=[]
    t0,t1=TEXT[0]-IB,TEXT[1]-IB
    for m in re.finditer(re.escape(pat), img[t0:t1]): out.append(m.start()+TEXT[0])
    return out
def dis(va,n=60,stop_ret=False):
    code=rd(va,n*8); k=0
    for i in md.disasm(code,va):
        print('%08x: %-24s %s %s'%(i.address,i.bytes.hex(),i.mnemonic,i.op_str)); k+=1
        if k>=n or (stop_ret and i.mnemonic.startswith('ret')): break
def insn_containing(va, back=16):
    # find instruction start that contains va
    for s in range(back,0,-1):
        for i in md.disasm(rd(va-s,s+8),va-s):
            if i.address<=va<i.address+i.size and i.address+i.size>va: return i
            if i.address>va: break
    return None
def callers(target):
    out=[]; t0,t1=TEXT[0]-IB,TEXT[1]-IB
    for m in re.finditer(b'\xe8', img[t0:t1]):
        a=m.start()+TEXT[0]; rel=struct.unpack('<i',img[a-IB+1:a-IB+5])[0]
        if a+5+rel==target: out.append(a)
    return out
def fstart(a):
    while not (img[a-IB-1] in (0x90,0xcc) and img[a-IB-2] in (0x90,0xcc)): a-=1
    return a
import re as _R
def dataptrs(v):
    return [m.start()+IB for m in _R.finditer(_R.escape(struct.pack('<I',v)),img) if not (TEXT[0]<=m.start()+IB<TEXT[1])]
