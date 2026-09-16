-- Chain reaction: every corpse is a thermal detonator.
--
-- When anything dies it explodes. Everything within the blast radius takes
-- damage; anything that dies from that explodes too, so one kill in a
-- crowded room cascades. Party members are in the blast as well (a third of
-- the damage, and never below 1 HP), because a demo where the player is
-- safe is not cursed.
--
-- Mechanism: death scripts run ON the corpse, so OnRunScript + the death
-- resref is the trigger (OnCreatureDeath is never dispatched). The blast
-- visual is the thermal detonator VFX applied at the corpse; the damage is
-- EffectDamage on every creature in range, which runs the victims' own
-- death scripts and re-enters this hook. Recursion is bounded because a
-- corpse only detonates once.
--
-- Oracle lines: "[cursed:boom] <name> detonated: k hit (#n)"
-- Counter: local number 7 on the PC == detonations so far; local number 6 ==
-- total damage dealt to party members. (Deaths caused by a blast show up as
-- their own detonation a frame later, when their death script runs; the
-- effect has not resolved by the time this hook returns.)
priority = 30

local RADIUS = 7.0
local DAMAGE = 40
local PARTY_DIVISOR = 3
local VFX_THERMAL = 3005
local VFX_FRAG = 3003
local DAMAGE_TYPE_FIRE = 256
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

local exploded = {}
local count = 0
local depth = 0
local party_damage = 0   -- published in local number 6 so the route can see the party was hit

local function is_death_script(s)
  return s == "k_def_death01" or s:find("death", 1, true) ~= nil or s:find("dead", 1, true) ~= nil
end

local function detonate(corpse)
  if exploded[corpse] then return end
  exploded[corpse] = true
  local pc = q("GetFirstPC")
  if not pc then return end
  local boom = q("EffectVisualEffect", depth > 0 and VFX_FRAG or VFX_THERMAL)
  if boom then q("ApplyEffectToObject", 0, boom, corpse, 0.0) end
  q("SetGlobalFadeOut", 0.0, 0.05, 1.0, 0.6, 0.1)
  q("SetGlobalFadeIn", 0.05, 0.4, 0.0, 0.0, 0.0)

  local hit, killed = 0, 0
  local area = q("GetArea", corpse)
  local victims = {}
  local o = q("GetFirstObjectInArea", area, 1)
  while o and yes(q("GetIsObjectValid", o)) do
    if o ~= corpse and not yes(q("GetIsDead", o))
       and dist(corpse, o) <= RADIUS then
      victims[#victims + 1] = o
    end
    o = q("GetNextObjectInArea", area, 1)
  end
  depth = depth + 1
  for _, v in ipairs(victims) do
    local party = yes(q("IsObjectPartyMember", v))
    local amount = party and math.floor(DAMAGE / PARTY_DIVISOR) or DAMAGE
    if party then q("SetMinOneHP", v, 1) end
    local dmg = q("EffectDamage", amount, DAMAGE_TYPE_FIRE, 0)
    if dmg then q("ApplyEffectToObject", 0, dmg, v, 0.0) end
    if party then
      party_damage = party_damage + amount
      q("SetLocalNumber", pc, 6, party_damage)
    end
    hit = hit + 1
  end
  depth = depth - 1
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  print(("[cursed:boom] %s detonated: %d hit (#%d)")
        :format(norm(q("GetName", corpse)), hit, count))
end

function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  local s = norm(script_name)
  if not is_death_script(s) then return end
  local pc = q("GetFirstPC")
  if not pc or object_id == pc then return end
  if not yes(q("GetIsObjectValid", object_id)) then return end
  if yes(q("IsObjectPartyMember", object_id)) then return end
  detonate(object_id)
end
