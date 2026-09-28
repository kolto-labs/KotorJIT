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
-- back to the value it read.
-- Identity: a numeric object ID is trusted only in the module epoch it was
-- read in. A module load or area enter starts a new epoch first, and then
-- every guarded creature is found again by role and tag: the PC through
-- GetFirstPC, a party member by its tag through the party roster
-- (GetPartyMemberByIndex), then GetObjectByTag. A candidate must be a
-- party member (IsObjectPartyMember) with the same tag. An old ID is never
-- reused after a transition, even if it is still valid.
-- A creature that cannot be found is logged ("restore pending") and tried
-- again at the next settle or transition. Everyone who can be found is
-- restored in the same pass. If a blast reaches it first, it keeps the prior
-- it had: the script never records its own 1 as a prior. If two records
-- land on one creature, its prior is unknown: it goes back to 0, the
-- NWScript default, and that is logged.
-- A member whose flag cannot be read (an error or a false answer) is left
-- out of the blast.
-- Not covered:
-- * Unload is the last pass. A creature it cannot find then keeps
--   min-one-HP. The log names it with the F12 console line that clears it
--   ("NOT restored at unload").
-- * An untagged party member other than the PC cannot be found again after
--   a transition.
-- * A save written inside the SETTLE_MS window keeps the flag set. Loading
--   it in a new session starts with no record of what to restore.
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

-- Identity epochs. A numeric object ID means something only inside the
-- module epoch it was read in: module load and area enter start a new epoch,
-- and K1 can hand an old ID to a different creature after a load. Each guard
-- entry is { id, epoch, tag, pc, prior }: prior is the min-one-HP flag before
-- this script first set it (nil = unknown), tag is GetTag then, pc = it was
-- GetFirstPC then. The entry itself is the "we set it" marker: while it
-- exists, the creature's flag is ours and is never read back as a prior.
-- settle_gen ignores timers that a later blast superseded.
local guards = {}
local epoch = 0
local settle_gen = 0
local function label(entry)
  if entry.pc then return "PC" end
  return entry.tag ~= "" and entry.tag or "untagged party member"
end
-- A candidate must be a valid party member with the entry's tag.
local function fits(m, entry)
  return valid(m) and yes(q("IsObjectPartyMember", m)) and tag_of(m) == entry.tag
end
-- The creature an entry refers to now, or nil. The stored ID counts only in
-- the epoch it was read in. Otherwise: the PC role through GetFirstPC, then
-- the party roster by tag, then GetObjectByTag (party members only).
local function find(entry)
  if entry.epoch == epoch and fits(entry.id, entry) then return entry.id end
  if entry.pc then
    local pc = q("GetFirstPC")
    if fits(pc, entry) then return pc end
  end
  if entry.tag == "" then return nil end
  local n = tonumber(q("GetPartyMemberCount")) or 0
  for i = 0, n - 1 do
    local m = q("GetPartyMemberByIndex", i)
    if fits(m, entry) then return m end
  end
  local m = q("GetObjectByTag", entry.tag, 0)
  if fits(m, entry) then return m end
  return nil
end
-- One pass over every entry: target[entry] = creature, claims[creature] =
-- the entries that resolved to it. Two entries on one creature cannot both
-- be right, so that creature's prior is unknown.
local function resolve_all()
  local target, claims = {}, {}
  for _, entry in ipairs(guards) do
    local m = find(entry)
    if m ~= nil then
      target[entry] = m
      local list = claims[m] or {}
      list[#list + 1] = entry
      claims[m] = list
    end
  end
  return target, claims
end
local function drop(gone)
  local kept = {}
  for _, entry in ipairs(guards) do
    if not gone[entry] then kept[#kept + 1] = entry end
  end
  guards = kept
end
local function guard(member)
  for _, entry in ipairs(guards) do
    if entry.epoch == epoch and entry.id == member then return true end
  end
  local tag = tag_of(member)
  local target, claims = resolve_all()
  local mine = claims[member] or {}
  if #mine == 0 then
    local prior = q("GetMinOneHP", member)
    if prior == nil then return false end
    prior = yes(prior) and 1 or 0
    -- A 1 may be our own flag on a creature an entry could not find again
    -- (an untagged member after a load). Never record that as a prior.
    if prior == 1 then
      for _, entry in ipairs(guards) do
        if target[entry] == nil and entry.tag == tag then mine[#mine + 1] = entry end
      end
    end
    if #mine == 0 then
      if not call("SetMinOneHP", member, 1) then return false end
      guards[#guards + 1] = { id = member, epoch = epoch, tag = tag,
                              pc = q("GetFirstPC") == member, prior = prior }
      return true
    end
  end
  if not call("SetMinOneHP", member, 1) then return false end
  local keep = mine[1]
  if #mine > 1 then
    keep.prior = nil
    kp.print(("[cursed:boom] min-one-HP prior unknown for %s: %d records match it; it goes back to 0")
          :format(label(keep), #mine))
  end
  local gone = {}
  for i = 2, #mine do gone[mine[i]] = true end
  drop(gone)
  keep.id, keep.epoch = member, epoch
  return true
end
local function restore_guards()
  local target, claims = resolve_all()
  local gone = {}
  for _, entry in ipairs(guards) do
    local now = target[entry]
    if now == nil then
      kp.print(("[cursed:boom] min-one-HP restore pending: %s not found"):format(label(entry)))
    elseif not gone[entry] then
      local mine = claims[now]
      local prior = entry.prior
      if #mine > 1 or prior == nil then
        prior = 0
        kp.print(("[cursed:boom] min-one-HP prior unknown for %s (%d records); set to the default 0")
              :format(label(entry), #mine))
      end
      if call("SetMinOneHP", now, prior) then
        for _, e in ipairs(mine) do gone[e] = true end
      else
        entry.id, entry.epoch = now, epoch
      end
    end
  end
  drop(gone)
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
-- A transition starts a new epoch before the restore, so no ID read before it
-- is trusted after it.
function OnModuleLoad(relevant) epoch = epoch + 1; disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end
-- Unload is the last chance: the script state is gone afterwards. Anything
-- still set is named with the console line that clears it.
function OnScriptUnload(relevant)
  restore_guards()
  for _, entry in ipairs(guards) do
    local who
    if entry.pc and entry.tag == "" then who = 'nwscript.call("GetFirstPC")'
    elseif entry.tag ~= "" then who = ('nwscript.call("GetObjectByTag", "%s", 0)'):format(entry.tag)
    elseif entry.epoch == epoch then who = tostring(entry.id)
    else who = "<the object>" end
    kp.print(("[cursed:boom] min-one-HP NOT restored at unload: %s still has it set and this script forgets it now. Fix it in the F12 console: nwscript.call(\"SetMinOneHP\", %s, %d)")
          :format(label(entry), who, entry.prior or 0))
  end
  guards = {}
end

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
