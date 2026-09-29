import struct, re
from . import macho_model as mt
def vtables(m):
    """return {class_name: [(vt_addr, offset_to_top, [fn...])]}"""
    ps=8 if m.is64 else 4; fmt='<Q' if m.is64 else '<I'
    # find typeinfo name strings: search all readable sections for strings like "\d+Name"
    names={}
    tc=[s for s in m.sections if s['seg']=='__TEXT' and s['sect'] in ('__const','__cstring')]
    def tname(v):
        for s in tc:
            if s['addr']<=v<s['addr']+s['size']:
                o=s['offset']+v-s['addr']; e=m.data.find(b'\0',o,o+300)
                if e<0: return None
                t=m.data[o:e]
                if re.fullmatch(rb'\d{1,3}[A-Za-z_][A-Za-z0-9_]*|N(\d+[A-Za-z_][A-Za-z0-9_]*)+E|St\d+\w+',t): return t.decode()
        return None
    # scan data segments for pointer-sized values
    dsegs=[s for s in m.sections if s['seg'] in ('__DATA','__DATA_CONST') and s['sect'] in ('__const','__data')]
    words={}
    for s in dsegs:
        d=m.data[s['offset']:s['offset']+s['size']]
        for i in range(0,len(d)-ps+1,ps):
            words[s['addr']+i]=struct.unpack(fmt,d[i:i+ps])[0]
    ti={}  # typeinfo addr -> name
    for a,v in words.items():
        n=tname(v)
        if n and a-ps in words:
            ti[a-ps]=n
    text=m.sect('__text'); lo,hi=text['addr'],text['addr']+text['size']
    out={}
    for a,v in words.items():
        if v in ti and words.get(a-ps,1)!=None:
            ott=words.get(a-ps)
            if ott is None: continue
            if m.is64: ott=struct.unpack('<q',struct.pack('<Q',ott))[0]
            else: ott=struct.unpack('<i',struct.pack('<I',ott))[0]
            if ott>0 or ott< -0x10000: continue
            fns=[]; k=a+ps
            while k in words and (lo<=words[k]<hi or words[k]==0):
                fns.append(words[k]); k+=ps
                if len(fns)>400: break
            out.setdefault(ti[v],[]).append((a+ps,ott,fns))
    return out
if __name__=='__main__':
    import sys
    m=mt.MachO(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else 'x86_64')
    vt=vtables(m)
    for c in ['8CSWSDoor','12CSWSCreature','25CSWVirtualMachineCommands','8CSWSArea','10CSWSModule','13CSWSEncounter','9CSWSStore','12CSWSWaypoint','22CSWSAreaOfEffectObject','11CSWSTrigger','13CSWSPlaceable']:
        for (a,ott,fns) in vt.get(c,[]):
            print(c, hex(a), ott, len(fns))
