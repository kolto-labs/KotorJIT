#!/usr/bin/env python3
"""Task 7 attempt 2: generate the harness routes (test-driver layer). PREP ONLY.

Writes, only into this directory:
  task7s2-v1-readonly-camera.toml   runnable candidate (V1, read-only kp.camera)
  task7s2-v2-stage2-PLACEHOLDER.toml NOT runnable (V2; kp.camera.set_distance/restore
                                     do not exist yet; poisoned top-level key)
  launcher-args.json                 proposed creative-runner marker flags

One constant (GIANT) feeds the typed construct command, the phase-2 native gate
and the phase-2 capture-marker regex; the three are asserted to agree below.
The Lua scene's camera tolerances are parsed from task7s2_scale.lua and asserted
equal to the route's, so the scene-side watch and the independent route gate
cannot drift apart.
"""
import json, os, pathlib, re, sys, tomllib

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / 'task7s2_scale.lua'
NAME = 'task7s2'
TINY, GIANT = 0.35, 1.9           # GIANT: see prep-report.md "Giant scale" (framing-fit.py)
Q_TOL, P_TOL, CFG_TOL = 0.001, 0.01, 0.0001
FACING_TOL, PC_POS_TOL = 0.1, 0.01
SETTLE_SAMPLES, SETTLE_SECONDS, SETTLE_TIMEOUT = 15, 20, 300
assert 1 < GIANT <= 2.0 and 0 < TINY < 1

# --- cross-check the Lua scene's constants -----------------------------------
lua = SCRIPT.read_text()
def lua_const(name):
    m = re.search(r'\b' + name + r'\s*=\s*([0-9.]+)', lua)
    assert m, name
    return float(m.group(1))
assert lua_const('Q_TOL') == Q_TOL and lua_const('P_TOL') == P_TOL and lua_const('CFG_TOL') == CFG_TOL
assert lua_const('GIANT_MAX') >= GIANT

def fmt3(x): return '%.3f' % x                     # model_scene logs base=%.3f
CONSTRUCT = ("task7s2=dofile('kotorphasor/scripts/task7s2_scale.lua');"
             "return task7s2.construct{tiny=%s,giant=%s}" % (repr(TINY), repr(GIANT)))
MARKERS = {                                         # name -> regex (native log)
    'calm_start': r'\[task7s2\] calm_start$',
    'tiny':       r'\[model-scene:task7s2\] phase=1 actor=1 base=' + re.escape(fmt3(TINY)) + ' ',
    'giant':      r'\[model-scene:task7s2\] phase=2 actor=1 base=' + re.escape(fmt3(GIANT)) + ' ',
    'normal':     r'\[model-scene:task7s2\] phase=3 actor=1 base=1\.000 ',
    'restored':   r'\[model-scene:task7s2\] restored actors=1 holding-original-scale',
    'complete':   r'\[model-scene:task7s2\] complete phases=3 restored=1',
    'calm_end':   r'\[task7s2\] calm_end$',
}
EFFECT_START = r'\[model-scene:task7s2\] phase=1 actor=1'

# --- harness-state Lua helpers (defined once, in the precondition step) -------
# Independent of the scene script: the route reads the camera and the model itself.
LIB = (
 "T7={q=%r,p=%r,cfg=%r,face=%r,pos=%r}; "
 "function t7_cam(soft) local function bad(m) if soft then return nil,m end; error(m) end; local c,msg,code=kp.camera.snapshot(); if not c then return bad('camera snapshot failed: '..tostring(code)..' '..tostring(msg)) end; "
 "if c.behavior~='chase' then return bad('camera behavior '..tostring(c.behavior)..' vtable '..tostring(c.behavior_vtable)) end; "
 "if c.pending_style~=-1 then return bad('camera style reapply pending '..tostring(c.pending_style)) end; "
 "return {mode=c.mode,module=c.module,camera=c.camera,behavior_ptr=c.behavior_ptr,distance=c.distance,speed=c.speed,pitch=c.pitch,height=c.height,dolly=c.dolly,style_row=c.style_row,base_distance=c.base_distance,base_view_angle=c.base_view_angle,q=c.raw_28_unverified,p=c.raw_38_unverified,p2=c.raw_50_unverified} end; "
 "function t7_camdev(a,b) for _,k in ipairs{'mode','module','camera','behavior_ptr','dolly','style_row'} do if a[k]~=b[k] then return false,k..' changed '..tostring(a[k])..'->'..tostring(b[k]) end end; "
 "for _,k in ipairs{'distance','speed','pitch','height','base_distance','base_view_angle'} do if math.abs(a[k]-b[k])>T7.cfg then return false,k..' changed '..a[k]..'->'..b[k] end end; "
 "local mq,mp=0,0; for i=1,4 do mq=math.max(mq,math.abs(a.q[i]-b.q[i])) end; for i=1,3 do mp=math.max(mp,math.abs(a.p[i]-b.p[i]),math.abs(a.p2[i]-b.p2[i])) end; "
 "if mq>T7.q then return false,'raw_28 moved '..mq end; if mp>T7.p then return false,'raw_38/raw_50 moved '..mp end; return true,'same',mq,mp end; "
 "function t7_pose() local q=nwscript.call; local p=q('GetFirstPC'); local v=q('GetPosition',p); return {f=q('GetFacing',p),x=v.x,y=v.y,z=v.z} end; "
 "function t7_posedev(a,b) if math.abs(a.f-b.f)>T7.face then return false,'PC facing changed' end; for _,k in ipairs{'x','y','z'} do if math.abs(a[k]-b[k])>T7.pos then return false,'PC moved' end end; return true end; "
 "function t7_stable(where) local ok,why=t7_camdev(t7_cam0,t7_cam()); if not ok then error('camera moved at '..where..': '..why) end; local pk,pw=t7_posedev(t7_pose0,t7_pose()); if not pk then error(pw..' at '..where) end; return true end"
) % (Q_TOL, P_TOL, CFG_TOL, FACING_TOL, PC_POS_TOL)

PRECONDITION = (
 "local q=nwscript.call; local p=q('GetFirstPC'); "
 "if not (kp.camera and kp.camera.capabilities) then error('kp.camera missing: wrong build') end; "
 "local cc=kp.camera.capabilities(); if cc.available~=true or cc.profile~='windows-k1-gog' then error('kp.camera unavailable: '..tostring(cc.profile)) end; "
 "if q('GetModuleFileName')~='danm14aa' or q('GetIsObjectValid',p)~=1 or q('GetIsDead',p)==1 or q('GetIsInCombat',p)~=0 or q('GetIsInConversation',p)~=0 or not kp.model.capabilities().available then return false end; "
 "t7_original=assert(kp.model.snapshot(p)); t7_module=q('GetModuleFileName'); t7_area=q('GetArea',p); t7_locals={}; for i=5,9 do t7_locals[i]=q('GetLocalNumber',p,i) end; "
 + LIB + "; return math.abs(t7_original.base-1)<0.001")

CAMERA_MODE = "local q=nwscript.call; q('SetCameraMode',q('GetFirstPC'),2); return true"

# Anchor-based settle: every sample is compared to a fixed anchor, not to the
# previous sample, so a slow drift cannot pass by small steps.
SETTLE = ("local c,why=t7_cam(true); t7_settle_last=why; t7_resets=t7_resets or 0; if not c then t7_anchor=nil; return false end; "
          "if not t7_anchor then t7_anchor=c; t7_anchor_t=os.time(); t7_same=0; return false end; "
          "local ok=t7_camdev(t7_anchor,c); if ok then t7_same=t7_same+1 else t7_anchor=c; t7_anchor_t=os.time(); t7_same=0; t7_resets=t7_resets+1 end; "
          "return t7_same>=%d and os.difftime(os.time(),t7_anchor_t)>=%d") % (SETTLE_SAMPLES, SETTLE_SECONDS)

BASELINE = ("t7_cam0=t7_cam(); local ok,why=t7_camdev(t7_anchor,t7_cam0); if not ok then error('camera moved after settle: '..why) end; t7_pose0=t7_pose(); return true")

# Harness-state kp.print does not reach kotorphasor.log (CAL log has 0 'camera-calibration' lines),
# so receipts are returned from `lua` steps; report.json keeps about 200 characters of the detail.
BASELINE_RECEIPT = ("local c=t7_cam0; return ('d=%.4f s=%.3g pi=%.4f h=%.4f fov=%.4g bd=%.4g do=%s sr=%d q=%.4f,%.4f,%.4f,%.4f p=%.3f,%.3f,%.3f r=%d f=%.2f')"
 ":format(c.distance,c.speed,c.pitch,c.height,c.base_view_angle,c.base_distance,tostring(c.dolly),c.style_row,c.q[1],c.q[2],c.q[3],c.q[4],c.p[1],c.p[2],c.p[3],t7_resets,t7_pose0.f)")

def phase_gate(phase, scale):
    return ("local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; "
            "t7_stable('phase %d poll'); if q('GetLocalNumber',p,6)~=%d then return false end; "
            "local c=assert(kp.model.snapshot(p)); return q('GetModuleFileName')==t7_module and q('GetArea',p)==t7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 "
            "and c.id==t7_original.id and c.model==t7_original.model and c.creature==t7_original.creature "
            "and math.abs(c.base-%s)<0.001 and math.abs(c.effective-t7_original.effective/t7_original.base*%s)<0.001") % (phase, phase, repr(scale), repr(scale))

COMPLETION = ("local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; t7_stable('completion poll'); "
              "local c=assert(kp.model.snapshot(p)); return q('GetLocalNumber',p,7)==1 and q('GetLocalNumber',p,6)==3 and c.model==t7_original.model and c.creature==t7_original.creature "
              "and math.abs(c.base-t7_original.base)<0.001 and math.abs(c.effective-t7_original.effective)<0.001")

CONSOLE_CLOSED = ("local q=nwscript.call; local p=q('GetFirstPC'); t7_stable('console closed'); "
                  "return q('GetLocalNumber',p,6)==0 and q('GetLocalNumber',p,8)==0")

AFTER_WINDOW = "return t7_stable('after calm_end')"
AFTER_RECEIPT = "local _,_,mq,mp=t7_camdev(t7_cam0,t7_cam()); return ('after calm_end vs baseline: max_q=%.6f max_p=%.6f'):format(mq,mp)"

FINAL = ("local q=nwscript.call; local p=q('GetFirstPC'); for i=5,9 do if q('GetLocalNumber',p,i)~=t7_locals[i] then return false end end; local c=assert(kp.model.snapshot(p)); "
         "return q('GetModuleFileName')==t7_module and q('GetArea',p)==t7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 and c.model==t7_original.model and c.creature==t7_original.creature "
         "and math.abs(c.base-t7_original.base)<0.001 and math.abs(c.effective-t7_original.effective)<0.001")

RECORD_POST = "local ok,why=t7_camdev(t7_cam0,t7_cam()); return 'post-cleanup camera (record only): '..tostring(ok)..' '..tostring(why)"

# --- V2 (Stage 2) placeholders: names from kp-camera-api-plan.md §3; NOT an existing API
V2_SET = ("--[[ V2 PLACEHOLDER: Stage 2 does not exist ]] "
          "t7_cam_orig=assert(kp.camera.snapshot()); assert(kp.camera.set_distance(t7_cam_orig, t7_cam_orig.distance*T7_K)); return true")
V2_RESTORE = ("--[[ V2 PLACEHOLDER: Stage 2 does not exist ]] "
              "assert(kp.camera.restore(t7_cam_orig)); return math.abs(kp.camera.snapshot().distance-t7_cam_orig.distance)==0")

def build(variant):
    steps = []
    def add(**s): steps.append(s)
    def check(label, code, **kw): add(label=label, do='assert_lua', code=code, equals=True, **kw)
    def physical(label, code):
        add(label=label, do='console_command', code=code, contains=['boolean: true'],
            expect_values=[{'type': 'Boolean', 'value': True}], return_count=1, timeout=30)
    add(do='load_save', dir='000001 - AUTOSAVE', timeout=600)
    add(wait='phase', equals='gameplay', timeout=600)
    add(do='clear_auto_pause')
    add(do='advance_dialog', until='gameplay', timeout=120)
    check('peaceful danm14aa, native model and camera available, original scale', PRECONDITION)
    check('one-time camera setup: chase mode only (no facing, no distance)', CAMERA_MODE)
    if variant == 'v2':
        check('V2 PLACEHOLDER: Stage 2 set_distance once before the marker (NOT RUNNABLE)', V2_SET)
    add(do='advance_ticks', ticks=600, timeout=180)
    check('camera settled: >=%d samples and >=%d s within tolerance of one fixed anchor' % (SETTLE_SAMPLES, SETTLE_SECONDS),
          SETTLE, poll=True, timeout=SETTLE_TIMEOUT)
    check('camera baseline taken and equal to the settle anchor (before start marker)', BASELINE)
    add(do='lua', label='camera baseline receipt (record)', code=BASELINE_RECEIPT)
    add(screenshot=True, label='framing still A: calm baseline, outside cadence window')
    add(do='advance_ticks', ticks=180, timeout=60)
    add(screenshot=True, label='framing still B: calm baseline +180 ticks, outside cadence window')
    check('camera unchanged over 180 settled ticks (before start marker)', "return t7_stable('pre-marker +180 ticks')")
    add(do='console_open', open=True)
    physical('physical F12 1: construct finite scene tiny=%s giant=%s' % (TINY, GIANT), CONSTRUCT)
    add(do='mark_log')
    physical('physical F12 2: arm delayed scene timer and trigger', 'return task7s2.arm()')
    add(do='console_open', open=False)
    check('console closed before calm_start; scene not started; camera unchanged', CONSOLE_CLOSED)
    add(do='await_log', label='calm_start has not fired before console closed',
        pattern=MARKERS['calm_start'], minimum=0, maximum=0, timeout=5)
    add(do='await_log', label='armed line', pattern=r'\[task7s2\] armed tiny=' + re.escape(fmt3(TINY)) + ' giant=' + re.escape(fmt3(GIANT)) + '$',
        minimum=1, maximum=1, timeout=10)
    for phase, scale in ((1, TINY), (2, GIANT), (3, 1.0)):
        check('independent native phase %d (base %s), identity, ratio, peaceful, camera unchanged' % (phase, scale),
              phase_gate(phase, scale), poll=True, timeout=90)
    check('native completion and exact original scale restored, camera unchanged', COMPLETION, poll=True, timeout=90)
    add(do='await_log', label='calm_end (restored lead-out finished)', pattern=MARKERS['calm_end'], minimum=1, maximum=1, timeout=120)
    for key in ('calm_start', 'tiny', 'giant', 'normal', 'restored', 'complete'):
        add(do='await_log', label='marker %s exactly once' % key, pattern=MARKERS[key], minimum=1, maximum=1, timeout=10)
    add(do='await_log', label='three phase lines', pattern=r'\[model-scene:task7s2\] phase=', minimum=3, maximum=3, timeout=10)
    add(do='await_log', label='scene-side camera watch stable', pattern=r'\[task7s2\] camera_watch .* cfg_changed=0 failures=0 stable=1$', minimum=1, maximum=1, timeout=10)
    add(do='await_log', label='no scene failure or timer error', pattern=r'\[(model-scene:)?task7s2\] (failed=|error=|scene_failed)', minimum=0, maximum=0, timeout=5)
    check('camera unchanged after calm_end (independent)', AFTER_WINDOW)
    add(do='lua', label='camera after-window receipt (record)', code=AFTER_RECEIPT)
    add(screenshot=True, label='framing still C: restored, after calm_end, outside cadence window')
    add(do='advance_ticks', ticks=120, timeout=60)
    add(do='console_open', open=True)
    physical('physical F12 3: verify completion and release scene-owned state', 'return task7s2.cleanup()')
    add(do='console_open', open=False)
    if variant == 'v2':
        check('V2 PLACEHOLDER: Stage 2 restore original distance (NOT RUNNABLE)', V2_RESTORE)
    check('native locals 5-9 and scale restored after physical cleanup', FINAL)
    add(do='lua', label='post-cleanup camera comparison (record only, not a gate)', code=RECORD_POST)
    add(do='advance_ticks', ticks=120, timeout=60)
    return steps

def value(v):
    if isinstance(v, dict): return '{' + ', '.join(k + '=' + value(x) for k, x in v.items()) + '}'
    if isinstance(v, list): return '[' + ', '.join(value(x) for x in v) + ']'
    return json.dumps(v, ensure_ascii=True)

def render(variant, steps):
    head = ''
    if variant == 'v2':
        head = ('# V2 PLACEHOLDER. NOT RUNNABLE. kp.camera.set_distance/restore (Stage 2) do not exist.\n'
                '# The unknown top-level key below makes the harness loader reject this file.\n'
                'NOT_RUNNABLE_STAGE2_CAMERA_API_MISSING = true\n')
    name = 'Task 7 attempt 2 native scale, read-only camera (V1)' if variant == 'v1' else 'Task 7 attempt 2 native scale, Stage 2 camera (V2 PLACEHOLDER)'
    text = head + 'name=' + value(name) + '\ntarget="k1"\n[settings]\ngame_speed=1.0\nhang_seconds=90\ndefault_timeout=45\nload_timeout=600\nshot_interval=0\n'
    for s in steps: text += '\n[[step]]\n' + '\n'.join(k + '=' + value(v) for k, v in s.items()) + '\n'
    return text

def main():
    out = {}
    for variant, fname in (('v1', 'task7s2-v1-readonly-camera.toml'), ('v2', 'task7s2-v2-stage2-PLACEHOLDER.toml')):
        steps = build(variant)
        text = render(variant, steps)
        parsed = tomllib.loads(text)
        if variant == 'v1':
            # single-constant agreement: typed command, phase-2 gate, phase-2 marker
            codes = [s['code'] for s in parsed['step'] if 'code' in s]
            assert ('giant=%r' % GIANT) in CONSTRUCT and any(CONSTRUCT == c for c in codes)
            assert any(("~=2 then return false" in c and 'c.base-%r' % GIANT in c) for c in codes)
            assert re.search(MARKERS['giant'], '[model-scene:task7s2] phase=2 actor=1 base=%s effective=%s' % (fmt3(GIANT), fmt3(GIANT)))
            assert sum(1 for s in parsed['step'] if s.get('do') == 'console_command') == 3
        path = HERE / fname
        path.write_text(text)
        out[fname] = len(steps)
    args = ['--marker', EFFECT_START]
    for k, v in MARKERS.items(): args += ['--capture-marker', k + '=' + v]
    args += ['--cadence-start-marker', 'calm_start', '--cadence-end-marker', 'calm_end']
    (HERE / 'launcher-args.json').write_text(json.dumps({
        'note': 'Proposed marker flags for kpharness.creative (Gamescope backend). Other flags as in the failed prep launch-once.json, with fresh paths, the new build, a fresh harness snapshot, and both --script entries (frozen model_scene.lua and task7s2_scale.lua).',
        'marker_args': args, 'giant': GIANT, 'tiny': TINY}, indent=2) + '\n')
    print(json.dumps(out))

if __name__ == '__main__':
    main()
