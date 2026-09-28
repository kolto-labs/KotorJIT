import sys; from kre import *
for a in sys.argv[1:]:
    va=int(a,16); print('==',a); dis(va,int(sys.argv[0:1] and 400),stop_ret=False) if False else None
