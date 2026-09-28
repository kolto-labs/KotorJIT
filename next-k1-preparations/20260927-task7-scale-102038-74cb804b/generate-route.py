# Save/run only inside the new private preparation directory.
import json, os, pathlib, tomllib
out = pathlib.Path(os.environ['KP_TASK7_ROUTE'])
steps = []
def add(**s): steps.append(s)
def check(label, code, **kw):
    add(label=label, do='assert_lua', code=code, equals=True, **kw)
def physical(label, code):
    add(label=label, do='console_command', code=code, contains=['boolean: true'],
        expect_values=[{'type':'Boolean','value':True}], return_count=1, timeout=30)
add(do='load_save', dir='000001 - AUTOSAVE', timeout=600)
add(wait='phase', equals='gameplay', timeout=600)
add(do='clear_auto_pause')
add(do='advance_dialog', until='gameplay', timeout=120)
check('peaceful danm14aa, checked native model, original scale',
 "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetModuleFileName')~='danm14aa' or q('GetIsObjectValid',p)~=1 or q('GetIsDead',p)==1 or q('GetIsInCombat',p)~=0 or q('GetIsInConversation',p)~=0 or not kp.model.capabilities().available then return false end; task7_original=assert(kp.model.snapshot(p)); task7_module=q('GetModuleFileName'); task7_area=q('GetArea',p); task7_locals={}; for i=5,9 do task7_locals[i]=q('GetLocalNumber',p,i) end; q('SetCameraMode',p,2); q('SetCameraFacing',q('GetFacing',p)); return math.abs(task7_original.base-1)<0.001")
add(do='advance_ticks', ticks=120, timeout=30)
add(do='console_open', open=True)
physical('physically construct finite native scale scene',
 "local q=nwscript.call; task7_pc=q('GetFirstPC'); task7_body=assert(kp.model.snapshot(task7_pc)); task7_local5=q('GetLocalNumber',task7_pc,5); task7_scene=dofile('kotorphasor/scripts/model_scene.lua').new{name='task7scale',trigger=1,hold_ticks=60,spawn=false,scales={{0.35},{2.4},{task7_body.base}}}; return task7_scene.state=='waiting' and math.abs(task7_body.base-1)<0.001")
add(do='mark_log')
physical('physically arm delayed finite scene with a native timer',
 "task7_delay=0; function task7_tick() task7_delay=task7_delay+1; if task7_delay<=180 then return true end; task7_scene:tick(); return task7_scene.state~='complete' and task7_scene.state~='failed' end; task7_timer=kp.registertimer(16,'task7_tick'); nwscript.call('SetLocalNumber',task7_pc,5,1); return task7_timer>0")
add(do='console_open', open=False)
for phase, scale in ((1,0.35),(2,2.4),(3,1.0)):
    check(f'independent native phase {phase}, identity, effective ratio, peaceful gameplay',
      "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; if q('GetLocalNumber',p,6)~="+str(phase)+" then return false end; local c=assert(kp.model.snapshot(p)); return q('GetModuleFileName')==task7_module and q('GetArea',p)==task7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 and c.id==task7_original.id and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-"+str(scale)+")<0.001 and math.abs(c.effective-task7_original.effective/task7_original.base*"+str(scale)+")<0.001",
      poll=True, timeout=45)
check('native completion and exact original scale restored',
 "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; local c=assert(kp.model.snapshot(p)); return q('GetLocalNumber',p,7)==1 and q('GetLocalNumber',p,6)==3 and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-task7_original.base)<0.001 and math.abs(c.effective-task7_original.effective)<0.001",
 poll=True, timeout=60)
add(do='await_log', pattern=r'\[model-scene:task7scale\] phase=', minimum=3, maximum=3, timeout=10)
add(do='await_log', pattern=r'\[model-scene:task7scale\] complete phases=3 restored=1', minimum=1, maximum=1, timeout=10)
add(do='advance_ticks', ticks=120, timeout=30)
add(do='console_open', open=True)
physical('physically verify completion and release only scene-owned state',
 "assert(task7_scene.state=='complete' and task7_scene.phase==3); task7_scene:unload(); nwscript.call('SetLocalNumber',task7_pc,5,task7_local5); task7_scene=nil; task7_tick=nil; task7_body=nil; return true")
add(do='console_open', open=False)
check('native local slots and scale remain restored after physical cleanup',
 "local q=nwscript.call; local p=q('GetFirstPC'); for i=5,9 do if q('GetLocalNumber',p,i)~=task7_locals[i] then return false end end; local c=assert(kp.model.snapshot(p)); return q('GetModuleFileName')==task7_module and q('GetArea',p)==task7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-task7_original.base)<0.001 and math.abs(c.effective-task7_original.effective)<0.001")
add(do='advance_ticks', ticks=120, timeout=30)
def value(v):
    if isinstance(v, dict): return '{'+', '.join(k+'='+value(x) for k,x in v.items())+'}'
    if isinstance(v, list): return '['+', '.join(value(x) for x in v)+']'
    return json.dumps(v, ensure_ascii=True)
text = 'name="Task 7 physical native scale"\ntarget="k1"\n[settings]\ngame_speed=1.0\nhang_seconds=90\ndefault_timeout=45\nload_timeout=600\n'
for s in steps: text+='\n[[step]]\n'+'\n'.join(k+'='+value(v) for k,v in s.items())+'\n'
tomllib.loads(text)
with out.open('x') as f: f.write(text)
print(out, 'steps=',len(steps))