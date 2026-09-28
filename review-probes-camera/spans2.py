import re,struct,hashlib,subprocess
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
IMG='/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image'
d=open(IMG,'rb').read(); print('sha',hashlib.sha256(d).hexdigest(),'len',hex(len(d)))
pe=struct.unpack_from('<I',d,0x3c)[0]; ns=struct.unpack_from('<H',d,pe+6)[0]; osz=struct.unpack_from('<H',d,pe+20)[0]
opt=pe+24; ib=struct.unpack_from('<I',d,opt+28)[0]; dllc=struct.unpack_from('<H',d,opt+70)[0]
reloc=struct.unpack_from('<II',d,opt+96+5*8); print('ImageBase',hex(ib),'DllChar',hex(dllc),'reloc dir',[hex(x) for x in reloc])
secs=[]
for i in range(ns):
    o=opt+osz+40*i; name=d[o:o+8].rstrip(b'\0'); vs,va,rs,rp=struct.unpack_from('<IIII',d,o+8); secs.append((name,va,vs,rp,rs)); print(name,hex(va),hex(vs),'raw',hex(rp),hex(rs))
def off(va):
    r=va-ib
    for n,sva,vs,rp,rs in secs:
        if sva<=r<sva+max(vs,rs): return r-sva+rp
def rd(va,n): o=off(va); return d[o:o+n]
txt=open(W+'/src/api/camera_profiles.cpp').read()
bad=0
for va,hx in re.findall(r'\{(0x[0-9a-f]+),"([0-9a-f]*)"\}',txt):
    v=int(va,16); b=rd(v,len(hx)//2); ok=b.hex()==hx; bad+=not ok
    if v<0x73a000:
        open('s.bin','wb').write(b)
        dis=subprocess.run(['/home/brunner56/.local/bin/host-cmd','objdump','-D','-b','binary','-mi386','-Mintel','--adjust-vma='+va,'/home/brunner56/kp-live-20260922/review-probes-camera/s.bin'],capture_output=True,text=True).stdout
        dis=' | '.join(l.split('\t',2)[-1].strip() for l in dis.splitlines() if re.match(r'\s+[0-9a-f]+:\t',l))
    else: dis=repr(b)
    print(va,'OK' if ok else 'MISMATCH',dis)
for va,t in re.findall(r'\{(0x[0-9a-f]+),(0x[0-9a-f]+)\}',txt):
    got=struct.unpack('<I',rd(int(va,16),4))[0]; print('slot',va,hex(got),t,'OK' if got==int(t,16) else 'MISMATCH')
print('pending init',struct.unpack('<i',rd(0x7a242c,4))[0],'mapped_off',hex(off(0x7a242c)))
print('mismatches',bad)
