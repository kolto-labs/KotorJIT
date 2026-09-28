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
"""
import hashlib, json, os, pathlib, re, subprocess, sys, tomllib

HERE = pathlib.Path(__file__).resolve().parent
WT = pathlib.Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
HARNESS = WT / 'scripts/harness'
HELPER = pathlib.Path('/home/brunner56/kp-live-20260922/frozen-model-393f68d/model_scene.lua')
LUAJIT = '/run/host/usr/bin/luajit'
V1 = HERE / 'task7s2-v1-readonly-camera.toml'
V2 = HERE / 'task7s2-v2-stage2-PLACEHOLDER.toml'
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
    for p in (V1, V2, SCRIPT, HELPER, HERE / 'generate-route.py', HERE / 'launcher-args.json', HERE / 'framing-fit.py'):
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
    for label, text in chunks: luajit_compile(label, text)
    say('LuaJIT compile (Lua 5.1 syntax): ok, chunks=%d (%s)' % (len(chunks), subprocess.run([LUAJIT, '-v'], capture_output=True, text=True).stdout.strip()))
    # 5
    hits, used, n = nwscript_scan(chunks + [('model_scene.lua (frozen)', HELPER.read_text())])
    assert not hits, hits
    say('NWScript-name scan vs %d K1 routines: no bare routine names; routines reached only via nwscript.call: %s' % (n, ', '.join(used)))
    # 6
    sim(v1)
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
    snapshot=function() local t={} for k,v in pairs(cam) do if type(v)=='table' then t[k]={unpack(v)} else t[k]=v end end return t end}
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

if __name__ == '__main__':
    main()
