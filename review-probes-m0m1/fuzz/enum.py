# Structured enumeration: every 1-byte and 0F-map opcode x every ModRM x 3 SIB x prefix sets,
# compared with capstone wherever capstone decodes a valid instruction.
import subprocess, collections, itertools
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
PREF = [b"", b"\x66", b"\xf2", b"\xf3", b"\x48", b"\x41", b"\x66\x48", b"\xf3\x48", b"\x66\x41", b"\x2e", b"\xf0"]
TAIL = bytes(range(0x11, 0x11+16))
cases = []
for p in PREF:
    for ops in [bytes([o]) for o in range(256)] + [b"\x0f"+bytes([o]) for o in range(256)] + \
               [b"\x0f\x38"+bytes([o]) for o in (0x00,0xf0,0xf1)] + [b"\x0f\x3a"+bytes([o]) for o in (0x0f,0x16,0x22)]:
        if ops[0] in (0x66,0xf2,0xf3,0x2e,0x36,0x3e,0x26,0x64,0x65,0xf0,0x67) or (ops[0]&0xf0)==0x40: continue
        for m in range(256):
            for sib in ([0x24, 0x25, 0x65] if (m>>6)!=3 and (m&7)==4 else [0x24]):
                cases.append(p+ops+bytes([m, sib])+TAIL)
out = subprocess.run(["./dec_cli"], input="\n".join(c.hex() for c in cases)+"\n", capture_output=True, text=True).stdout.splitlines()
acc = 0; res = collections.Counter(); ex = {}
for c, l in zip(cases, out):
    ln, rel, roff = map(int, l.split()[:3])
    if not ln: continue
    acc += 1
    ins = next(md.disasm(c, 0x1000), None)
    if ins is None: res["cs-invalid"] += 1; continue
    if ins.size != ln:
        k = "LEN " + ins.mnemonic; res[k] += 1; ex.setdefault(k, (c[:max(ln, ins.size)].hex(), ln, ins.size, ins.op_str)); continue
    riprel = any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP for o in ins.operands)
    if (rel == 1) != riprel or (riprel and roff != ins.disp_offset):
        k = "RIP " + ins.mnemonic; res[k] += 1; ex.setdefault(k, (c[:ln].hex(), rel, roff, ins.disp_offset, ins.op_str)); continue
    res["ok"] += 1
print("cases", len(cases), "kp-accepted", acc)
for k, v in res.most_common(): print(v, k, ex.get(k, ""))
