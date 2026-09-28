-- Bullet time: get hurt, and the world slows down.
--
-- When the player loses health while under 70% the whole game drops to a
-- quarter speed for two and a half seconds, the screen tints blue, and the
-- player gets a knight-speed aura. Then it snaps back.
--
-- Mechanism: kp.game_speed(n) is the engine's own SetGameSpeed scale (the
-- five world/pause/animation timers), the same knob the route's `speed`
-- step uses, so this is real slow motion, not an effect on the creatures.
-- kp.speed is a different thing: whole extra ticks per frame, 1..16, and
-- cannot go below 1 (verified live: kp.speed(0.25) read back 1). A timer
-- restores the previous scale. The tint is a coloured SetGlobalFadeOut
-- held until the fade-in.
--
-- Trigger: OnTick polling the player's hit points (every 5th frame). The
-- EventHandler attacked callback fires for NPC victims but never for the
-- player creature (verified live 2026-09-16: OnCreatureAttacked(pc, x) did
-- not dispatch while the PC was being hit), so "you got hurt" is read from
-- the HP delta instead.
--
-- Oracle lines: "[cursed:slowmo] engaged at hp x/y, speed now s (#n)" / "[cursed:slowmo] released"
-- Counter: local number 7 on the PC == slow-motion entries so far; local
-- number 6 == the read-back speed x100 at the last entry.
priority = 30

local THRESHOLD = 0.7
local SLOW = 0.25
local HOLD_MS = 2500
local POLL_EVERY = 5
local VFX_STUN = 1040
local VFX_KNIGHT_SPEED = 2031
local DURATION_TEMPORARY = 1
local COUNTER_SLOT = 7

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end

local active = false
local previous = 1.0
local entries = 0
local last_hp = nil

local function scale(...)
  if not (kp and kp.game_speed) then return nil end
  local ok, v = pcall(kp.game_speed, ...)
  return ok and v or nil
end

function cursed_release(timer_id, fired, data)
  active = false
  scale(previous)
  q("SetGlobalFadeIn", 0.0, 0.3, 0.0, 0.0, 0.0)
  kp.print("[cursed:slowmo] released")
  return false
end

local function engage(pc, hp, max)
  if not (kp and kp.game_speed) then return end
  active = true
  local cur = scale()
  previous = (type(cur) == "number" and cur > 0) and cur or 1.0
  scale(SLOW)
  -- Read the scale back and publish it (x100, local number 6): the route
  -- asserts the engine really ran slow, not just that we asked.
  local seen = scale()
  seen = type(seen) == "number" and seen or -1
  q("SetLocalNumber", pc, 6, math.floor(seen * 100 + 0.5))
  q("SetGlobalFadeOut", 0.0, 0.1, 0.1, 0.2, 0.8)
  local haste = q("EffectVisualEffect", VFX_KNIGHT_SPEED)
  local ping = q("EffectVisualEffect", VFX_STUN)
  if haste then q("ApplyEffectToObject", DURATION_TEMPORARY, haste, pc, 3.0) end
  if ping then q("ApplyEffectToObject", 0, ping, pc, 0.0) end
  entries = entries + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, entries)
  kp.registertimer(HOLD_MS, "cursed_release", {})
  kp.print(("[cursed:slowmo] engaged at hp %d/%d, speed now %.2f (#%d)"):format(hp, max, seen, entries))
end

function OnTick(tick, relevant)
  if active or tick % POLL_EVERY ~= 0 then return end
  local pc = q("GetFirstPC")
  if not pc or not yes(q("GetIsObjectValid", pc)) then return end
  local hp, max = q("GetCurrentHitPoints", pc), q("GetMaxHitPoints", pc)
  if type(hp) ~= "number" or type(max) ~= "number" or max <= 0 then return end
  local dropped = last_hp ~= nil and hp < last_hp
  last_hp = hp
  if dropped and hp <= max * THRESHOLD then engage(pc, hp, max) end
end
