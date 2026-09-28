# For kp-accepted encodings that capstone calls invalid, ask GNU objdump for the length.
import random, subprocess, sys, os, re, tempfile, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md = Cs(CS_ARCH_X86, CS_MODE_64)
PFX = [0x66,0xf2,0xf3,0x2e,0x36,0x3e,0x26,0x64,0x65]  # no lock: lock only changes #UD, not length
rng = random.Random(7)
cases=[]
for _ in range(200000):
    b=[rng.choice(PFX) for _ in range(rng.choice([0,0,1,2]))]
    if rng.random()<0.5: b.append(0x40|rng.randrange(16))
    if rng.random()<0.5: b.append(0x0f)
    b+=[rng.randrange(256) for _ in range(20)]
    cases.append(bytes(b))
out=subprocess.run(["./dec_cli"],input="\n".join(c.hex() for c in cases)+"\n",capture_output=True,text=True).stdout.splitlines()
inv=[]
for c,l in zip(cases,out):
    ln=int(l.split()[0])
    if ln and next(md.disasm(c,0),None) is None: inv.append((c,ln))
rng.shuffle(inv); inv=inv[:3000]
# one blob, each case at a 64-byte stride, int3-padded; disassemble with --start-address per case is slow,
# so instead lay them out and parse objdump output by address.
blob=bytearray(b"\xcc"*(64*len(inv)))
for i,(c,ln) in enumerate(inv): blob[i*64:i*64+len(c)]=c
fn="blob.bin"; open(fn,"wb").write(blob)
txt=subprocess.run(["objdump","-D","-b","binary","-m","i386:x86-64","-w",fn],capture_output=True,text=True).stdout
lines=[]
for L in txt.splitlines():
    m=re.match(r"\s*([0-9a-f]+):\t([0-9a-f ]+)\t(.*)",L)
    if m: lines.append((int(m.group(1),16),len(m.group(2).split()),m.group(3).strip()))
starts={a:(n,t) for a,n,t in lines}
PREF=re.compile(r"^(rex(\.\w+)?|data16|addr32|fs|gs|ss|cs|ds|es|repz?|repnz|lock|bnd|notrack)$")
res=collections.Counter(); ex={}
for i,(c,ln) in enumerate(inv):
    a=i*64; total=0; txtop=None
    if a not in starts: res["objdump-desync"]+=1; continue
    while a+total in starts:
        n,t=starts[a+total]; total+=n
        if not PREF.match(t.split()[0] if t else ""): txtop=t; break
    key = "bad" if (txtop is None or txtop.startswith("(bad)")) else ("same-len" if total==ln else "DIFF-len")
    res[key]+=1
    if key=="DIFF-len": ex.setdefault(txtop.split()[0],(c[:max(ln,total)].hex(),ln,total,txtop))
print(res)
for k,v in ex.items(): print(k,v)
