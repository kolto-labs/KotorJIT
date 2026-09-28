import struct,sys
img=open(sys.argv[1],'rb').read()
pe=struct.unpack_from('<I',img,0x3c)[0]
nsec=struct.unpack_from('<H',img,pe+6)[0]; opt=struct.unpack_from('<H',img,pe+20)[0]
base=struct.unpack_from('<I',img,pe+24+28)[0]
secs=[]
for i in range(nsec):
    o=pe+24+opt+i*40
    name=img[o:o+8].rstrip(b'\0').decode(); vs,va,rs,ra=struct.unpack_from('<IIII',img,o+8)
    secs.append((name,va,vs,ra,rs))
def off(v):
    r=v-base
    for n,va,vs,ra,rs in secs:
        if va<=r<va+max(vs,rs): return ra+r-va
checks=[(0x5f6041,'e8ba76ffff80786d05'),(0x60b94b,'80786d05'),(0x615b71,'80786d05'),
 (0x639fee,'c7065c167500'),(0x63a011,'897e38'),(0x63a017,None),(0x63a026,'897e50'),(0x63a02c,'897e58'),
 (0x63ad94,'c7065c167500'),(0x63adb4,'897e38'),(0x63adba,None),(0x63adc6,'897e50'),(0x63adcc,'897e58')]
print('base',hex(base))
for v,h in checks:
    o=off(v); b=img[o:o+(len(h)//2 if h else 3)].hex()
    print(hex(v),hex(o),b,'OK' if h is None or b==h else 'MISMATCH '+h)
# call target
o=off(0x5f6041); rel=struct.unpack_from('<i',img,o+1)[0]; print('call target',hex(0x5f6041+5+rel))
