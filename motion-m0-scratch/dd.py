import sys
from kre import *
# disassemble until a ret followed by padding (cc/90), max n
def fn(va,n=400):
    code=rd(va,n*8)
    for i in md.disasm(code,va):
        print('%08x: %-20s %s %s'%(i.address,i.bytes.hex(),i.mnemonic,i.op_str))
        if i.mnemonic.startswith('ret'):
            nx=img[i.address+i.size-IB]
            if nx in (0x90,0xcc): break
for a in sys.argv[1:]:
    print('==',a); fn(int(a,16))
