#!/usr/bin/env python3
"""L1 camera diagnostic route (CP §2h). NON-ACCEPTANCE. PREP ONLY.

Writes, only into this directory:
  l1-camera-diagnostic.toml   one-launch diagnostic route; no F12, no acceptance media
  l1-launcher-args.json       proposed creative-runner flags (no capture markers, no cadence)

It reuses V1's own chunks (precondition + camera library, chase-mode step, settle,
baseline, +180 stability check) by importing generate-route.py, and asserts that
each reused chunk is byte-identical to the code in task7s2-v1-readonly-camera.toml.
So the settle rehearsal here tests exactly what V1 step 8 will run.
It does not rewrite V1, V2 or launcher-args.json.
"""
import importlib.util, json, pathlib, re, sys, tomllib

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('t7gen', HERE / 'generate-route.py')
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)   # module-level asserts only; main() not run
V1 = tomllib.loads((HERE / 'task7s2-v1-readonly-camera.toml').read_text())
V1_CODES = {i + 1: s.get('code') for i, s in enumerate(V1['step'])}
STABLE_180 = "return t7_stable('pre-marker +180 ticks')"
# byte-identity with the reviewed V1 route (step numbers are V1's)
assert V1_CODES[5] == G.PRECONDITION, 'V1 step 5 drifted'
assert V1_CODES[6] == G.CAMERA_MODE, 'V1 step 6 drifted'
assert V1['step'][6] == {'do': 'advance_ticks', 'ticks': 600, 'timeout': 180}, 'V1 step 7 drifted'
assert V1_CODES[8] == G.SETTLE, 'V1 step 8 drifted'
assert V1_CODES[9] == G.BASELINE, 'V1 step 9 drifted'
assert V1_CODES[14] == STABLE_180, 'V1 step 14 drifted'

PROBE = 'l1_camera_probe.lua'
LOAD_MARKER = r'\[l1cam\] loaded camera='

# Harness-state library. Readings are stored at full precision; record steps format them
# with %.9g (round-trips any IEEE single) into strings short enough to survive
# report.json's 200-character detail cut ('lua -> {"values": ["' is 20 of them).
L1LIB = (
 "L1={}; L1K={'behavior','mode','pending_style','module','camera','behavior_ptr','behavior_vtable','distance','speed','pitch','height','dolly','base_distance','base_view_angle','style_row'}; "
 "L1CFG={'distance','speed','pitch','height','base_distance','base_view_angle'}; L1ID={'behavior','mode','pending_style','module','camera','behavior_ptr','dolly','style_row'}; "
 "function l1_g(x) if type(x)=='number' then return ('%.9g'):format(x) end; return tostring(x) end; "
 "function l1_take(tag) local q=nwscript.call; local p=q('GetFirstPC'); local v=q('GetPosition',p); "
 "local r={t=os.time(),pc={x=v.x,y=v.y,z=v.z,f=q('GetFacing',p)}}; local ok,c,msg,code=pcall(kp.camera.snapshot); "
 "if not ok then r.err='pcall '..tostring(c) elseif not c then r.err=tostring(code)..' '..tostring(msg) else local s={}; for _,k in ipairs(L1K) do s[k]=c[k] end; "
 "for _,k in ipairs{'raw_28_unverified','raw_38_unverified','raw_50_unverified'} do local t=c[k]; if t then s[k]={t[1],t[2],t[3],t[4]} end end; r.c=s end; "
 "L1[tag]=r; return r end; "
 "function l1_geo(r,k) local v=r.c and r.c[k]; if not v then return 'nil','nil' end; local dx,dy=v[1]-r.pc.x,v[2]-r.pc.y; return l1_g(math.sqrt(dx*dx+dy*dy)),l1_g(v[3]-r.pc.z) end; "
 "function l1_part(r,part) local c=r.c; if part=='e' then return ('pc=%s,%s,%s f=%s t=%d'):format(l1_g(r.pc.x),l1_g(r.pc.y),l1_g(r.pc.z),l1_g(r.pc.f),r.t) end; "
 "if not c then return 'snapshot failed: '..tostring(r.err):sub(1,120) end; "
 "if part=='a' then return ('beh=%s mode=%s ps=%s dolly=%s sr=%s vt=%s bp=%s cam=%s mod=%s'):format(tostring(c.behavior),l1_g(c.mode),l1_g(c.pending_style),l1_g(c.dolly),l1_g(c.style_row),tostring(c.behavior_vtable),tostring(c.behavior_ptr),tostring(c.camera),tostring(c.module)) end; "
 "if part=='b' then return ('d=%s s=%s pi=%s h=%s bd=%s fov=%s'):format(l1_g(c.distance),l1_g(c.speed),l1_g(c.pitch),l1_g(c.height),l1_g(c.base_distance),l1_g(c.base_view_angle)) end; "
 "local q,p,p2=c.raw_28_unverified or {},c.raw_38_unverified or {},c.raw_50_unverified or {}; "
 "if part=='c' then return ('q28=%s,%s,%s,%s'):format(l1_g(q[1]),l1_g(q[2]),l1_g(q[3]),l1_g(q[4])) end; "
 "if part=='d' then return ('p38=%s,%s,%s p50=%s,%s,%s'):format(l1_g(p[1]),l1_g(p[2]),l1_g(p[3]),l1_g(p2[1]),l1_g(p2[2]),l1_g(p2[3])) end; "
 "local r38,z38=l1_geo(r,'raw_38_unverified'); local r50,z50=l1_geo(r,'raw_50_unverified'); "
 "return ('r38=%s dz38=%s r50=%s dz50=%s'):format(r38,z38,r50,z50) end; "
 "function l1_rec(tag,part) local ok,s=pcall(function() local r=L1[tag]; if not r then return 'no reading' end; return l1_part(r,part) end); "
 "return tag..part..' '..(ok and s or ('record error: '..tostring(s):sub(1,120))) end; "
 "function l1_maxd(a,b,n) if not (a and b) then return nil end; local m=0; for i=1,n do if not (a[i] and b[i]) then return nil end; m=math.max(m,math.abs(a[i]-b[i])) end; return m end; "
 "function l1_delta(a,b) local ok,s=pcall(function() local A,B=L1[a],L1[b]; if not (A and B and A.c and B.c) then return 'n/a (snapshot missing)' end; "
 "local same=1; for _,k in ipairs(L1ID) do if A.c[k]~=B.c[k] then same=0 end end; local dc=0; for _,k in ipairs(L1CFG) do if A.c[k] and B.c[k] then dc=math.max(dc,math.abs(A.c[k]-B.c[k])) else dc=nil; break end end; "
 "local f=function(x) return x and ('%.4g'):format(x) or 'nil' end; "
 "return ('idsame=%d dcfg=%s dq=%s dp38=%s dp50=%s dpc=%s df=%s dt=%d'):format(same,f(dc),f(l1_maxd(A.c.raw_28_unverified,B.c.raw_28_unverified,4)),"
 "f(l1_maxd(A.c.raw_38_unverified,B.c.raw_38_unverified,3)),f(l1_maxd(A.c.raw_50_unverified,B.c.raw_50_unverified,3)),"
 "f(l1_maxd({A.pc.x,A.pc.y,A.pc.z},{B.pc.x,B.pc.y,B.pc.z},3)),f(math.abs(A.pc.f-B.pc.f)),B.t-A.t) end); "
 "return b..' vs '..a..' '..(ok and s or ('delta error: '..tostring(s):sub(1,120))) end; "
 "return true")

TAKE = "local ok,r=pcall(l1_take,%r); if not ok then return %r..' take error: '..tostring(r):sub(1,120) end; return %r..' taken '..(r.err and ('ERR '..r.err:sub(1,100)) or 'ok')"
PARTS = 'abcdef'

def build():
    steps = []
    def add(**s): steps.append(s)
    def check(label, code, **kw): add(label=label, do='assert_lua', code=code, equals=True, **kw)
    def take(tag): add(do='lua', label='L1 reading %s (snapshot + PC pose, stored in harness state)' % tag, code=TAKE % (tag, tag, tag))
    def still(n, what): add(screenshot=True, label='L1 still %d: %s' % (n, what))
    def records(tag):
        for part in PARTS:
            add(do='lua', label='L1 record %s%s' % (tag, part), code='return l1_rec(%r,%r)' % (tag, part))
    def delta(a, b): add(do='lua', label='L1 delta %s vs %s' % (b, a), code='return l1_delta(%r,%r)' % (a, b))
    # V1 steps 1-7, same verbs and same code (asserted above); the library step has no game effect.
    add(do='load_save', dir='000001 - AUTOSAVE', timeout=600)
    add(wait='phase', equals='gameplay', timeout=600)
    add(do='clear_auto_pause')
    add(do='advance_dialog', until='gameplay', timeout=120)
    check('V1 step 5 (verbatim): peaceful danm14aa, kp.camera present and available, original scale; fails early on a build without kp.camera', G.PRECONDITION)
    check('L1 harness library (no game effect)', L1LIB)
    check('V1 step 6 (verbatim): chase mode only', G.CAMERA_MODE)
    add(do='advance_ticks', ticks=600, timeout=180)
    # CP §2h pair: recorded before any step that can fail on camera state.
    take('R1'); still(1, 'mode 2 +600 ticks')
    add(do='advance_ticks', ticks=180, timeout=60)
    take('R2'); still(2, 'mode 2 +780 ticks')
    records('R1'); records('R2'); delta('R1', 'R2')
    # V1 settle and baseline rehearsal (verbatim). A timeout here means V1 would die at its step 8.
    check('V1 step 8 rehearsal (verbatim settle)', G.SETTLE, poll=True, timeout=G.SETTLE_TIMEOUT)
    check('V1 step 9 rehearsal (verbatim baseline)', G.BASELINE)
    # V1 still A/B timing.
    take('R3'); still(3, 'after settle, V1 still A timing')
    add(do='advance_ticks', ticks=180, timeout=60)
    take('R4'); still(4, 'settle +180 ticks, V1 still B timing')
    records('R3'); records('R4'); delta('R3', 'R4')
    check('V1 step 14 rehearsal (verbatim +180 stability)', STABLE_180)
    return steps

def render(steps):
    head = ('# L1 CAMERA DIAGNOSTIC. NON-ACCEPTANCE. One launch (KP_MAX_BOOT_ATTEMPTS=1), no F12, no scale change.\n'
            '# Its media is never acceptance media. Generated by generate-l1.py; do not hand-edit.\n')
    text = head + 'name=' + G.value('L1 camera diagnostic, K1 danm14aa (NON-ACCEPTANCE, one launch, no F12)') + \
        '\ntarget="k1"\n[settings]\ngame_speed=1.0\nhang_seconds=90\ndefault_timeout=45\nload_timeout=600\nshot_interval=0\n'
    for s in steps: text += '\n[[step]]\n' + '\n'.join(k + '=' + G.value(v) for k, v in s.items()) + '\n'
    return text

def main():
    steps = build()
    text = render(steps)
    parsed = tomllib.loads(text)
    assert not any(s.get('do') == 'console_command' for s in parsed['step'])
    assert sum(1 for s in parsed['step'] if s.get('screenshot')) == 4
    (HERE / 'l1-camera-diagnostic.toml').write_text(text)
    (HERE / 'l1-launcher-args.json').write_text(json.dumps({
        'note': ('L1 NON-ACCEPTANCE diagnostic. Same launcher, backend, build, harness snapshot, stage, save and 1024x768 as V1, '
                 'with KP_MAX_BOOT_ATTEMPTS=1 in the driver environment and no --dev-max-boot-attempts. '
                 'Only --script l1_camera_probe.lua (no task7s2 or model_scene script), --route l1-camera-diagnostic.toml, '
                 'and --marker below. No --capture-marker and no --cadence-* flags, so there is no cadence window.'),
        'env': {'KP_MAX_BOOT_ATTEMPTS': '1'},
        'args': ['--backend', 'linux-wine-k1-gamescope', '--target', 'k1', '--script', PROBE,
                 '--route', 'l1-camera-diagnostic.toml', '--width', '1024', '--height', '768',
                 '--capture-fps', '60', '--boot-timeout', '120', '--marker', LOAD_MARKER]}, indent=2) + '\n')
    print(json.dumps({'l1-camera-diagnostic.toml': len(steps)}))

if __name__ == '__main__':
    main()
