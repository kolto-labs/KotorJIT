from pathlib import Path
import hashlib, io, json, shutil, tarfile, zipfile
r=Path(__file__).resolve().parent
s=r/'source';b=r/'build';p=r/'package'
acceptance=json.loads((r/'live-acceptance.json').read_text())
assert acceptance['k1']['result']=='passed' and acceptance['k2']['result']=='passed'
assert acceptance['k2']['playable_view_verified'] is True
assert acceptance['k1']['checks']>=44
for target in ('k1','k2'):
    assert acceptance[target]['artifacts']==acceptance['artifacts'],'Each target receipt must cover new binaries'
assert acceptance['k2']['physical_console_commands']>=8
assert acceptance['artifacts']==json.loads((r/'build-artifacts.json').read_text()),'Acceptance must cover new exact binaries'
scope=json.loads((r/'release-scope-check.json').read_text())
assert scope['dll_sha256']==acceptance['artifacts']['kphasor.dll']
assert scope['unfinished_playback_absent'] and scope['experimental_projectiles_absent']
# Approval file is supplied only after independent review freezes the final table.
approval=json.loads((r/'approved-k2-table.json').read_text())
assert approval['approved'] is True
k2=Path(approval['path']);k2bytes=k2.read_bytes()
assert hashlib.sha256(k2bytes).hexdigest()==approval['sha256']
assert json.loads(k2bytes)['build']=='k2_gog_aspyr'
assert acceptance['k2']['table_sha256']==approval['sha256'],'K2 live receipt must cover approved table'
assert hashlib.sha256((s/'data/addresses/k2_gog_aspyr.json').read_bytes()).hexdigest()==approval['sha256']
assert 'DRAFT — NOT RELEASE READY' not in (r/'README-preview.md').read_text(),'Refresh README only after acceptance'
# Corresponding source is selected explicitly; research receipts are not a release input.
roots={'src','tools','scripts','third_party','data'}
root_files={'CMakeLists.txt','LICENSE','ATTRIBUTION.md','VERSION','README.md','CONTRIBUTING.md','CHANGELOG.md','.gitignore'}
docs={'docs/devtools-console.md','docs/devtools-protocol.md','docs/user/install.md'}
retail={'.bif','.key','.mdl','.mdx','.rim','.erf','.sav','.ncs','.nss','.bik','.tlk','.2da','.utp','.utc','.uti','.dlg','.wav','.mp3','.mp4'}
build_outputs={'.o','.obj','.a','.so','.dll','.exe','.d','.pyc'}
excluded=[];sanitized=[];source_hashes={}
def source_allowed(rel):
    parts=rel.parts;name=rel.as_posix()
    if parts[0] not in roots and name not in root_files and name not in docs:return False
    if '.git' in parts or '__pycache__' in parts:return False
    if name.startswith('data/adjudication/'):return False
    if name.startswith('data/research/') and name!='data/research/phasor_structs.json':return False
    if rel.suffix.lower() in retail|build_outputs:return False
    if parts[0]=='third_party' and parts[1] not in {'luajit','imgui'}:return False
    if name in {'third_party/luajit/src/luajit','third_party/luajit/src/host/buildvm'}:return False
    return True
def clean_bytes(f, name):
    data=k2bytes if f==s/'data/addresses/k2_gog_aspyr.json' else f.read_bytes()
    if f.suffix=='.json':
        obj=json.loads(data)
        changes=[]
        def walk(v):
            if isinstance(v,dict):
                for k in list(v):
                    if k=='reference_image' or (k in {'signature_source','source_path','corpus_path'} and isinstance(v[k],str) and v[k].startswith(('/home/','/run/media/'))):
                        changes.append(k);del v[k]
                    else:walk(v[k])
            elif isinstance(v,list):
                for x in v:walk(x)
        walk(obj)
        if changes:
            data=(json.dumps(obj,indent=2)+'\n').encode();sanitized.append({'path':name,'removed_metadata_keys':sorted(set(changes))})
    return data
# Fail before staging for unexpected links; do not follow paths out of the export.
files=sorted(s.rglob('*'))
assert not any(f.is_symlink() for f in files), 'source contains a symlink; review before packaging'
provenance=json.loads((r/'source-provenance.json').read_text())
for name,expected in provenance['overlay_sha256'].items():
    assert hashlib.sha256((s/name).read_bytes()).hexdigest()==expected, name
for name in ('kphasor.dll','binkw32.dll'):assert (b/name).is_file(),name
for name,expected in json.loads((r/'live-acceptance.json').read_text())['artifacts'].items():
    assert hashlib.sha256((b/name).read_bytes()).hexdigest()==expected,name
provenance['table_overlay']={'path':'data/addresses/k2_gog_aspyr.json','sha256':approval['sha256']}
(r/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
p.mkdir(exist_ok=False)
for name in ('kphasor.dll','binkw32.dll'):
    shutil.copy2(b/name,p/name)
    assert hashlib.sha256((p/name).read_bytes()).hexdigest()==acceptance['artifacts'][name]
for name in ('source-provenance.json','README-preview.md','live-acceptance.json','release-scope-check.json'):shutil.copy2(r/name,p/name)
for name in ('LICENSE','ATTRIBUTION.md','docs/devtools-console.md','docs/devtools-protocol.md','third_party/imgui/LICENSE.txt','third_party/imgui/PIN.md','third_party/luajit/COPYRIGHT'):
    dest=p/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s/name,dest)
a=p/'kotorphasor/addresses';a.mkdir(parents=True)
for name in ('k1_gog_103.json','k2_gog_aspyr.json'):
    (a/name).write_bytes(clean_bytes(s/'data/addresses'/name,'kotorphasor/addresses/'+name))
with tarfile.open(p/'source.tar.gz','w:gz') as tf:
    for f in files:
        if not f.is_file():continue
        rel=f.relative_to(s)
        if not source_allowed(rel):excluded.append(rel.as_posix());continue
        data=clean_bytes(f,'source/'+rel.as_posix())
        info=tf.gettarinfo(str(f),arcname='source/'+rel.as_posix());info.size=len(data)
        tf.addfile(info,io.BytesIO(data));source_hashes[rel.as_posix()]=hashlib.sha256(data).hexdigest()
receipt={'exclusions':excluded,'sanitizations':sanitized,'source_files_sha256':source_hashes,'research_exception':'data/research/phasor_structs.json retained because structs.cmake requires it to regenerate the shipped layout table','scope':'No retail assets; private corpus files and research reports excluded. Descriptive private path metadata removed from packaged JSON only; build source unchanged.'}
(p/'packaging-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
manifest={'scope':'K1/K2 GOG Windows preview tested under Wine; K1 44 checks; K2 one copied save and eight physical-console commands with mixed Steam assets and empty Override; native Windows and Mac unverified','files':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file()}}
(p/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
z=r/'kotorphasor-k1-k2-gog-console-preview.zip'
with zipfile.ZipFile(z,'x',compression=zipfile.ZIP_DEFLATED) as out:
    for f in sorted(p.rglob('*')):
        if f.is_file():out.write(f,arcname='kotorphasor-preview/'+str(f.relative_to(p)))
(r/'zip-sha256.txt').write_text(hashlib.sha256(z.read_bytes()).hexdigest()+'  '+z.name+'\n')
with zipfile.ZipFile(z) as check:
    assert check.testzip() is None,'ZIP CRC failure'
    for name,expected in manifest['files'].items():
        assert hashlib.sha256(check.read('kotorphasor-preview/'+name)).hexdigest()==expected,name
(r/'verification.json').write_text(json.dumps({'zip_crc':'PASS','manifest_hashes':'PASS','files_checked':len(manifest['files']),'zip_sha256':hashlib.sha256(z.read_bytes()).hexdigest()},indent=2)+'\n')
print(z)
