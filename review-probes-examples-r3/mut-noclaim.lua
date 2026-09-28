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
-- Party protection: before a party member's first blast, the script reads
-- its GetMinOneHP flag, then sets it. SETTLE_MS after the latest blast, and
-- on a module load, area enter or script unload, the script puts each flag
-- back to the value it read, on the same object it set while that object is
-- still valid (even if GetFirstPC now names another creature). Only a
-- guarded object that is gone is looked up again: the PC with GetFirstPC,
-- a party member by its tag through the party roster
-- (GetPartyMemberByIndex), then GetObjectByTag. A lookup never takes an
-- object this script guarded under its own ID earlier in the session. A
-- guarded creature that cannot be found is logged ("restore pending") and
-- tried again at the next settle, area enter or module load; everyone who
-- can be found is restored in the same pass. If a blast reaches that
-- creature first, it keeps the prior flag it had.
-- A member whose flag cannot be read (an error or a false answer) is left
-- out of the blast. Not covered: a save written inside the SETTLE_MS window
-- keeps the flag set, and loading it in a new session starts with no record
-- of what to restore.
--
-- VFX_FRAG marks a blast set off while another blast is still applying its
-- damage (depth > 0). That happens only if a victim's death script runs
-- inside the bridge call. The tests show both cases. A live chained kill
-- decides which one the engine does; the header note below says deaths
-- arrive a frame later, which gives thermal only.
--
-- Oracle lines: "[cursed:boom] <name> detonated: k hit (#n)"
-- Counter: local number 7 on the PC == detonations so far; local number 6 ==
-- total damage requested against party members (not a measurement).
-- (Deaths caused by a blast show up as their own detonation a frame later,
-- when their death script runs; the effect has not resolved by the time
-- this hook returns.)
priority = 30

local RADIUS = 7.0
local DAMAGE = 40
local PARTY_DIVISOR = 3
local VFX_THERMAL = 3005
local VFX_FRAG = 3003
local DAMAGE_TYPE_FIRE = 256
local COUNTER_SLOT = 7
local SETTLE_MS = 3000

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function call(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return false end
  return (pcall(nwscript.call, name, ...))
end

local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end
local function tag_of(o) return norm(q("GetTag", o)) end
local function valid(o) return o ~= nil and yes(q("GetIsObjectValid", o)) end

-- guarded[id] == { prior = the min-one-HP flag before our first SetMinOneHP,
-- tag = GetTag then, pc = it was GetFirstPC then }. owned[id] is set for
-- every ID an entry has been keyed on this session and is never cleared.
-- settle_gen ignores timers that a later blast superseded.
local guarded = {}
local owned = {}
local settle_gen = 0
-- The object an entry refers to now, or nil. The object this script set is
-- used while it is still valid and keeps its tag, even if GetFirstPC now
-- names someone else. Only when it is gone (object IDs can change across a
-- module load) is it looked up again: the PC through GetFirstPC, a party
-- member by tag through the party roster, then GetObjectByTag. A lookup
-- never takes an object this script has guarded under its own ID, now or
-- earlier in the session: that object has its own entry and its own prior.
local function unclaimed(m, id)
  return valid(m)
end
local function current(id, entry)
  if valid(id) and (entry.tag == "" or tag_of(id) == entry.tag) then return id end
  if entry.pc then
    local pc = q("GetFirstPC")
    return unclaimed(pc, id) and pc or nil
  end
  if entry.tag == "" then return nil end
  local n = tonumber(q("GetPartyMemberCount")) or 0
  for i = 0, n - 1 do
    local m = q("GetPartyMemberByIndex", i)
    if unclaimed(m, id) and tag_of(m) == entry.tag then return m end
  end
  local m = q("GetObjectByTag", entry.tag, 0)
  if unclaimed(m, id) and yes(q("IsObjectPartyMember", m)) then return m end
  return nil
end
local function guard(member)
  if guarded[member] ~= nil then return true end
  -- A creature whose restore is still pending keeps its first prior; reading
  -- the flag now would record our own 1.
  local old
  for id, entry in pairs(guarded) do
    if current(id, entry) == member then old = id; break end
  end
  if old then
    if not call("SetMinOneHP", member, 1) then return false end
    guarded[member], guarded[old] = guarded[old], nil
    owned[member] = true
    return true
  end
  local prior = q("GetMinOneHP", member)
  if prior == nil then return false end
  prior = yes(prior) and 1 or 0
  if not call("SetMinOneHP", member, 1) then return false end
  guarded[member] = { prior = prior, tag = tag_of(member), pc = q("GetFirstPC") == member }
  owned[member] = true
  return true
end
local function restore_guards()
  local done = {}
  for id, entry in pairs(guarded) do
    local now = current(id, entry)
    if now == nil then
      kp.print(("[cursed:boom] min-one-HP restore pending: %s not found")
            :format(entry.pc and "PC" or (entry.tag ~= "" and entry.tag or tostring(id))))
    elseif call("SetMinOneHP", now, entry.prior) then
      done[#done + 1] = id
    end
  end
  for _, id in ipairs(done) do guarded[id] = nil end
end
function chain_settle(timer_id, fired, data)
  if type(data) == "table" and data.gen == settle_gen then restore_guards() end
  return false
end
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
  restore_guards()
  armed_flag = false; tick_count = 0
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, 0) end
end
function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end
function OnScriptUnload(relevant) restore_guards() end

local exploded = {}
local count = 0
local depth = 0
local party_damage = 0   -- published in local number 6 (requested, not measured)

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
    if not party or guard(v) then
      local amount = party and math.floor(DAMAGE / PARTY_DIVISOR) or DAMAGE
      local dmg = q("EffectDamage", amount, DAMAGE_TYPE_FIRE, 0)
      if dmg then q("ApplyEffectToObject", 0, dmg, v, 0.0) end
      if party then
        party_damage = party_damage + amount
        q("SetLocalNumber", pc, 6, party_damage)
      end
      hit = hit + 1
    end
  end
  depth = depth - 1
  settle_gen = settle_gen + 1
  if kp and type(kp.registertimer) == "function" then
    kp.registertimer(SETTLE_MS, "chain_settle", { gen = settle_gen })
  end
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  kp.print(("[cursed:boom] %s detonated: %d hit (#%d)")
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
