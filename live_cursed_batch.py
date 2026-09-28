import hashlib,json,subprocess,sys
from pathlib import Path
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
out=Path('/home/brunner56/kp-live-20260922')
files=sorted((root/'scripts/examples/cursed').glob('*.lua'),key=lambda p:int(p.name.split('_')[0]))
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(out/'cursed-frozen-source.json').write_text(json.dumps(manifest,indent=2))
results=json.loads((out/'cursed-final-results.json').read_text()) if (out/'cursed-final-results.json').exists() else []
passed={r['script'] for r in results if r['exit_code']==0}
files=[p for p in files if p.name not in passed]
for p in files:
    if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest[str(p.relative_to(root))]:raise SystemExit('Source changed since freeze: '+str(p))
    console=out/(p.stem+'-final-console.log')
    print('RUN',p.name,flush=True)
    with console.open('w') as f:
        proc=subprocess.run(['/usr/bin/python3','-u',str(out/'live_example.py'),'--script','cursed/'+p.name,'--route',str(root/'scripts/harness/scenarios/cursed'/p.with_suffix('.toml').name)],stdout=f,stderr=subprocess.STDOUT)
    latest=json.loads((out/'latest-live-result.json').read_text())
    results.append({'script':p.name,'exit_code':proc.returncode,**latest})
    (out/'cursed-final-results.json').write_text(json.dumps(results,indent=2))
    print('RESULT',json.dumps(results[-1]),flush=True)
    if not latest['source_unchanged']:raise SystemExit('Source installation changed; halted')
    if proc.returncode:raise SystemExit('Route failed; halted for diagnosis')
