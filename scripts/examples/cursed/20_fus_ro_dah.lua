-- FUS RO DAH: every player hit is a Force shout.
--
-- Whoever the player attacks gets Force-pushed off their feet with a force
-- wave burst, a screen flash and a bark from the player. Every fifth hit is
-- a full shout: everything hostile within 10m is thrown at once.
--
-- Mechanism: OnCreatureAttacked is a live EventHandler callback; `creature`
-- is the victim and `attacker` the one who swung. EffectForcePushed is the
-- authored knockback (k_sp1_generic's Force Push), applied instantly. The
-- flash is SetGlobalFadeOut to white for a tenth of a second, then a fade
-- back in.
--
-- Oracle lines: "[cursed:shout] <victim> flung (#n)" / "[cursed:shout] FUS RO DAH: k flung"
-- Counter: local number 7 on the PC == pushes so far.
priority = 30

-- Inside an engine hook, GetIsEnemy(x, pc) answers 0 even for a creature that
-- is plainly hostile (verified live 2026-09-16: 1 from the harness state, 0
-- from inside OnRunScript for the same trooper), and GetIsDead is still 0
-- while the death script runs. Hooks therefore treat "not a party member"
-- as hostile and never gate on GetIsDead for the creature the hook is about.

local VFX_FORCE_WAVE = 3001
local VFX_WHIRLWIND = 1018
local BIG_EVERY = 5
local BIG_RADIUS = 10.0
local COUNTER_SLOT = 7

local function q(name, ...)
  if not kotor then return nil end
  local fn = kotor[name]
  if not fn then return nil end
  local ok, v = pcall(fn, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end
-- Distance from positions: GetDistanceBetween answered 99/oversized inside
-- hooks (the big shout and the airstrike found 0-1 targets in a ring of 6).
local function dist(a, b)
  local pa, pb = q("GetPosition", a), q("GetPosition", b)
  if type(pa) ~= "table" or type(pb) ~= "table" then return 99 end
  local dx, dy, dz = pa.x - pb.x, pa.y - pb.y, pa.z - pb.z
  return math.sqrt(dx * dx + dy * dy + dz * dz)
end

-- Arming: nothing fires until ARM_TICKS frames after a module/area load and
-- never while the player is in a conversation. Effects applied from a hook
-- during a load or a cutscene bark hung the client (verified 2026-09-16:
-- the client loop stopped at 100 frames with disguises applied during
-- Trask's tutorial bark). PC local number 5 == 1 publishes "armed".
local ARM_TICKS = 200
local armed_flag = false
local tick_count = 0
local function armed()
  if not armed_flag then return false end
  local pc = q("GetFirstPC")
  if not pc then return false end
  if yes(q("IsInConversation", pc)) then return false end
  return true
end
function OnTick(tick, relevant)
  if armed_flag then return end
  tick_count = tick_count + 1
  if tick_count >= ARM_TICKS then
    armed_flag = true
    local pc = q("GetFirstPC")
    if pc then q("SetLocalNumber", pc, 5, 1) end
    print("[cursed] armed")
  end
end
local function disarm()
  armed_flag = false; tick_count = 0
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, 0) end
end
function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end

local pushes = 0
local last_tick_push = {}

local function flash(r, g, b, hold)
  q("SetGlobalFadeOut", 0.0, 0.08, r, g, b)
  q("SetGlobalFadeIn", hold or 0.1, 0.35, 0.0, 0.0, 0.0)
end

local function fling(victim, pc)
  if not yes(q("GetIsObjectValid", victim)) or yes(q("GetIsDead", victim)) then return false end
  if victim == pc or yes(q("IsObjectPartyMember", victim)) then return false end
  local push = q("EffectForcePushed")
  local wave = q("EffectVisualEffect", VFX_WHIRLWIND)
  if push then q("ApplyEffectToObject", 0, push, victim, 0.0) end
  if wave then q("ApplyEffectToObject", 0, wave, victim, 0.0) end
  return true
end

function OnCreatureAttacked(creature, attacker, relevant)
  if not armed() then return end
  local pc = q("GetFirstPC")
  if not pc or attacker ~= pc then return end
  -- one push per victim per game-second: the attacked event can fire more
  -- than once for a single flurry.
  local now = q("GetTimeSecond") or 0
  if last_tick_push[creature] == now then return end
  last_tick_push[creature] = now

  if not fling(creature, pc) then return end
  pushes = pushes + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, pushes)
  local burst = q("EffectVisualEffect", VFX_FORCE_WAVE)
  if burst then q("ApplyEffectToObject", 0, burst, pc, 0.0) end
  flash(1.0, 1.0, 1.0)
  print(("[cursed:shout] %s flung (#%d)"):format(norm(q("GetName", creature)), pushes))

  if pushes % BIG_EVERY == 0 then
    local flung = 0
    local area = q("GetArea", pc)
    local o = q("GetFirstObjectInArea", area, 1)
    while o and yes(q("GetIsObjectValid", o)) do
      if o ~= creature and dist(pc, o) <= BIG_RADIUS and fling(o, pc) then
        flung = flung + 1
      end
      o = q("GetNextObjectInArea", area, 1)
    end
    if kp and kp.as then
      kp.as(pc, function() q("SpeakString", "FUS RO DAH!", 1) end)
    end
    flash(0.6, 0.8, 1.0, 0.2)
    print(("[cursed:shout] FUS RO DAH: %d flung"):format(flung))
  end
end
