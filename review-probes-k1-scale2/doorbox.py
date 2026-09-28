import zlib,struct,sys
def png(path):
    d=open(path,'rb').read(); assert d[:8]==b'\x89PNG\r\n\x1a\n'; i=8; idat=b''
    while i<len(d):
        n,=struct.unpack('>I',d[i:i+4]); t=d[i+4:i+8]; c=d[i+8:i+8+n]; i+=12+n
        if t==b'IHDR': w,h,bd,ct=struct.unpack('>IIBB',c[:10])
        elif t==b'IDAT': idat+=c
    bpp={2:3,6:4}[ct]; raw=zlib.decompress(idat); s=w*bpp; rows=[]; prev=bytearray(s); p=0
    for y in range(h):
        f=raw[p]; line=bytearray(raw[p+1:p+1+s]); p+=1+s
        for x in range(s):
            a=line[x-bpp] if x>=bpp else 0; b=prev[x]; c=prev[x-bpp] if x>=bpp else 0
            if f==1: line[x]=(line[x]+a)&255
            elif f==2: line[x]=(line[x]+b)&255
            elif f==3: line[x]=(line[x]+(a+b)//2)&255
            elif f==4:
                pp=a+b-c; pa,pb,pc=abs(pp-a),abs(pp-b),abs(pp-c)
                line[x]=(line[x]+(a if pa<=pb and pa<=pc else b if pb<=pc else c))&255
        rows.append(bytes(line)); prev=line
    return w,h,bpp,rows
for t in sys.argv[1:]:
    w,h,bpp,rows=png(t)
    # door box: bright orange panel R>110, R>G+30, B<G, rows 100-260
    xs=[];ys=[]
    for y in range(100,260):
        r=rows[y]
        for x in range(0,w):
            R,G,B=r[x*bpp],r[x*bpp+1],r[x*bpp+2]
            if R>110 and R>G+30 and G>B: xs.append(x); ys.append(y)
    xs.sort()
    print(t.split('/')[-1], 'n=',len(xs), 'x10/50/90=',xs[len(xs)//10] if xs else None, xs[len(xs)//2] if xs else None, xs[9*len(xs)//10] if xs else None, 'rows',min(ys) if ys else None,max(ys) if ys else None)
