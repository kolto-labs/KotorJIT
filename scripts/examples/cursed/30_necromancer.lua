-- Necromancer: nothing stays dead.
--
-- Under a second after an enemy dies, something stands up on its corpse
-- wearing Darth Malak's body, wreathed in dark lightning, hostile, and
-- shouting. Each corpse rises exactly once and the risen die for good, so a
-- fight ends after every enemy has died twice.
--
-- Mechanism: the engine never dispatches OnCreatureDeath (see
-- docs/user/api-status.md, dead names), so the trigger is OnRunScript with
-- the death script running ON the corpse (k_def_death01 and the module's
-- own *_dead / *death scripts). The delay is kotor.registertimer, the Lua
-- stand-in for DelayCommand. The rise is a CreateObject on the corpse's
-- location plus EffectDisguise(21); ChangeToStandardFaction makes it
-- hostile because the template's own faction is not guaranteed to be.
--
-- Oracle lines: "[cursed:necro] <name> fell" / "[cursed:necro] <name> rose as Malak (#n)"
-- Counter: local number 7 on the PC == resurrections so far.
priority = 30

-- Inside an engine hook, GetIsEnemy(x, pc) answers 0 even for a creature that
-- is plainly hostile (verified live 2026-09-16: 1 from the harness state, 0
-- from inside OnRunScript for the same trooper), and GetIsDead is still 0
-- while the death script runs. Hooks therefore treat "not a party member"
-- as hostile and never gate on GetIsDead for the creature the hook is about.

local RISE_AFTER_MS = 800    -- K1 removes a lootless corpse ~3s after death; rise before it goes
local TEMPLATE = "g_sithtroop01"
local OBJECT_TYPE_CREATURE = 1
local MALAK = 21
local VFX_DARK_LIGHTNING = 2038
local VFX_LIGHTNING_HIT = 1028
local STANDARD_FACTION_HOSTILE_1 = 1
local DURATION_PERMANENT = 2
local DURATION_TEMPORARY = 1
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

local risen = {}      -- object id -> true once it has been raised
local pending = {}    -- object id -> true while a timer is armed
local count = 0

local function is_death_script(s)
  return s == "k_def_death01" or s:find("death", 1, true) ~= nil or s:find("dead", 1, true) ~= nil
end

function cursed_rise(timer_id, fired, data)
  local id = data.id
  pending[id] = nil
  local pc = q("GetFirstPC")
  local pos = q("GetPosition", id)
  if not pc or not yes(q("GetIsObjectValid", id)) or type(pos) ~= "table" then
    print(("[cursed:necro] corpse %s was gone before it could rise"):format(tostring(id)))
    return false
  end
  risen[id] = true
  -- Rebirth, not revival: the corpse is replaced by a fresh creature on the
  -- same spot. EffectResurrection does not take on these bodies (verified
  -- live: dead stays 1), and the engine removes a lootless corpse within
  -- ~3s of death, so the new body has to be up before that.
  local loc = q("Location", { x = pos.x, y = pos.y, z = pos.z }, q("GetFacing", id) or 0.0)
  local reborn = loc and q("CreateObject", OBJECT_TYPE_CREATURE, TEMPLATE, loc, 1)
  if not reborn or not yes(q("GetIsObjectValid", reborn)) then
    print("[cursed:necro] CreateObject failed; nothing rose")
    return false
  end
  risen[reborn] = true           -- a reborn body dies for good
  q("DestroyObject", id, 0.0)
  q("ChangeToStandardFaction", reborn, STANDARD_FACTION_HOSTILE_1)
  local look = q("EffectDisguise", MALAK)
  local aura = q("EffectVisualEffect", VFX_DARK_LIGHTNING)
  local hit = q("EffectVisualEffect", VFX_LIGHTNING_HIT)
  if look then q("ApplyEffectToObject", DURATION_PERMANENT, look, reborn, 0.0) end
  if aura then q("ApplyEffectToObject", DURATION_TEMPORARY, aura, reborn, 12.0) end
  if hit then q("ApplyEffectToObject", 0, hit, reborn, 0.0) end
  q("SetGlobalFadeOut", 0.0, 0.1, 0.5, 0.0, 0.7)
  q("SetGlobalFadeIn", 0.15, 0.6, 0.0, 0.0, 0.0)
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  if kp and kp.as then
    kp.as(reborn, function()
      q("SpeakString", "Death is only the beginning.", 1)
      q("ActionAttack", pc, 0)
    end)
  end
  print(("[cursed:necro] %s rose as Malak (#%d): corpse %s -> %s"):format(
    norm(q("GetName", id)), count, tostring(id), tostring(reborn)))
  q("registertimer", 2500, "cursed_verify", { id = reborn })
  return false
end

-- Effects resolve on a later frame, so the proof line is written 2.5s after
-- the rise: is it standing, hostile, and wearing Malak (appearance row 21)?
function cursed_verify(timer_id, fired, data)
  local id = data.id
  print(("[cursed:necro] verify %s: valid=%s dead=%s hp=%s app=%s"):format(tostring(id),
    tostring(q("GetIsObjectValid", id)), tostring(q("GetIsDead", id)),
    tostring(q("GetCurrentHitPoints", id)), tostring(q("GetAppearanceType", id))))
  return false
end

function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  local s = norm(script_name)
  if not is_death_script(s) then return end
  if risen[object_id] or pending[object_id] then return end
  local pc = q("GetFirstPC")
  if not pc or object_id == pc then return end
  if not yes(q("GetIsObjectValid", object_id)) then return end
  if yes(q("IsObjectPartyMember", object_id)) then return end
  pending[object_id] = true
  print(("[cursed:necro] %s fell (%s)"):format(norm(q("GetName", object_id)), s))
  q("registertimer", RISE_AFTER_MS, "cursed_rise", { id = object_id })
end
