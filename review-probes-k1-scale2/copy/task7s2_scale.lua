-- Task 7 attempt 2 (K1): calm normal -> tiny -> giant -> restored normal on the PC.
-- PREP ONLY. Not run. Deployed next to the frozen model_scene.lua helper.
--
-- Inert when the host autoloads it: it defines no events, touches no game state
-- and starts no timer at load. It is driven by exactly three physical F12
-- console submissions (see the route):
--   task7s2=dofile('kotorphasor/scripts/task7s2_scale.lua');return task7s2.construct{tiny=0.35,giant=1.9}
--   return task7s2.arm()
--   return task7s2.cleanup()
--
-- Engine access: kp.* native facilities and nwscript.call(<routine>, ...) only.
-- No routine is exposed or called under any other name.
--
-- Native log markers (one line each, in this order; the cadence window is
-- [calm_start, calm_end], and it opens only after the console is closed):
--   [task7s2] camera_construct dist=.. pitch=.. height=.. q=.. p=..   (before the marker)
--   [task7s2] armed tiny=0.350 giant=1.900
--   [task7s2] calm_start               calm normal lead-in begins
--   [model-scene:task7s2] phase=1 actor=1 base=0.350 ...   tiny
--   [model-scene:task7s2] phase=2 actor=1 base=<giant> ... giant
--   [model-scene:task7s2] phase=3 actor=1 base=1.000 ...   normal again
--   [model-scene:task7s2] restored actors=1 holding-original-scale
--   [model-scene:task7s2] complete phases=3 restored=1
--   [task7s2] camera_watch samples=N max_q=.. max_p=.. cfg_changed=0 failures=0 stable=1
--   [task7s2] calm_end                 restored lead-out ends
-- The camera watch is log-only. It never changes scale behaviour; the route
-- asserts on its line. The route also samples the camera independently.

local M = {}

local NAME = "task7s2"
local GIANT_MAX = 2.0
-- Camera watch tolerances. The route generator asserts these equal its own.
local Q_TOL = 0.001      -- raw_28 component, about 0.11 deg, about 1.5 px at 55 deg FOV
local P_TOL = 0.01       -- raw_38/raw_50 component, about 1.2 px at 6.25 units
local CFG_TOL = 0.0001   -- distance/speed/pitch/height/base_* (bit-stable expected)
-- Timing floors. Callbacks are timer pumps (one per frame at most); seconds use
-- os.time (1 s resolution), so N here guarantees at least N-1 real seconds.
local CALM_CALLBACKS, CALM_SECONDS = 180, 4  -- arm -> calm_start (console closed first)
local LEAD_CALLBACKS, LEAD_SECONDS = 120, 3  -- calm_start -> phase 1 (>= 2 s calm normal)
local OUT_CALLBACKS, OUT_SECONDS = 120, 3    -- complete -> calm_end (>= 2 s restored)
local TIMER_MS = 16
local HOLD = 60                              -- model_scene hold_ticks, as reviewed
local TRIGGER_SLOT, TRIGGER = 5, 1           -- model_scene trigger contract

M.constants = {giant_max=GIANT_MAX, q_tol=Q_TOL, p_tol=P_TOL, cfg_tol=CFG_TOL,
  calm_callbacks=CALM_CALLBACKS, calm_seconds=CALM_SECONDS,
  lead_callbacks=LEAD_CALLBACKS, lead_seconds=LEAD_SECONDS,
  out_callbacks=OUT_CALLBACKS, out_seconds=OUT_SECONDS,
  timer_ms=TIMER_MS, hold=HOLD}

local S = nil  -- run state, created by construct()

local function log(text) kp.print("["..NAME.."] "..text) end
local function call(name, ...) return nwscript.call(name, ...) end
local function helper_path()
  local src = debug.getinfo(1, "S").source
  local dir = src:sub(1, 1) == "@" and src:sub(2):match("^(.*[/\\])") or nil
  return (dir or "kotorphasor/scripts/").."model_scene.lua"
end

-- Plain-table copy of a chase capture, or nil + reason. Never raises.
local function camera_read()
  if not (kp.camera and kp.camera.snapshot) then return nil, "kp.camera missing" end
  local c, msg, code = kp.camera.snapshot()
  if not c then return nil, "snapshot "..tostring(code)..": "..tostring(msg) end
  if c.behavior ~= "chase" then return nil, "behavior "..tostring(c.behavior) end
  return {mode=c.mode, pending_style=c.pending_style, module=c.module, camera=c.camera,
    behavior_ptr=c.behavior_ptr, distance=c.distance, speed=c.speed, pitch=c.pitch,
    height=c.height, dolly=c.dolly, style_row=c.style_row, base_distance=c.base_distance,
    base_view_angle=c.base_view_angle, q=c.raw_28_unverified, p=c.raw_38_unverified,
    p2=c.raw_50_unverified}
end

-- Returns cfg_same, max orientation delta, max position delta.
local function camera_delta(a, b)
  local same = true
  for _, k in ipairs{"mode", "pending_style", "module", "camera", "behavior_ptr", "dolly", "style_row"} do
    if a[k] ~= b[k] then same = false end
  end
  for _, k in ipairs{"distance", "speed", "pitch", "height", "base_distance", "base_view_angle"} do
    if math.abs(a[k] - b[k]) > CFG_TOL then same = false end
  end
  local mq, mp = 0, 0
  for i = 1, 4 do mq = math.max(mq, math.abs(a.q[i] - b.q[i])) end
  for i = 1, 3 do mp = math.max(mp, math.abs(a.p[i] - b.p[i]), math.abs(a.p2[i] - b.p2[i])) end
  return same, mq, mp
end

local function watch()
  local ok, err = pcall(function()
    local c, why = camera_read()
    local w = S.watch
    w.samples = w.samples + 1
    if not c then w.failures = w.failures + 1; w.last_failure = why; return end
    if not w.ref then w.ref = c; return end
    local same, mq, mp = camera_delta(w.ref, c)
    if not same then w.cfg_changed = w.cfg_changed + 1 end
    if mq > w.max_q then w.max_q = mq end
    if mp > w.max_p then w.max_p = mp end
  end)
  if not ok then S.watch.failures = S.watch.failures + 1; S.watch.last_failure = tostring(err) end
end

local function watch_line()
  local w = S.watch
  local stable = w.ref ~= nil and w.failures == 0 and w.cfg_changed == 0
    and w.max_q <= Q_TOL and w.max_p <= P_TOL
  log(("camera_watch samples=%d max_q=%.6f max_p=%.6f cfg_changed=%d failures=%d stable=%d%s"):format(
    w.samples, w.max_q, w.max_p, w.cfg_changed, w.failures, stable and 1 or 0,
    w.last_failure and (" last_failure="..w.last_failure) or ""))
end

local function elapsed(since) return os.difftime(os.time(), since) end

-- One timer callback. Returns true to keep the timer, false to stop it.
local function step()
  S.n = S.n + 1
  if S.stage == "pre" then
    if S.n >= CALM_CALLBACKS and elapsed(S.t_arm) >= CALM_SECONDS then
      S.stage = "lead"; S.n = 0; S.t_stage = os.time()
      log("calm_start")
      watch()
    end
    return true
  end
  watch()
  if S.stage == "lead" then
    if S.n >= LEAD_CALLBACKS and elapsed(S.t_stage) >= LEAD_SECONDS then
      S.stage = "scene"; S.n = 0
      S.scene:tick()
    end
    return true
  end
  if S.stage == "scene" then
    S.scene:tick()
    if S.scene.state == "failed" then
      S.stage = "done"; watch_line(); log("scene_failed")
      return false
    end
    if S.scene.state == "complete" then S.stage = "out"; S.n = 0; S.t_stage = os.time() end
    return true
  end
  if S.stage == "out" then
    if S.n >= OUT_CALLBACKS and elapsed(S.t_stage) >= OUT_SECONDS then
      S.stage = "done"; watch_line(); log("calm_end")
      return false
    end
    return true
  end
  return false
end

-- Physical command 1. Builds the finite scene; changes no game state.
function M.construct(args)
  assert(S == nil, "already constructed")
  assert(type(args) == "table", "construct{tiny=,giant=} required")
  local tiny, giant = args.tiny, args.giant
  assert(type(tiny) == "number" and tiny > 0 and tiny < 1, "tiny must be in (0,1)")
  assert(type(giant) == "number" and giant > 1 and giant <= GIANT_MAX, "giant must be in (1,"..GIANT_MAX.."]")
  assert(kp.model.capabilities().available, "native model backend unavailable")
  assert(kp.camera and kp.camera.capabilities().available, "native camera snapshot unavailable")
  local pc = call("GetFirstPC")
  assert(call("GetIsObjectValid", pc) == 1, "no PC")
  local body = assert(kp.model.snapshot(pc))
  assert(math.abs(body.base - 1) < 0.001, "PC not at original base scale 1")
  local cam = assert(camera_read(), "camera not in chase behaviour")
  log(("camera_construct dist=%.4f pitch=%.4f height=%.4f speed=%.3g fov=%.4g dolly=%s row=%d q=%.4f,%.4f,%.4f,%.4f p=%.3f,%.3f,%.3f"):format(
    cam.distance, cam.pitch, cam.height, cam.speed, cam.base_view_angle, tostring(cam.dolly), cam.style_row,
    cam.q[1], cam.q[2], cam.q[3], cam.q[4], cam.p[1], cam.p[2], cam.p[3]))
  local scene = dofile(helper_path()).new{name=NAME, trigger=TRIGGER, hold_ticks=HOLD, spawn=false,
    scales={{tiny}, {giant}, {body.base}}}
  assert(scene.state == "waiting", "scene not waiting")
  S = {pc=pc, body=body, tiny=tiny, giant=giant, scene=scene, stage="built", n=0,
    local5=call("GetLocalNumber", pc, TRIGGER_SLOT),
    watch={samples=0, failures=0, cfg_changed=0, max_q=0, max_p=0}}
  return true
end

-- Physical command 2. Registers the timer and sets the trigger slot.
function M.arm()
  assert(S and S.stage == "built", "construct first, arm once")
  S.stage = "pre"; S.n = 0; S.t_arm = os.time()
  _G.task7s2_tick = function()
    local ok, keep = pcall(step)
    if not ok then log("error="..tostring(keep)); return false end
    return keep
  end
  S.timer = kp.registertimer(TIMER_MS, "task7s2_tick")
  call("SetLocalNumber", S.pc, TRIGGER_SLOT, TRIGGER)
  log(("armed tiny=%.3f giant=%.3f"):format(S.tiny, S.giant))
  return type(S.timer) == "number" and S.timer > 0
end

-- Physical command 3. Releases only scene-owned state.
function M.cleanup()
  assert(S and S.stage == "done", "scene not finished")
  assert(S.scene.state == "complete" and S.scene.phase == 3, "scene did not complete")
  S.scene:unload()
  call("SetLocalNumber", S.pc, TRIGGER_SLOT, S.local5)
  _G.task7s2_tick = nil
  S = nil
  return true
end

return M
