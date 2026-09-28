import sys,re,collections
sys.path.insert(0,sys.argv[1]); import scan_release_zip as Z
for z in sys.argv[2:]:
    raw=open(z,'rb').read()
    m=Z.privacy_markers()+('/tmp/','/var/tmp/')
    # reuse scanner walk but with only tmp markers
    out=[]; Z._scan_zip(Z.zipfile.ZipFile(Z.io.BytesIO(raw)),raw,'',tuple(m),0,out)
    hits=[f for f in out if f['kind']=='marker' and ('/tmp/' in f['detail'] or '/var/tmp/' in f['detail'])]
    print(z.split('/')[3],len(hits))
    for h in hits: print('  ',h['entry'].split('!')[-1],h['detail'])
