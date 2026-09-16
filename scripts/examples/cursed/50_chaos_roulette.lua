-- Chaos roulette: every combat round rolls a curse on whoever just finished it.
--
-- The stock end-of-round script (k_def_combend01) runs on every creature in
-- combat, party and enemies alike, once per round. Each time it runs the
-- wheel spins: whirlwind, choke, terror, sudden gizka, a lightning tether
-- from the player, haste, a lit damage shield, a heal, a hot-potato teleport
-- next to the player, or nothing. The victim announces the result.
--
-- Mechanism: OnRunScript on k_def_combend01 (OnCreatureEndCombatRound is a
-- dead name). Effects are the authored NWScript effect constructors applied
-- with ApplyEffectToObject; the tether is EffectBeam with the player as the
-- effector; the teleport is JumpToLocation next to the player.
--
-- Oracle lines: "[cursed:wheel] <name>: <curse> (#n)"
-- Counter: local number 7 on the PC == spins so far.
priority = 30

local COUNTER_SLOT = 7
local RANGE = 30.0   -- cutscene actors elsewhere in the area run k_def_combend01 too; keep it in frame
local DURATION_TEMPORARY = 1
local BODY_NODE_CHEST = 1
local VFX_BEAM_LIGHTNING = 2037
local VFX_CHOKE = 1004
local VFX_STUN = 1040
local VFX_PLASMA = 3010
local GIZKA = 69

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

local function apply(kind, e, who, secs)
  if e then q("ApplyEffectToObject", kind, e, who, secs or 0.0) end
end

local WHEEL = {
  { name = "whirlwind", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectWhirlWind"), who, 3.0)
    end },
  { name = "choke", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectChoke"), who, 4.0)
      apply(DURATION_TEMPORARY, q("EffectVisualEffect", VFX_CHOKE), who, 4.0)
    end },
  { name = "terror", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectHorrified"), who, 4.0)
    end },
  { name = "sudden gizka", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectDisguise", GIZKA), who, 9.0)
    end },
  { name = "lightning tether", run = function(who, pc)
      if who ~= pc then
        apply(DURATION_TEMPORARY, q("EffectBeam", VFX_BEAM_LIGHTNING, pc, BODY_NODE_CHEST, 0), who, 3.0)
        apply(0, q("EffectDamage", 8, 64, 0), who)
      end
    end },
  { name = "haste", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectHaste"), who, 6.0)
    end },
  { name = "burning shield", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectDamageShield", 5, 0, 256), who, 6.0)
      apply(0, q("EffectVisualEffect", VFX_PLASMA), who)
    end },
  { name = "second wind", run = function(who, pc)
      apply(0, q("EffectHeal", 30), who)
    end },
  { name = "stun", run = function(who, pc)
      apply(DURATION_TEMPORARY, q("EffectStunned"), who, 3.0)
      apply(0, q("EffectVisualEffect", VFX_STUN), who)
    end },
  { name = "hot potato", run = function(who, pc)
      if who ~= pc and kp and kp.as then
        local loc = q("GetLocation", pc)
        if loc then kp.as(who, function() q("JumpToLocation", loc) end) end
      end
    end },
}

local spins = 0

function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  if norm(script_name) ~= "k_def_combend01" then return end
  local pc = q("GetFirstPC")
  if not pc or not yes(q("GetIsObjectValid", object_id)) then return end
  if yes(q("GetIsDead", object_id)) then return end
  if object_id ~= pc and dist(pc, object_id) > RANGE then return end
  local pick = WHEEL[math.random(#WHEEL)]
  pick.run(object_id, pc)
  spins = spins + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, spins)
  if kp and kp.as then
    kp.as(object_id, function() q("SpeakString", pick.name, 0) end)
  end
  print(("[cursed:wheel] %s: %s (#%d)"):format(norm(q("GetName", object_id)), pick.name, spins))
end
