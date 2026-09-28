#!/usr/bin/env python3
"""Offline validation for the Task 7 attempt-2 prep. Launches no game, Wine,
Gamescope or FFmpeg; touches no lock. Imports the worktree harness read-only
(-I -S -B, sys.dont_write_bytecode) and writes only into this directory.

Checks
  1. Worktree Scenario.load accepts V1 and rejects V2 (poisoned key).
  2. control.py-equivalent route policy on V1 (3 physical commands, Boolean
     true / return_count 1, k1, game_speed 1.0, allowed verbs; the allowed set
     is widened by `screenshot` and `lua` versus the failed prep, on purpose).
  3. The creative-runner parser and marker_configuration accept the proposed
     marker flags (names and regexes).
  4. LuaJIT (Lua 5.1 syntax) compiles every embedded chunk, the typed console
     commands and task7s2_scale.lua.
  5. No NWScript routine name (data/routines/k1.json) appears in the Lua or in
     route chunks except as the first string argument of nwscript.call(...)
     through the local alias `q`/`call`.
  6. Stub simulation (LuaJIT, fake kp/nwscript/timer/clock): the V1 route's own
     chunks + task7s2_scale.lua + the frozen model_scene.lua run end to end; the
     marker order and every await_log bound are checked with the harness regexes.
     Negative cases: camera drift during giant, missing kp.camera, and a slow
     pre-settle drift. This is host simulation, not live evidence.
  7. L1 (NON-ACCEPTANCE camera diagnostic, CP §2h): loader accepts it, no
     console_command, 4 stills, shot_interval=0, reused chunks byte-identical to
     V1; launcher flags parse with no named markers and no cadence window; stub
     simulation (nominal, no kp.camera, non-chase behaviour, pan, huge floats)
     with every record string <= 150 chars and free of quotes/backslashes.
  8. postrun-gate.py on synthetic run directories: one PASS, and FAIL for a
     missing still, an empty still, a wrong-size still, a boot budget of 5,
     two launches, and an unset KP_MAX_BOOT_ATTEMPTS.
  9. postrun-gate.py --require-l1 (r3, closes round-2 review Finding I1): a
     synthetic V1 run with no L1 trace anywhere must REFUSE (nonzero exit, one
     line), reproduced first against postrun-gate.py.pre-r3 where it PASSED
     (red-first). Then, against the r3 gate: a well-formed L1/V1 pair PASSes;
     an L1 that failed its own gate, a wrong L1 route hash, an L1 whose
     boot-attempts.json shows launch_count 2 (with a stale PASS receipt, to
     prove the check re-reads the file rather than trusting the receipt), and
     an L1 that finished after V1 started, each REFUSE with the matching
     one-line reason. Plus (added after a self-review pass) five negative
     cases through check_admission()/check_build_match(): an out-of-band still
     height (A3), a negative feature dx that abs() must still catch (A4), a
     NaN delta that must not silently satisfy "<=1e-4" (A4), a missing
     admission.json (distinct from a failed rule), and mismatched
     creative-run.json runtime hashes between L1 and V1 (A6).
"""
import hashlib, json, os, pathlib, re, subprocess, sys, tomllib

HERE = pathlib.Path(__file__).resolve().parent
WT = pathlib.Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
HARNESS = WT / 'scripts/harness'
HELPER = pathlib.Path('/home/brunner56/kp-live-20260922/frozen-model-393f68d/model_scene.lua')
LUAJIT = '/run/host/usr/bin/luajit'
V1 = HERE / 'task7s2-v1-readonly-camera.toml'
V2 = HERE / 'task7s2-v2-stage2-PLACEHOLDER.toml'
L1 = HERE / 'l1-camera-diagnostic.toml'
PROBE = HERE / 'l1_camera_probe.lua'
SCRIPT = HERE / 'task7s2_scale.lua'
OUT = []
def say(*a):
    line = ' '.join(str(x) for x in a); OUT.append(line); print(line)
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def harness_load(path):
    code = ("import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,%r);from pathlib import Path;"
            "from kpharness.scenario import Scenario\n"
            "try:\n s=Scenario.load(Path(%r))\n print(json.dumps({'ok':True,'target':s.target,'settings':s.settings,'steps':[dict(index=x.index,kind=x.kind,raw=x.raw) for x in s.steps]},default=str))\n"
            "except Exception as e:\n print(json.dumps({'ok':False,'error':type(e).__name__+': '+str(e)}))\n") % (str(HARNESS), str(path))
    r = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], capture_output=True, text=True, env={'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin'})
    if r.returncode: raise SystemExit('loader crashed: ' + r.stderr)
    return json.loads(r.stdout)

def check_route_policy(parsed):
    physical = [s for s in parsed['steps'] if s['raw'].get('do') == 'console_command']
    assert len(physical) == 3, len(physical)
    assert all(s['raw']['expect_values'] == [{'type': 'Boolean', 'value': True}] and s['raw']['return_count'] == 1 for s in physical)
    assert parsed['target'] == 'k1' and float(parsed['settings']['game_speed']) == 1.0
    allowed = {'load_save', 'clear_auto_pause', 'advance_dialog', 'assert_lua', 'advance_ticks', 'console_open',
               'console_command', 'mark_log', 'await_log', 'lua'}   # + screenshot steps (widened vs failed prep)
    bad = [s['index'] for s in parsed['steps'] if not (s['raw'].get('do') in allowed or s['raw'].get('wait') == 'phase' or s['raw'].get('screenshot') is True)]
    assert not bad, bad
    return physical

def check_launcher_flags():
    args = json.loads((HERE / 'launcher-args.json').read_text())['marker_args']
    code = ("import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,%r)\n"
            "from kpharness.creative import parser, marker_configuration\n"
            "o=parser().parse_args(['--backend','linux-wine-k1-gamescope','--script','model_scene.lua','--script','task7s2_scale.lua','--route','task7s2-v1-readonly-camera.toml']+json.loads(sys.argv[1]))\n"
            "m,s,e=marker_configuration(o);print(json.dumps({'markers':m,'start':s,'end':e}))\n") % str(HARNESS)
    r = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, json.dumps(args)], capture_output=True, text=True, env={'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin'})
    if r.returncode: raise SystemExit('launcher flag check failed: ' + r.stderr[-2000:])
    return json.loads(r.stdout)

def luajit_compile(label, text):
    prog = "local s=io.read('*a'); local f,e=loadstring(s,'=chunk'); if not f then io.stderr:write(e) os.exit(1) end"
    r = subprocess.run([LUAJIT, '-e', prog], input=text, capture_output=True, text=True)
    assert r.returncode == 0, (label, r.stderr)

def nwscript_scan(chunks):
    names = {e['name'] for e in json.loads((WT / 'data/routines/k1.json').read_text())['routines']}
    hits = []; used = set()
    for label, text in chunks:
        # strip the sanctioned form: first string argument of nwscript.call / q / call
        sanctioned = re.findall(r"(?:nwscript\.call\(|\bq\(|\bcall\(|pcall\(\s*call\s*,)\s*['\"]([A-Za-z_0-9]+)['\"]", text)
        used.update(sanctioned)
        stripped = re.sub(r"(?:nwscript\.call\(|\bq\(|\bcall\(|pcall\(\s*call\s*,)\s*['\"][A-Za-z_0-9]+['\"]", 'CALL(', text)
        stripped = re.sub(r'--[^\n]*', '', stripped)          # comments
        for tok in set(re.findall(r'\b[A-Z][A-Za-z0-9_]+\b', stripped)):
            if tok in names: hits.append((label, tok))
    return hits, sorted(used), len(names)

def main():
    say('# validate.py', 'python', sys.version.split()[0])
    for p in (V1, V2, SCRIPT, HELPER, HERE / 'generate-route.py', HERE / 'launcher-args.json', HERE / 'framing-fit.py',
              L1, PROBE, HERE / 'generate-l1.py', HERE / 'l1-launcher-args.json', HERE / 'postrun-gate.py'):
        say('sha256', sha(p), p)
    # 1/2
    v1 = harness_load(V1)
    assert v1['ok'], v1
    physical = check_route_policy(v1)
    say('V1 Scenario.load: ok, steps=%d, physical_console_commands=%d, target=%s, game_speed=%s'
        % (len(v1['steps']), len(physical), v1['target'], v1['settings']['game_speed']))
    v2 = harness_load(V2)
    assert not v2['ok'], 'V2 must not load'
    say('V2 Scenario.load: REJECTED as intended ->', v2['error'])
    v2_raw = tomllib.loads(V2.read_text())
    assert v2_raw.get('NOT_RUNNABLE_STAGE2_CAMERA_API_MISSING') is True
    # 3
    m = check_launcher_flags()
    say('creative parser + marker_configuration: ok, markers=%s, cadence=%s..%s' % (sorted(m['markers']), m['start'], m['end']))
    # 4
    chunks = [('task7s2_scale.lua', SCRIPT.read_text())]
    for s in v1['steps']:
        if 'code' in s['raw']: chunks.append(('V1 step %d' % s['index'], s['raw']['code']))
    for s in tomllib.loads(V2.read_text())['step']:
        if 'code' in s: chunks.append(('V2 ' + s.get('label', s.get('do')), s['code']))
    l1 = harness_load(L1)
    assert l1['ok'], l1
    for s in l1['steps']:
        if 'code' in s['raw']: chunks.append(('L1 step %d' % s['index'], s['raw']['code']))
    chunks.append(('l1_camera_probe.lua', PROBE.read_text()))
    for label, text in chunks: luajit_compile(label, text)
    say('LuaJIT compile (Lua 5.1 syntax): ok, chunks=%d (%s)' % (len(chunks), subprocess.run([LUAJIT, '-v'], capture_output=True, text=True).stdout.strip()))
    # 5
    hits, used, n = nwscript_scan(chunks + [('model_scene.lua (frozen)', HELPER.read_text())])
    assert not hits, hits
    say('NWScript-name scan vs %d K1 routines: no bare routine names; routines reached only via nwscript.call: %s' % (n, ', '.join(used)))
    # 6
    sim(v1)
    # 7
    check_l1(v1, l1)
    # 8
    check_postrun_gate()
    # 9
    check_require_l1()
    (HERE / 'validation-output.txt').write_text('\n'.join(OUT) + '\n')

# ----------------------------------------------------------------- simulation
SIM_LUA = r'''
local CFG = CONFIG
local LOG, EVENTS = {}, {}
local ticks, now = 0, 1000000
local PC, AREA = 2147483644, 77
local locals = {[5]=0,[6]=0,[7]=0,[8]=0,[9]=0}
local model = {id=PC, model='0x1a2b', creature='0x3c4d', base=1.0, effective=1.25}
local eff0 = model.effective
local routines = {}
local cam = {behavior='chase', mode=2, pending_style=-1, module='0x10', camera='0x20', behavior_ptr='0x30',
  behavior_vtable='0x75165c', distance=6.25, speed=20, pitch=80, height=3.5, dolly=0, base_distance=6.25,
  base_view_angle=55, style_row=3, raw_28_unverified={0,0,0.38,0.92}, raw_38_unverified={100,90,4}, raw_50_unverified={100,90,4}}
local function emit(kind, a, b) EVENTS[#EVENTS+1] = kind..'\t'..tostring(a)..'\t'..tostring(b or '') end
local KP = {}
KP.print = function(s) LOG[#LOG+1] = s; emit('LOG', #LOG, s) end
KP.model = {capabilities=function() return {available=true} end,
  snapshot=function(id) if id~=PC then return nil,'no model' end return {id=model.id,model=model.model,creature=model.creature,base=model.base,effective=model.effective} end,
  resize=function(c,s) model.base=s; model.effective=eff0*s; return true end,
  restore=function(c) model.base=c.base; model.effective=c.effective; return true end}
if not CFG.no_camera then
  KP.camera = {capabilities=function() return {available=true, profile='windows-k1-gog'} end,
    snapshot=function()
      if cam.behavior ~= 'chase' then  -- lua-api.md: fields from distance down are nil unless chase
        return {behavior=cam.behavior, mode=cam.mode, pending_style=cam.pending_style, module=cam.module, camera=cam.camera,
                behavior_ptr=cam.behavior_ptr, behavior_vtable=cam.behavior_vtable} end
      local t={} for k,v in pairs(cam) do if type(v)=='table' then t[k]={unpack(v)} else t[k]=v end end return t end}
end
local timers, next_id = {}, 1
KP.registertimer = function(ms, name) timers[#timers+1] = {name=name, id=next_id}; next_id = next_id + 1; return next_id - 1 end
local NW = {call=function(name, ...)
  routines[name] = true
  local a = {...}
  if name=='GetFirstPC' then return PC
  elseif name=='GetIsObjectValid' then return a[1]==PC and 1 or 0
  elseif name=='GetIsDead' or name=='GetIsInCombat' or name=='GetIsInConversation' then return 0
  elseif name=='GetModuleFileName' then return 'danm14aa'
  elseif name=='GetArea' then return AREA
  elseif name=='GetLocalNumber' then return locals[a[2]] or 0
  elseif name=='SetLocalNumber' then locals[a[2]] = a[3]; return nil
  elseif name=='GetPosition' then return {x=105.676, y=96.464, z=0.996}
  elseif name=='GetFacing' then return 136.474
  elseif name=='SetCameraMode' then cam.mode = a[2]; return nil
  else error('sim: unexpected routine '..tostring(name)) end
end}
local FAKE_OS = {time=function() return now end, difftime=os.difftime}
local function mkenv()
  local e = setmetatable({}, {__index=_G}); e._G = e; e.kp = KP; e.nwscript = NW; e.os = FAKE_OS
  e.dofile = function(path)
    local real = path:match('model_scene%.lua$') and CFG.helper or (path:match('task7s2_scale%.lua$') and CFG.script) or error('sim: unexpected dofile '..path)
    local f = assert(loadfile(real)); setfenv(f, e); return f()
  end
  return e
end
local H, C = mkenv(), mkenv()   -- harness state, console state (separate, as live)
local function pump(n)
  for _ = 1, n do
    ticks = ticks + 1
    if ticks % CFG.tps == 0 then now = now + 1 end
    if CFG.drift and CFG.drift(ticks, cam, model) then end
    local keep = {}
    for _, t in ipairs(timers) do
      local fn = C[t.name]
      local ok, r = pcall(fn)
      if ok and r then keep[#keep+1] = t end
      if not ok then emit('TIMERERR', t.name, r) end
    end
    timers = keep
  end
end
local function run(env, code)
  local f, e = loadstring(code, '=step'); if not f then return false, 'compile: '..e end
  setfenv(f, env)
  local r = {pcall(f)}
  if not r[1] then return false, r[2] end
  return true, r[2], #r - 1
end
local STEPS = STEPLIST
local mark = 0
for _, s in ipairs(STEPS) do
  local k = s.k
  if k == 'assert' or k == 'lua' then
    local tries = 0
    while true do
      local ok, v = run(H, s.code)
      if not ok then emit('STEPFAIL', s.i, 'error: '..tostring(v)); goto done end
      if k == 'lua' then emit('LUA', s.i, v); break end
      if v == true then break end
      if not s.poll or tries > 3000 then emit('STEPFAIL', s.i, 'mismatch: '..tostring(v)); goto done end
      tries = tries + 1; pump(CFG.poll_ticks)
    end
    emit('STEPOK', s.i, ticks)
  elseif k == 'console' then
    local ok, v, n = run(C, s.code)
    if not ok or v ~= true or n ~= 1 then emit('STEPFAIL', s.i, 'console: '..tostring(v)..' n='..tostring(n)); goto done end
    emit('STEPOK', s.i, ticks)
  elseif k == 'ticks' then pump(s.n); emit('STEPOK', s.i, ticks)
  elseif k == 'mark' then mark = #LOG; emit('MARK', s.i, mark)
  elseif k == 'await' then
    local tries = 0
    local function count() local c = 0 for j = mark + 1, #LOG do if LOG[j]:find(s.sub, 1, true) then c = c + 1 end end return c end
    while s.min > 0 and count() < s.min and tries < 3000 do tries = tries + 1; pump(2) end
    emit('AWAIT', s.i, mark..':'..#LOG)
  else emit('STEPOK', s.i, ticks) end
end
::done::
for n in pairs(routines) do emit('ROUTINE', n) end
emit('END', ticks, now)
for _, l in ipairs(EVENTS) do io.write(l:gsub('\n', ' '), '\n') end
'''

def lua_str(s):
    n = 0
    while (']' + '=' * n + ']') in s: n += 1
    return '[' + '=' * n + '[' + s + ']' + '=' * n + ']'

AWAIT_SUB = {  # plain substring the sim waits on; exact bounds are then checked with the harness regex
    'calm_end': 'calm_end', 'calm_start': 'calm_start', 'armed': 'armed tiny='}

def sim_program(v1, cfg, drift_lua='nil'):
    items = []
    for s in v1['steps']:
        r = s['raw']; i = s['index']; d = r.get('do')
        if d in ('assert_lua', 'lua'):
            items.append('{k=%s,i=%d,code=%s,poll=%s}' % ("'assert'" if d == 'assert_lua' else "'lua'", i, lua_str(r['code']), 'true' if r.get('poll') else 'false'))
        elif d == 'console_command': items.append("{k='console',i=%d,code=%s}" % (i, lua_str(r['code'])))
        elif d == 'advance_ticks': items.append("{k='ticks',i=%d,n=%d}" % (i, r['ticks']))
        elif d == 'mark_log': items.append("{k='mark',i=%d}" % i)
        elif d == 'await_log':
            sub = next((v for k, v in AWAIT_SUB.items() if k in r['pattern']), '')
            items.append("{k='await',i=%d,min=%d,sub=%s}" % (i, r.get('minimum', 1), lua_str(sub if r.get('minimum', 1) > 0 else '')))
        else: items.append("{k='noop',i=%d}" % i)
    conf = '{helper=%s,script=%s,tps=%d,poll_ticks=%d,no_camera=%s,drift=%s}' % (
        lua_str(str(HELPER)), lua_str(str(SCRIPT)), cfg['tps'], cfg['poll_ticks'], 'true' if cfg.get('no_camera') else 'false', drift_lua)
    return SIM_LUA.replace('CONFIG', conf).replace('STEPLIST', '{' + ',\n'.join(items) + '}')

def run_sim(v1, name, cfg, drift_lua='nil'):
    r = subprocess.run([LUAJIT, '-'], input=sim_program(v1, cfg, drift_lua), capture_output=True, text=True, timeout=120)
    if r.returncode: raise SystemExit('sim %s crashed: %s' % (name, r.stderr))
    ev = [l.split('\t') for l in r.stdout.splitlines()]
    log = [e[2] for e in ev if e[0] == 'LOG']
    fails = [e for e in ev if e[0] in ('STEPFAIL', 'TIMERERR')]
    return ev, log, fails

def check_awaits(v1, ev, log):
    raw = {s['index']: s['raw'] for s in v1['steps']}
    for e in ev:
        if e[0] != 'AWAIT': continue
        r = raw[int(e[1])]; a, b = map(int, e[2].split(':'))
        n = sum(1 for l in log[a:b] if re.search(r['pattern'], l))
        lo, hi = r.get('minimum', 1), r.get('maximum')
        assert n >= lo and (hi is None or n <= hi), ('await_log bound', e[1], r.get('label'), n, lo, hi)


def recorder_order(log, tps):
    """Feed the simulated native log through the WT recorder's own marker observer."""
    path = HERE / ('sim-native-log-tps%d.txt' % tps)
    path.write_text(''.join('[running] info: [script] ' + l + '\n' for l in log))
    args = json.loads((HERE / 'launcher-args.json').read_text())['marker_args']
    code = ("import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,%r)\n"
            "from pathlib import Path\n"
            "from kpharness.creative import parser, marker_configuration\n"
            "from kpharness.recording import X11Recorder\n"
            "o=parser().parse_args(['--backend','linux-wine-k1-gamescope','--script','a.lua','--route','r.toml']+json.loads(sys.argv[1]))\n"
            "m,s,e=marker_configuration(o)\n"
            "r=X11Recorder(Path(sys.argv[3]),marker_pattern=o.marker,named_markers=m,cadence_start_marker=s,cadence_end_marker=e)\n"
            "r.started=0.0; r.observe(Path(sys.argv[2]),1.0)\n"
            "print(json.dumps({'order':r._marker_order_status(),'duplicates':r.marker_duplicates,'effect_start':r.marker['line'] if r.marker else None,"
            "'sequence':[(n,r.markers[n]['sequence']) for n in m if n in r.markers]}))\n") % str(HARNESS)
    r = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, json.dumps(args), str(path), str(HERE / 'sim-recorder-unused')],
                       capture_output=True, text=True, env={'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin'})
    if r.returncode: raise SystemExit('recorder order check failed: ' + r.stderr[-2000:])
    out = json.loads(r.stdout)
    assert out['order'] == 'ordered' and out['duplicates'] == [], out
    assert not (HERE / 'sim-recorder-unused').exists()
    return out

def sim(v1):
    order = [r'\[task7s2\] armed', r'\[task7s2\] calm_start$', r'phase=1 actor=1 base=0\.350', r'phase=2 actor=1 base=1\.900',
             r'phase=3 actor=1 base=1\.000', r'restored actors=1', r'complete phases=3 restored=1', r'camera_watch .* stable=1', r'\[task7s2\] calm_end$']
    total = len(v1['steps'])
    for tps in (10, 60):
        ev, log, fails = run_sim(v1, 'nominal', {'tps': tps, 'poll_ticks': max(1, tps // 3)})
        assert not fails, fails
        ok_steps = sum(1 for e in ev if e[0] in ('STEPOK', 'MARK', 'AWAIT'))
        assert ok_steps == total, (ok_steps, total)
        check_awaits(v1, ev, log)
        idx = [next(i for i, l in enumerate(log) if re.search(p, l)) for p in order]
        assert idx == sorted(idx), idx
        # timing receipts: callbacks between markers (ticks at LOG events are not emitted; count via STEPOK ticks)
        routines = sorted(e[1] for e in ev if e[0] == 'ROUTINE')
        end = [e for e in ev if e[0] == 'END'][0]
        say('SIM nominal tps=%d: all %d steps passed; marker order ok; await_log bounds ok; sim ticks=%s fake_seconds=%d'
            % (tps, total, end[1], int(end[2]) - 1000000))
        say('  log:', ' | '.join(l for l in log if 'task7s2' in l))
        say('  routines called via nwscript.call:', ', '.join(routines))
        ro = recorder_order(log, tps)
        say('  WT X11Recorder marker observer on this log: order=%s duplicates=%s sequence=%s' % (ro['order'], ro['duplicates'], ro['sequence']))
    # negative: raw_28 moves by 0.01 while giant (base 1.9)
    drift = "function(t, cam, model) if model.base > 1.5 and cam.raw_28_unverified[3] < 0.385 then cam.raw_28_unverified[3] = 0.39 end end"
    ev, log, fails = run_sim(v1, 'giant-drift', {'tps': 10, 'poll_ticks': 3}, drift)
    f = [e for e in ev if e[0] == 'STEPFAIL']
    assert f and 'camera moved' in f[0][2] and 'raw_28' in f[0][2], f
    say('SIM negative (raw_28 moves 0.01 during giant): route FAILS at step %s -> %s' % (f[0][1], f[0][2][:140]))
    watch = [l for l in log if 'camera_watch' in l]
    say('  scene-side watch line (not reached before failure, expected empty or stable=0):', watch or 'none')
    # negative: kp.camera missing (wrong build)
    ev, log, fails = run_sim(v1, 'no-camera', {'tps': 10, 'poll_ticks': 3, 'no_camera': True})
    f = [e for e in ev if e[0] == 'STEPFAIL']
    assert f and int(f[0][1]) == 5 and 'kp.camera missing' in f[0][2], f
    say('SIM negative (build without kp.camera): route FAILS at step %s (precondition, before any F12) -> %s' % (f[0][1], f[0][2][:100]))
    # settle: slow drift for the first 400 ticks after load, then still
    slow = "function(t, cam) if t < 1000 then cam.raw_28_unverified[4] = 0.92 + t*0.00002 end end"
    ev, log, fails = run_sim(v1, 'slow-settle', {'tps': 10, 'poll_ticks': 3}, slow)
    assert not fails, fails
    base = [e[2] for e in ev if e[0] == 'LUA' and ' r=' in e[2]][0]
    say('SIM settle (raw_28 drifts 2e-5/tick until tick 1000, then still): route passes; baseline receipt (lua step detail) ->', base)
    # slow drift that never stops must fail at the settle step
    never = "function(t, cam) cam.raw_28_unverified[4] = 0.92 + t*0.00002 end"
    ev, log, fails = run_sim(v1, 'never-settles', {'tps': 10, 'poll_ticks': 3}, never)
    f = [e for e in ev if e[0] == 'STEPFAIL']
    assert f and int(f[0][1]) == 8, f
    say('SIM negative (drift never stops, 2e-5/tick): route FAILS at settle step %s -> %s' % (f[0][1], f[0][2][:80]))



# ----------------------------------------------------------------- L1 (7)
def check_l1(v1, l1):
    raw = tomllib.loads(L1.read_text())
    assert 'NON-ACCEPTANCE' in raw['name'] and raw['settings']['shot_interval'] == 0 and raw['target'] == 'k1'
    assert not any(s['raw'].get('do') == 'console_command' for s in l1['steps'])
    shots = [s['index'] for s in l1['steps'] if s['raw'].get('screenshot') is True]
    assert len(shots) == 4, shots
    v1code = {s['index']: s['raw'].get('code') for s in v1['steps']}
    l1code = [s['raw'].get('code') for s in l1['steps']]
    reused = {5: 'precondition+camera library', 6: 'chase mode', 8: 'settle', 9: 'baseline', 14: '+180 stability'}
    for i, what in reused.items():
        assert l1code.count(v1code[i]) == 1, ('L1 must reuse V1 step', i, what)
    pos = {i: l1code.index(v1code[i]) + 1 for i in reused}
    assert pos[5] == 5 and pos[5] < pos[6] < pos[8] < pos[9] < pos[14], pos
    assert shots[0] < pos[8] and shots[1] < pos[8] and pos[9] < shots[2] < shots[3] < pos[14], (shots, pos)
    say('L1 Scenario.load: ok, steps=%d, console_command=0, stills at steps %s, shot_interval=0, name marks NON-ACCEPTANCE' % (len(l1['steps']), shots))
    say('  V1 chunks reused byte-identical: V1 step -> L1 step %s' % ', '.join('%d->%d' % (k, v) for k, v in sorted(pos.items())))
    args = json.loads((HERE / 'l1-launcher-args.json').read_text())
    assert args['env'] == {'KP_MAX_BOOT_ATTEMPTS': '1'} and '--dev-max-boot-attempts' not in args['args']
    code = ("import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,%r)\n"
            "from kpharness.creative import parser, marker_configuration\n"
            "o=parser().parse_args(json.loads(sys.argv[1]))\n"
            "m,s,e=marker_configuration(o);print(json.dumps({'markers':m,'start':s,'end':e,'marker':o.marker,'w':o.width,'h':o.height,'script':o.script}))\n") % str(HARNESS)
    r = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, json.dumps(args['args'])], capture_output=True, text=True, env={'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin'})
    if r.returncode: raise SystemExit('L1 launcher flag check failed: ' + r.stderr[-2000:])
    lo = json.loads(r.stdout)
    assert lo['markers'] == {'effect_start': lo['marker']} and lo['start'] is None and lo['end'] is None and (lo['w'], lo['h']) == (1024, 768), lo
    assert re.search(lo['marker'], '[l1cam] loaded camera=present') and re.search(lo['marker'], '[l1cam] loaded camera=absent')
    say('L1 launcher flags: creative parser ok, named markers=%s, cadence=%s..%s, %dx%d, --marker matches the probe load line' % (lo['markers'], lo['start'], lo['end'], lo['w'], lo['h']))
    total = len(l1['steps'])
    def records(ev): return [e[2] for e in ev if e[0] == 'LUA']
    def check_strings(name, ev):
        recs = records(ev)
        worst = max(len(x) for x in recs)
        assert worst <= 150 and not any(('"' in x or '\\' in x) for x in recs), (name, worst)
        return recs, worst
    # nominal
    ev, log, fails = run_sim(l1, 'l1-nominal', {'tps': 10, 'poll_ticks': 3})
    assert not fails, fails
    assert sum(1 for e in ev if e[0] in ('STEPOK', 'MARK', 'AWAIT')) == total
    recs, worst = check_strings('nominal', ev)
    say('SIM L1 nominal: all %d steps passed; %d lua receipts, longest %d chars; no quotes/backslashes' % (total, len(recs), worst))
    for x in recs:
        if x.startswith(('R1a', 'R1b', 'R1c', 'R1d', 'R1e', 'R1f', 'R2 vs', 'R4 vs')): say('  ' + x)
    # huge floats: worst-case record length
    big = ("function(t, cam) cam.distance=-1.23456789e+30; cam.speed=-1.23456789e+30; cam.pitch=-1.23456789e+30; cam.height=-1.23456789e+30; "
           "cam.base_distance=-1.23456789e+30; cam.base_view_angle=-1.23456789e+30; cam.dolly=4294967295; cam.style_row=-2147483648; cam.pending_style=-2147483648; "
           "cam.module='0xffffffff'; cam.camera='0xffffffff'; cam.behavior_ptr='0xffffffff'; cam.behavior_vtable='0xffffffff'; "
           "for i=1,4 do cam.raw_28_unverified[i]=-1.23456789e+30 end; for i=1,3 do cam.raw_38_unverified[i]=-1.23456789e+30; cam.raw_50_unverified[i]=-1.23456789e+30 end end")
    ev, log, fails = run_sim(l1, 'l1-huge', {'tps': 10, 'poll_ticks': 3}, big)
    recs, worst = check_strings('huge', ev)
    assert [int(x[1]) for x in fails] == [pos[8]] and len([x for x in recs if x[:2] in ('R1', 'R2')]) == 15, (fails, len(recs))
    say('SIM L1 huge values (-1.23456789e+30 in every float, 0xffffffff pointers, pending_style -2^31): all 15 R1/R2 receipts (2 takes, 12 records, 1 delta) recorded, longest %d chars (limit 150); '
        'then the settle rehearsal fails at step %d as it must (pending_style ~= -1)' % (worst, pos[8]))
    # no kp.camera
    ev, log, fails = run_sim(l1, 'l1-no-camera', {'tps': 10, 'poll_ticks': 3, 'no_camera': True})
    f = [e for e in ev if e[0] == 'STEPFAIL']
    assert f and int(f[0][1]) == 5 and 'kp.camera missing' in f[0][2], f
    say('SIM L1 negative (build without kp.camera): FAILS at step %s before any reading -> %s' % (f[0][1], f[0][2][:60]))
    # non-chase behaviour: readings recorded, then the settle rehearsal fails
    other = "function(t, cam) cam.behavior='other' end"
    ev, log, fails = run_sim(l1, 'l1-other', {'tps': 10, 'poll_ticks': 3}, other)
    f = [e for e in ev if e[0] == 'STEPFAIL']
    recs, worst = check_strings('other', ev)
    r1a = [x for x in recs if x.startswith('R1a')]
    assert f and int(f[0][1]) == pos[8] and r1a and 'beh=other' in r1a[0] and any(x.startswith('R2f') for x in recs), (f, recs[:3])
    say('SIM L1 non-chase behaviour: R1/R2 recorded (%s), then FAILS at settle rehearsal step %s (V1 would die at its step 8)' % (r1a[0][:40], f[0][1]))
    # pan between R1 and R2, still after
    pan = "function(t, cam) if t > 650 and t < 760 then cam.raw_28_unverified[3] = 0.38 + (t-650)*0.0001 end end"
    ev, log, fails = run_sim(l1, 'l1-pan', {'tps': 10, 'poll_ticks': 3}, pan)
    recs, worst = check_strings('pan', ev)
    d = [x for x in recs if x.startswith('R2 vs R1')]
    assert not fails and d and 'dq=0 ' not in d[0], (fails, d)
    say('SIM L1 pan during R1->R2 (raw_28 moves, then stops): route passes; delta receipt -> %s' % d[0])

# ----------------------------------------------------------------- postrun gate (8)
def check_postrun_gate():
    import importlib.util, shutil, struct, tempfile, zlib
    spec = importlib.util.spec_from_file_location('postrun_gate', HERE / 'postrun-gate.py')
    PG = importlib.util.module_from_spec(spec); spec.loader.exec_module(PG)
    def png(w, h):
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')
    def fixture(root, route, *, boot=None, env='1', drop=None, empty=None, wrong=None, ppm=None):
        run = root / 'run'; (run / 'shots').mkdir(parents=True)
        b = {'max_boot_attempts': 1, 'max_boot_attempts_source': 'kwarg', 'launch_count': 1, 'outcome': 'channel', 'attempts': [{'attempt': 1}]}
        b.update(boot or {})
        (run / 'boot-attempts.json').write_text(json.dumps(b))
        (run / 'creative-run.json').write_text(json.dumps({'boot_attempts': {'env': env, 'acceptance_eligible': True}}))
        steps = []
        for i, s in enumerate(tomllib.loads(route.read_text())['step'], 1):
            label = s.get('label', 'x')
            if s.get('screenshot') is True:
                n = len([x for x in steps if x.get('shot')]) + 1
                name = '%04d_%s.%s' % (n, 'still', 'ppm' if ppm == n else 'png')
                data = b'P6\n1024 768\n255\n' if ppm == n else png(*((800, 600) if wrong == n else (1024, 768)))
                path = run / 'shots' / name
                path.write_bytes(b'' if empty == n else data)
                steps.append({'index': i, 'step': label, 'status': 'ok', 'detail': 'no screenshot taken' if drop == n else str(path), 'shot': True})
            else:
                steps.append({'index': i, 'step': label, 'status': 'ok', 'detail': ''})
        (run / 'report.json').write_text(json.dumps({'steps': steps}))
        return run
    cases = [('pass (PNG stills)', {}, 'PASS'), ('pass (one PPM kept)', {'ppm': 2}, 'PASS'),
             ('still 2 not taken', {'drop': 2}, 'FAIL'), ('still 1 empty', {'empty': 1}, 'FAIL'),
             ('still 3 800x600', {'wrong': 3}, 'FAIL'), ('boot budget 5', {'boot': {'max_boot_attempts': 5}}, 'FAIL'),
             ('two launches', {'boot': {'launch_count': 2, 'attempts': [{}, {}]}}, 'FAIL'),
             ('KP_MAX_BOOT_ATTEMPTS unset', {'env': None}, 'FAIL')]
    for route in (V1, L1):
        got = []
        for name, kw, want in cases:
            if route == V1 and kw.get('drop', 0) > 3: continue
            tmp = pathlib.Path(tempfile.mkdtemp(prefix='gate-', dir=HERE))
            try:
                out = PG.gate(route, fixture(tmp, route, **kw), (1024, 768))
            finally:
                shutil.rmtree(tmp)
            assert out['verdict'] == want, (route.name, name, out)
            got.append('%s=%s' % (name, out['verdict']) + ('' if want == 'PASS' else ' (%s)' % out['problems'][0][:40]))
        say('postrun-gate %s: %s' % (route.name, '; '.join(got)))

# --------------------------------------------------------- postrun-gate --require-l1 (9)
def check_require_l1():
    """r3: closes round-2 review Finding I1. postrun-gate.py's F3 enforcement (§5b) is now
    mechanical: a V1-shaped acceptance check refuses, one line, nonzero exit, unless a prior
    passing L1 run is named and its own records (not just its cached receipt) hold up."""
    import shutil, struct, zlib
    GATE = HERE / 'postrun-gate.py'

    def png(w, h):
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')

    def fixture(root, route, *, name, started=1000.0, finished=1010.0, launch_started=None,
                build='BUILDX', route_sha256=None, admission=None, boot=None, env='1', ok=True,
                runtime=None):
        run = root / name; (run / 'shots').mkdir(parents=True)
        if launch_started is None: launch_started = started - 5.0
        b = {'max_boot_attempts': 1, 'max_boot_attempts_source': 'kwarg', 'launch_count': 1,
             'outcome': 'channel', 'attempts': [{'attempt': 1, 'started': launch_started, 'ended': started}]}
        b.update(boot or {})
        (run / 'boot-attempts.json').write_text(json.dumps(b))
        rs = sha(route) if route_sha256 is None else route_sha256
        if runtime is None: runtime = {'kphasor.dll': {'sha256': 'rt-' + build}}
        (run / 'creative-run.json').write_text(json.dumps(
            {'boot_attempts': {'env': env, 'acceptance_eligible': True}, 'route_source': {'sha256': rs},
             'runtime': runtime}))
        steps = []
        for i, s in enumerate(tomllib.loads(route.read_text())['step'], 1):
            label = s.get('label', 'x')
            if s.get('screenshot') is True:
                n = len([x for x in steps if x.get('shot')]) + 1
                p = run / 'shots' / ('%04d_still.png' % n)
                p.write_bytes(png(1024, 768))
                steps.append({'index': i, 'step': label, 'status': 'ok', 'detail': str(p), 'shot': True})
            else:
                steps.append({'index': i, 'step': label, 'status': 'ok', 'detail': ''})
        (run / 'report.json').write_text(json.dumps(
            {'scenario': route.stem, 'build': build, 'started': started, 'finished': finished,
             'ok': ok, 'steps': steps}))
        if admission is not None:
            (run / 'admission.json').write_text(json.dumps(admission))
        return run

    def run_cli(route, run_dir, require_l1=None):
        cmd = [sys.executable, '-I', '-S', '-B', str(GATE), '--route', str(route), '--run-dir', str(run_dir)]
        if require_l1 is not None: cmd += ['--require-l1', str(require_l1)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    good_admission = {
        'beh_r1a': 'chase', 'ps_r1a': -1, 'beh_r3a': 'chase', 'ps_r3a': -1, 'dolly': [0.5, 0.5, 0.5, 0.5],
        'height_still3': 210, 'height_still4': 208,
        'feature_disp_3_4': {'dx': 1.0, 'dy': 0.5, 'row_span_delta': 0.5},
        'r4_vs_r3': {'idsame': 1, 'dcfg': 0.0, 'dq': 0.0, 'dp38': 0.0, 'dp50': 0.0},
        'feature_disp_1_2': {'dx': 6.0, 'dy': 0.2, 'row_span_delta': 0.5},
        'r2_vs_r1': {'idsame': 1, 'dcfg': 0.0, 'dq': 0.02, 'dp38': 0.01, 'dp50': 0.0},
    }

    # A fixed (not random-suffixed) scratch directory: one of the negative cases below lets a
    # real OSError string (which embeds the failing path) reach validation-output.txt, and that
    # output must stay byte-identical across reruns, the same as every other check in this file.
    root = HERE / '.reql1-scratch'
    if root.exists(): shutil.rmtree(root)
    root.mkdir()
    got = []
    try:
        # RED FIRST: reproduce round-2 review Finding I1 against the pre-r3 gate: a V1 run with
        # zero L1 trace anywhere still PASSes.
        pre_gate = HERE / 'postrun-gate.py.pre-r3'
        v1_only = fixture(root, V1, name='red-v1-only', started=2000.0, build='BUILDX')
        r = subprocess.run([sys.executable, '-I', '-S', '-B', str(pre_gate),
                             '--route', str(V1), '--run-dir', str(v1_only)], capture_output=True, text=True)
        assert r.returncode == 0 and json.loads(r.stdout)['verdict'] == 'PASS', ('red-first must reproduce the bug', r.returncode, r.stdout)
        got.append('RED-FIRST pre-r3 (V1, no L1 anywhere)=PASS exit 0 <- the bug Finding I1 found')
        # Same directory, r3 gate, no --require-l1: must now REFUSE (the direct green-first pair,
        # not just a lookalike case built separately below).
        rc, out, err = run_cli(V1, v1_only)
        assert rc != 0 and out.startswith('REFUSE:'), ('r3 gate on the exact same v1_only dir must REFUSE', rc, out)
        got.append('GREEN, same dir, r3 (V1, no L1 anywhere)=%s (exit %d)' % (out, rc))

        # 1. well-formed pair: L1 passes its own gate, then V1 accepts it.
        l1_good = fixture(root, L1, name='good-l1', started=1000.0, finished=1010.0, admission=good_admission)
        rc, out, err = run_cli(L1, l1_good)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('L1 fixture itself must PASS its own gate', rc, out, err)
        v1_good = fixture(root, V1, name='good-v1', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_good, require_l1=l1_good)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('well-formed L1/V1 pair should PASS', rc, out, err)
        got.append('well-formed pair=PASS exit 0')

        # 2. V1 with no --require-l1 at all must REFUSE, one line, nonzero exit (not silently skip).
        v1_noflag = fixture(root, V1, name='v1-noflag', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_noflag)
        assert rc != 0 and out.startswith('REFUSE:') and '\n' not in out, ('missing --require-l1 must refuse, one line', rc, out)
        got.append('no --require-l1=%s (exit %d)' % (out, rc))

        # 3. L1 failed its own gate (a dropped still) -> REFUSE.
        l1_failed = fixture(root, L1, name='l1-failed', started=1000.0, finished=1010.0, admission=good_admission)
        # break it: overwrite report.json so still step 10 reports "no screenshot taken"
        rep = json.loads((l1_failed / 'report.json').read_text())
        for s in rep['steps']:
            if s.get('shot') and s['index'] == 10: s['detail'] = 'no screenshot taken'
        (l1_failed / 'report.json').write_text(json.dumps(rep))
        rc, out, err = run_cli(L1, l1_failed)
        assert rc != 0 and json.loads(out)['verdict'] == 'FAIL', ('sanity: broken L1 fixture must FAIL its own gate', rc, out)
        v1_vs_failed = fixture(root, V1, name='v1-vs-l1-failed', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_vs_failed, require_l1=l1_failed)
        assert rc != 0 and out.startswith('REFUSE:') and 'gate did not pass' in out, ('L1 that failed its own gate must REFUSE V1', rc, out)
        got.append('L1 failed its own gate=%s (exit %d)' % (out, rc))

        # 4. Wrong L1 route hash (only the recorded route_source.sha256 is wrong) -> REFUSE.
        l1_wronghash = fixture(root, L1, name='l1-wronghash', started=1000.0, finished=1010.0,
                                admission=good_admission, route_sha256='deadbeef' * 8)
        rc, out, err = run_cli(L1, l1_wronghash)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('sanity: only route hash is wrong; L1 gate itself must still PASS', rc, out)
        v1_vs_wronghash = fixture(root, V1, name='v1-vs-wronghash', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_vs_wronghash, require_l1=l1_wronghash)
        assert rc != 0 and out.startswith('REFUSE:') and 'route hash' in out, ('wrong L1 route hash must REFUSE V1', rc, out)
        got.append('wrong L1 route hash=%s (exit %d)' % (out, rc))

        # 5. L1 launch_count 2, discovered only by re-reading boot-attempts.json directly: the
        #    gate receipt itself still says PASS (written honestly, before the file changed), so
        #    this proves the check re-derives rather than trusting the cached receipt.
        l1_relaunch = fixture(root, L1, name='l1-relaunch', started=1000.0, finished=1010.0, admission=good_admission)
        rc, out, err = run_cli(L1, l1_relaunch)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('sanity: L1 fixture must PASS before tampering', rc, out)
        boot = json.loads((l1_relaunch / 'boot-attempts.json').read_text())
        boot['launch_count'] = 2
        boot['attempts'] = boot['attempts'] * 2
        (l1_relaunch / 'boot-attempts.json').write_text(json.dumps(boot))
        receipt = json.loads((l1_relaunch / 'postrun-gate-result.json').read_text())
        assert receipt['verdict'] == 'PASS', ('sanity: receipt must still read PASS, cached from before the tamper', receipt)
        v1_vs_relaunch = fixture(root, V1, name='v1-vs-relaunch', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_vs_relaunch, require_l1=l1_relaunch)
        assert rc != 0 and out.startswith('REFUSE:') and 'launch_count' in out, ('L1 launch_count=2 must REFUSE V1 even with a stale PASS receipt', rc, out)
        got.append('L1 launch_count=2 (stale PASS receipt)=%s (exit %d)' % (out, rc))

        # 6. L1 finished after V1 started (timestamps from run records) -> REFUSE.
        l1_late = fixture(root, L1, name='l1-late', started=5000.0, finished=5010.0, admission=good_admission)
        rc, out, err = run_cli(L1, l1_late)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('sanity: late-L1 fixture must PASS its own gate', rc, out)
        v1_early = fixture(root, V1, name='v1-early', started=100.0, finished=200.0, launch_started=95.0)
        rc, out, err = run_cli(V1, v1_early, require_l1=l1_late)
        assert rc != 0 and out.startswith('REFUSE:') and ('start' in out or 'happen' in out), ('L1 after V1 must REFUSE', rc, out)
        got.append('L1 after V1 started=%s (exit %d)' % (out, rc))

        # 7-11: check_admission()/check_build_match() have no negative-path coverage yet without
        # these -- each varies exactly one field off the well-formed admission.json, through the
        # real CLI, and asserts the A-code named in the REFUSE reason.
        def adm_with(**overrides):
            a = json.loads(json.dumps(good_admission))
            for k, v in overrides.items(): a[k] = v
            return a

        # 7. A3: still 3 height is a real, plausible, out-of-band measurement (the RUN/CAL 0006
        #    view, 272px -- exactly Grill me #2's "L1 just moves the failure one launch earlier").
        l1_a3 = fixture(root, L1, name='l1-a3', started=1000.0, finished=1010.0, admission=adm_with(height_still3=272))
        rc, out, err = run_cli(L1, l1_a3)
        assert rc == 0 and json.loads(out)['verdict'] == 'PASS', ('sanity: L1 gate itself only checks stills/boot, not admission', rc, out)
        v1_a3 = fixture(root, V1, name='v1-a3', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_a3, require_l1=l1_a3)
        assert rc != 0 and out.startswith('REFUSE:') and 'A3' in out, ('out-of-band still 3 height must REFUSE via A3', rc, out)
        got.append('admission A3 (height 272px, out of 192-230 band)=%s (exit %d)' % (out, rc))

        # 8. A4: a negative dx (feature moved -10px) must trip the >4px band; an unsigned check
        #    would let this through, since -10 < 4.
        l1_a4 = fixture(root, L1, name='l1-a4', started=1000.0, finished=1010.0,
                         admission=adm_with(feature_disp_3_4={'dx': -10.0, 'dy': 0.0, 'row_span_delta': 0.0}))
        run_cli(L1, l1_a4)
        v1_a4 = fixture(root, V1, name='v1-a4', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_a4, require_l1=l1_a4)
        assert rc != 0 and out.startswith('REFUSE:') and 'A4' in out, ('negative dx=-10 must still trip the 4px band via abs(), REFUSE via A4', rc, out)
        got.append('admission A4 (dx=-10px, sign must not hide it)=%s (exit %d)' % (out, rc))

        # 9. A4: a NaN in the R4-vs-R3 delta must not silently satisfy "<= 1e-4" (NaN compares
        #    False against every ordering, which would otherwise let it through).
        l1_a4nan = fixture(root, L1, name='l1-a4nan', started=1000.0, finished=1010.0,
                            admission=adm_with(r4_vs_r3={'idsame': 1, 'dcfg': 0.0, 'dq': float('nan'), 'dp38': 0.0, 'dp50': 0.0}))
        run_cli(L1, l1_a4nan)
        v1_a4nan = fixture(root, V1, name='v1-a4nan', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_a4nan, require_l1=l1_a4nan)
        assert rc != 0 and out.startswith('REFUSE:') and 'A4' in out, ('NaN dq must not pass the equality rule, REFUSE via A4', rc, out)
        got.append('admission A4 (dq=NaN, must not pass "<=1e-4")=%s (exit %d)' % (out, rc))

        # 10. Missing admission.json entirely -> REFUSE (distinct from a failed admission rule).
        l1_noadm = fixture(root, L1, name='l1-noadm', started=1000.0, finished=1010.0)
        run_cli(L1, l1_noadm)
        v1_noadm = fixture(root, V1, name='v1-noadm', started=2000.0, finished=2100.0)
        rc, out, err = run_cli(V1, v1_noadm, require_l1=l1_noadm)
        assert rc != 0 and out.startswith('REFUSE:') and 'admission.json unreadable' in out, ('missing admission.json must REFUSE', rc, out)
        got.append('missing admission.json=%s (exit %d)' % (out, rc))

        # 11. A6: L1 and V1 deployed a different runtime file (build mismatch), via the
        #     runner-recorded creative-run.json 'runtime' hashes, not session.build.
        l1_a6 = fixture(root, L1, name='l1-a6', started=1000.0, finished=1010.0, admission=good_admission,
                         runtime={'kphasor.dll': {'sha256': 'aaaa'}})
        run_cli(L1, l1_a6)
        v1_a6 = fixture(root, V1, name='v1-a6', started=2000.0, finished=2100.0,
                         runtime={'kphasor.dll': {'sha256': 'bbbb'}})
        rc, out, err = run_cli(V1, v1_a6, require_l1=l1_a6)
        assert rc != 0 and out.startswith('REFUSE:') and 'A6' in out, ('mismatched runtime hash must REFUSE via A6', rc, out)
        got.append('admission A6 (runtime hash mismatch = different build)=%s (exit %d)' % (out, rc))
    finally:
        shutil.rmtree(root)
    for line in got: say('require-l1:', line)

if __name__ == '__main__':
    main()
