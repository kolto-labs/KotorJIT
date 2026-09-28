-- Chain reaction: every corpse is a thermal detonator.
--
-- When a creature outside the party dies, it explodes. Every other creature
-- outside the party within the blast radius takes fire damage, and anything
-- that dies from that explodes too, so one kill in a crowded room cascades.
--
-- Mechanism: death scripts run ON the corpse, so OnRunScript + the death
-- resref is the trigger (OnCreatureDeath is never dispatched). The blast
-- visual is the thermal detonator VFX applied at the corpse; the damage is
-- EffectDamage on every creature in range, which runs the victims' own
-- death scripts and re-enters this hook. Recursion is bounded because a
-- corpse only detonates once.
--
-- The player and the party are left out. The script changes nothing on them
-- that it would have to put back later. Before each hit it asks the engine
-- two things about the victim: is it GetFirstPC, and is it a party member
-- (IsObjectPartyMember). A yes to either, or no clear answer, and the victim
-- is skipped. The same test decides whether a corpse detonates. No object ID
-- is kept from one blast to the next for this, so a companion that comes back
-- under a new ID, a swap of the controlled character, or a tag that another
-- creature shares changes nothing.
--
-- VFX_FRAG marks a blast set off while another blast is still applying its
-- damage (depth > 0). That happens only if a victim's death script runs
-- inside the bridge call. The tests show both cases. A live chained kill
-- decides which one the engine does; the note below says deaths arrive a
-- frame later, which gives thermal only.
--
-- Oracle lines: "[cursed:boom] <name> detonated: k hit (#n)"
-- Counter: local number 7 on the PC == detonations so far.
-- (Deaths caused by a blast show up as their own detonation a frame later,
-- when their death script runs; the effect has not resolved by the time
-- this hook returns.)
priority = 30

local RADIUS = 7.0
local DAMAGE = 40
local VFX_THERMAL = 3005
local VFX_FRAG = 3003
local DAMAGE_TYPE_FIRE = 256
local COUNTER_SLOT = 7

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end

-- true = in the party, false = not, nil = no answer (an error or an odd
-- value). q() cannot be used here: it turns a false answer into nil.
local function in_party(o)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, "IsObjectPartyMember", o)
  if not ok then return nil end
  if v == 1 or v == true then return true end
  if v == 0 or v == false then return false end
  return nil
end
-- Asked again every time, right before it matters.
local function spared(o)
  local pc = q("GetFirstPC")
  if pc == nil or o == pc then return true end
  return in_party(o) ~= false
end

-- Distance from positions: GetDistanceBetween answered 99/oversized inside
-- hooks (the big shout and the airstrike found 0-1 targets in a ring of 6).
local function dist(a, b)
  local pa, pb = q("GetPosition", a), q("GetPosition", b)
  if type(pa) ~= "table" or type(pb) ~= "table" then return 99 end
  local dx, dy, dz = pa.x - pb.x, pa.y - pb.y, pa.z - pb.z
  return math.sqrt(dx * dx + dy * dy + dz * dz)
end

-- Corpses that already detonated. Object IDs are reused after a module load,
-- so this is emptied on every module load and on a save-game load.
local exploded = {}
local count = 0
local depth = 0

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
  if yes(q("GetIsInConversation", pc)) then return false end
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
function OnModuleLoad(relevant) exploded = {}; disarm() end
-- Signature per docs/lua-api.md. from_save_game is an int, and 0 is true in
-- Lua, so it is compared with 1.
function OnAreaEnter(area, entering, from_save_game, relevant)
  if from_save_game then exploded = {} end
  disarm()
end

local function is_death_script(s)
  return s == "k_def_death01" or s:find("death", 1, true) ~= nil or s:find("dead", 1, true) ~= nil
end

local function detonate(corpse)
  if exploded[corpse] then return end
  local pc = q("GetFirstPC")
  if not pc then return end
  exploded[corpse] = true
  local boom = q("EffectVisualEffect", depth > 0 and VFX_FRAG or VFX_THERMAL)
  if boom then q("ApplyEffectToObject", 0, boom, corpse, 0.0) end
  q("SetGlobalFadeOut", 0.0, 0.05, 1.0, 0.6, 0.1)
  q("SetGlobalFadeIn", 0.05, 0.4, 0.0, 0.0, 0.0)

  local hit = 0
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
    if not spared(v) then
      local dmg = q("EffectDamage", DAMAGE, DAMAGE_TYPE_FIRE, 0)
      if dmg then q("ApplyEffectToObject", 0, dmg, v, 0.0) end
      hit = hit + 1
    end
  end
  depth = depth - 1
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  kp.print(("[cursed:boom] %s detonated: %d hit (#%d)")
        :format(norm(q("GetName", corpse)), hit, count))
end

function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  local s = norm(script_name)
  if not is_death_script(s) then return end
  if not yes(q("GetIsObjectValid", object_id)) then return end
  if spared(object_id) then return end
  detonate(object_id)
end
