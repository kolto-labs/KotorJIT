from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md = Cs(CS_ARCH_X86, CS_MODE_64)
PFX = ["", "66", "48", "6648", "41", "6641", "6649", "f348"]
OPS = ["05","0d","15","1d","25","2d","35","3d","a9","68","69c0","81c0","c7c0","f7c0","f7c8","b8"]
tail = bytes(range(0x11,0x11+12))
for op in OPS:
    row=[]
    for p in PFX:
        c = bytes.fromhex(p+op)+tail
        i = next(md.disasm(c,0),None)
        row.append(i.size if i else 0)
    print(op, row, next(md.disasm(bytes.fromhex("6648"+op)+tail,0)).mnemonic)
for c in ["48660511223344","4866b811223344"]:
    i = next(md.disasm(bytes.fromhex(c)+tail,0),None); print(c, i.size if i else None, i.mnemonic if i else None)
