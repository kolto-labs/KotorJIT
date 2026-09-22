-- Doppelganger: every enemy wears your face, and you wear Malak's.
--
-- The first time the player is attacked they are redrawn as Darth Malak.
-- Every hostile that fights the player is redrawn as the player's own
-- appearance the moment it engages, so the fight is Malak against a room
-- full of copies of you.
--
-- Mechanism: OnCreatureAttacked (live) gives victim and attacker.
-- GetAppearanceType(pc) is the player's appearance.2da row, which
-- EffectDisguise accepts directly. Disguises are permanent-duration effects
-- so they survive the rest of the fight.
--
-- Oracle lines: "[cursed:mirror] you are Malak now" / "[cursed:mirror] <name> wears your face (#n)"
-- Counter: local number 7 on the PC == copies so far.
priority = 30

-- Inside an engine hook, GetIsEnemy(x, pc) answers 0 even for a creature that
-- is plainly hostile (verified live 2026-09-16: 1 from the harness state, 0
-- from inside OnRunScript for the same trooper), and GetIsDead is still 0
-- while the death script runs. Hooks therefore treat "not a party member"
-- as hostile and never gate on GetIsDead for the creature the hook is about.

local MALAK = 21
local VFX_WHIRLWIND = 1018
local VFX_DARK_LIGHTNING = 2038
local DURATION_PERMANENT = 2
local DURATION_TEMPORARY = 1
local COUNTER_SLOT = 7

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end

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
    kp.print("[cursed] armed")
  end
end
local function disarm()
  armed_flag = false; tick_count = 0
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, 0) end
end
function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end

local pc_cursed = false
local copies = {}
local count = 0

local function malak(pc)
  if pc_cursed then return end
  pc_cursed = true
  local look = q("EffectDisguise", MALAK)
  local aura = q("EffectVisualEffect", VFX_DARK_LIGHTNING)
  if look then q("ApplyEffectToObject", DURATION_PERMANENT, look, pc, 0.0) end
  if aura then q("ApplyEffectToObject", DURATION_TEMPORARY, aura, pc, 6.0) end
  q("SetGlobalFadeOut", 0.0, 0.1, 0.4, 0.0, 0.0)
  q("SetGlobalFadeIn", 0.1, 0.5, 0.0, 0.0, 0.0)
  if nwscript and nwscript.with_caller then nwscript.with_caller(pc, function() q("SpeakString", "I am the Dark Lord.", 1) end) end
  kp.print("[cursed:mirror] you are Malak now")
end

local function copy(who, pc)
  if copies[who] or who == pc then return end
  if not yes(q("GetIsObjectValid", who)) or yes(q("GetIsDead", who)) then return end
  if yes(q("IsObjectPartyMember", who)) then return end
  local row = q("GetAppearanceType", pc)
  if type(row) ~= "number" or row <= 0 then return end
  copies[who] = true
  local look = q("EffectDisguise", row)
  local puff = q("EffectVisualEffect", VFX_WHIRLWIND)
  if look then q("ApplyEffectToObject", DURATION_PERMANENT, look, who, 0.0) end
  if puff then q("ApplyEffectToObject", 0, puff, who, 0.0) end
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  if nwscript and nwscript.with_caller then nwscript.with_caller(who, function() q("SpeakString", "I am you.", 0) end) end
  kp.print(("[cursed:mirror] %s wears your face (#%d)"):format(norm(q("GetName", who)), count))
end

function OnCreatureAttacked(creature, attacker, relevant)
  if not armed() then return end
  local pc = q("GetFirstPC")
  if not pc then return end
  if creature == pc then
    malak(pc)
    copy(attacker, pc)
  elseif attacker == pc then
    malak(pc)
    copy(creature, pc)
  end
end
