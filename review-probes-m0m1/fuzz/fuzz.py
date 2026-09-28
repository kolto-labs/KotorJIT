# Differential test: kp x64 decode() vs capstone 5 on biased random byte streams.
import random, subprocess, sys, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
PFX = [0x66,0xf2,0xf3,0xf0,0x2e,0x36,0x3e,0x26,0x64,0x65]
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
cases = []
def split(c):
    i=0; p=[]
    while c[i] in PFX: p.append(c[i]); i+=1
    rex = c[i] if (c[i]&0xf0)==0x40 else None
    if rex is not None: i+=1
    op = c[i:i+2].hex() if c[i]==0x0f else c[i:i+1].hex()
    return p, rex, op
def has66w(c):
    p, rex, op = split(c); return 0x66 in p and rex is not None and rex & 8
def opkey(c):
    p, rex, op = split(c)
    tag = "lock" if 0xf0 in p else ("f2/f3" if (0xf2 in p or 0xf3 in p) else "")
    return op + ("/"+tag if tag else "")
for _ in range(N):
    b = []
    for _ in range(rng.choice([0,0,0,1,1,2,3])): b.append(rng.choice(PFX))
    if rng.random() < 0.5: b.append(0x40 | rng.randrange(16))
    if rng.random() < 0.3: b.append(0x0f)
    b += [rng.randrange(256) for _ in range(20)]
    cases.append(bytes(b))
out = subprocess.run(["./dec_cli"], input="\n".join(c.hex() for c in cases)+"\n",
                     capture_output=True, text=True).stdout.splitlines()
accepted = mism = relmis = inval = 0
buckets = collections.defaultdict(list)
for c, line in zip(cases, out):
    ln, rel, roff, ends, r = line.split()
    ln, rel, roff = int(ln), int(rel), int(roff)
    if ln == 0: continue
    accepted += 1
    ins = next(md.disasm(c, 0x1000), None)
    if ins is None:
        buckets["invalid-in-cs:"+opkey(c)].append((c[:ln].hex(), ln)); inval += 1; continue
    if ins.size != ln:
        key = f"len kp={ln} cs={ins.size} {ins.mnemonic}"
        buckets["len:"+ins.mnemonic+(" 66+REX.W" if has66w(c) else " OTHER")].append((c[:max(ln,ins.size)].hex(), ln, ins.size, ins.mnemonic, ins.op_str)); mism += 1; continue
    riprel = any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP for o in ins.operands)
    mn = ins.mnemonic.replace("bnd ","").replace("notrack ","")
    br = mn in ("call","jmp") or mn.startswith("j")
    exp = 1 if riprel else 0
    if rel == 1 and (not riprel or roff != ins.disp_offset):
        buckets["rip:"+ins.mnemonic].append((c[:ln].hex(), roff, ins.disp_offset, ins.mnemonic, ins.op_str)); relmis += 1
    elif rel == 0 and riprel:
        buckets["missed-rip:"+ins.mnemonic].append((c[:ln].hex(), ins.mnemonic, ins.op_str)); relmis += 1
    elif rel == 2 and not (br and ins.imm_offset == roff):
        buckets["rel32:"+ins.mnemonic].append((c[:ln].hex(), roff, ins.imm_offset, ins.mnemonic, ins.op_str)); relmis += 1
print(f"cases={N} accepted={accepted} len_mismatch={mism} rel_mismatch={relmis} cs_invalid={inval}")
for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
    print(f"{len(v):6d} {k}  e.g. {v[0]}")
