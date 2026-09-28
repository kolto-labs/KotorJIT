import re,pefile,capstone,hashlib,struct
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
IMG='/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image'
data=open(IMG,'rb').read(); print('sha',hashlib.sha256(data).hexdigest())
pe=pefile.PE(data=data)
print('ImageBase',hex(pe.OPTIONAL_HEADER.ImageBase),'DllChar',hex(pe.OPTIONAL_HEADER.DllCharacteristics),'reloc dir size',pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].Size)
for s in pe.sections: print(s.Name.rstrip(b'\0'),hex(s.VirtualAddress),hex(s.PointerToRawData),hex(s.Misc_VirtualSize),hex(s.SizeOfRawData))
def rd(va,n): return pe.get_data(va-0x400000,n)
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
txt=open(W+'/src/api/camera_profiles.cpp').read()
for va,hx in re.findall(r'\{(0x[0-9a-f]+),"([0-9a-f]*)"\}',txt):
    va=int(va,16); b=rd(va,len(hx)//2); ok=b.hex()==hx
    # also raw-file-offset view as used by the consistency test
    rawok=data[va-0x400000:va-0x400000+len(hx)//2].hex()==hx
    if va>=0x73a000: dis=repr(b)
    else: dis='; '.join(f'{i.mnemonic} {i.op_str}' for i in md.disasm(b,va))
    # is the span start an instruction boundary? check by disassembling from containing function isn't trivial; print prev bytes
    print(hex(va),ok,rawok,dis)
for va,t in re.findall(r'\{(0x[0-9a-f]+),(0x[0-9a-f]+)\}',txt):
    print('slot',va,hex(struct.unpack('<I',rd(int(va,16),4))[0]),t)
print('pending init', struct.unpack('<i',rd(0x7a242c,4))[0], 'rawfile', struct.unpack_from('<i',data,0x7a242c-0x400000)[0])
