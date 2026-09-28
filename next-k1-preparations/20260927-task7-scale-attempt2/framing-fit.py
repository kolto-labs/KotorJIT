#!/usr/bin/env python3
"""Offline re-derivation of task7-k1-framing-plan.md §2b/§2c pinhole fits.
Pure arithmetic; reads no media. Pinhole, 768-row image, fixed vertical FOV,
camera dollied back along its optical axis about the look-at point on the
player's vertical axis (pitch and look-at kept). Units: z in normal heights."""
import math, sys, json
H=768; CY=H/2
def f_of(fov): return CY/math.tan(math.radians(fov/2))
def row(p, z, f):
    X, cz, a = p
    return CY - f*math.tan(math.atan2(z-cz, X) - a)
def _solve(M, b):
    n=len(b); M=[M[i][:]+[b[i]] for i in range(n)]
    for c in range(n):
        piv=max(range(c,n),key=lambda i:abs(M[i][c])); M[c],M[piv]=M[piv],M[c]
        for i in range(n):
            if i!=c:
                fac=M[i][c]/M[c][c]; M[i]=[M[i][j]-fac*M[c][j] for j in range(n+1)]
    return [M[i][n]/M[i][i] for i in range(n)]
def projective(points):
    """row(z)=(A z+B)/(C z+1); exact for 3 points, linear least squares for more."""
    rows=[[z,1.0,-z*y] for z,y in points]; rhs=[y for z,y in points]
    if len(points)==3: return _solve(rows,rhs)
    M=[[sum(r[i]*r[j] for r in rows) for j in range(3)] for i in range(3)]
    v=[sum(rows[k][i]*rhs[k] for k in range(len(rows))) for i in range(3)]
    return _solve(M,v)
def fit(points, f):
    """Pinhole (X, cz, a) with the same projective map as `projective`, fixed focal f."""
    A,B,C=projective(points)
    D0=f/(CY*C-A); t=C*D0; P=(B-CY)*D0/f
    X=(D0+t*P)/(1+t*t); cz=P-t*X
    p=(X,cz,math.atan(t))
    rms=math.sqrt(sum((row(p,z,f)-y)**2 for z,y in points)/len(points))
    return p, rms
def dolly(p,k):
    X,cz,a=p; lz=cz+X*math.tan(a)
    return (k*X, lz+k*(cz-lz), a)
def normal_px(p,f): return row(p,0,f)-row(p,1,f)
def k_for(p,f,target):
    lo,hi=0.3,5.0
    for _ in range(100):
        m=(lo+hi)/2
        if normal_px(dolly(p,m),f)>target: lo=m
        else: hi=m
    return (lo+hi)/2
def max_scale(p,f,margin):
    lo,hi=0.1,6.0
    for _ in range(100):
        m=(lo+hi)/2
        if row(p,m,f)>=margin: lo=m
        else: hi=m
    return (lo+hi)/2
def main():
    fov=float(sys.argv[1]) if len(sys.argv)>1 else 55.0
    f=f_of(fov)
    sets={}
    for ts,ns in ((0,-5),(5,-5),(5,0),(5,5)):
        sets[f'670/{ts:+d}/{ns:+d}']=[(0,670),(0.35,588+ts),(1.0,414+ns)]
    sets['4-point']=[(0,670),(0.35,588),(1.0,414),(1.92,40)]
    out={'fov':fov,'fits':{}}
    for name,pts in sets.items():
        p,rms=fit(pts,f)
        d={'rms':round(rms,2),'run_normal_px':round(normal_px(p,f),1),
           'run_top@2.0':round(row(p,2.0,f),1),'run_top@2.4':round(row(p,2.4,f),1),
           'run_max_scale_16px':round(max_scale(p,f,16),3)}
        for share in (0.30,0.275,0.25):
            k=k_for(p,f,share*H); q=dolly(p,k)
            d[f'k@{share}']=round(k,3); d[f'top@2.0@{share}']=round(row(q,2.0,f),1)
        # for V1: baselines 200..240 px, largest scale keeping 60 px and 16 px headroom
        for px in (205,211,217,220,225,230,235,240):
            k=k_for(p,f,px); q=dolly(p,k)
            d[f'max_scale_60px@{px}']=round(max_scale(q,f,60),3)
            d[f'max_scale_16px@{px}']=round(max_scale(q,f,16),3)
            d[f'feet_row@{px}']=round(row(q,0,f),1)
        out['fits'][name]=d
    print(json.dumps(out,indent=1))
if __name__=='__main__': main()
