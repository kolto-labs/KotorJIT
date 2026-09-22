-- Loot pinata: enemies burst into credits, and every other one into a gizka.
--
-- When an enemy dies, a stun-grenade sparkle goes off on the corpse and a
-- ring of credit piles appears around it. Every second corpse also releases
-- a hostile gizka with the appear animation, so the room fills with lizards
-- that want you dead.
--
-- Mechanism: OnRunScript on the death script running on the corpse.
-- CreateObject(OBJECT_TYPE_ITEM, "g_i_credits00N", location) places a pile
-- on the floor; CreateObject(OBJECT_TYPE_CREATURE, "g_gizka01", ...) with
-- the appear flag spawns the lizard, and ChangeToStandardFaction makes it
-- hostile (its template faction is gizka, which is indifferent to you).
-- Locations are offset from GetPosition(corpse) with Location(vector, facing).
--
-- Oracle lines: "[cursed:pinata] <name> burst: k piles" / "[cursed:pinata] gizka released (#n)"
-- Counter: local number 7 on the PC == bursts so far.
priority = 30

local PILES = 5
local RING = 1.2
local OBJECT_TYPE_CREATURE = 1
local OBJECT_TYPE_ITEM = 2
local STANDARD_FACTION_HOSTILE_1 = 1
local VFX_STUN_GRENADE = 3004
local CREDITS = { "g_i_credits001", "g_i_credits002", "g_i_credits003", "g_i_credits004" }
local GIZKA = "g_gizka01"
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
function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end

local burst = {}
local count = 0
local gizkas = 0

local function is_death_script(s)
  return s == "k_def_death01" or s:find("death", 1, true) ~= nil or s:find("dead", 1, true) ~= nil
end

local function pinata(corpse, pc)
  if burst[corpse] then return end
  local pos = q("GetPosition", corpse)
  if type(pos) ~= "table" then return end
  burst[corpse] = true
  local sparkle = q("EffectVisualEffect", VFX_STUN_GRENADE)
  if sparkle then q("ApplyEffectToObject", 0, sparkle, corpse, 0.0) end

  local placed = 0
  for i = 1, PILES do
    local a = (i / PILES) * 2 * math.pi
    local loc = q("Location", { x = pos.x + RING * math.cos(a), y = pos.y + RING * math.sin(a), z = pos.z }, 0.0)
    local it = loc and q("CreateObject", OBJECT_TYPE_ITEM, CREDITS[math.random(#CREDITS)], loc, 0)
    if it and yes(q("GetIsObjectValid", it)) then placed = placed + 1 end
  end
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  kp.print(("[cursed:pinata] %s burst: %d piles"):format(norm(q("GetName", corpse)), placed))

  if count % 2 == 0 then
    local loc = q("Location", { x = pos.x, y = pos.y, z = pos.z }, 0.0)
    local liz = loc and q("CreateObject", OBJECT_TYPE_CREATURE, GIZKA, loc, 1)
    if liz and yes(q("GetIsObjectValid", liz)) then
      gizkas = gizkas + 1
      q("ChangeToStandardFaction", liz, STANDARD_FACTION_HOSTILE_1)
      if nwscript and nwscript.with_caller then nwscript.with_caller(liz, function() q("ActionAttack", pc, 0) end) end
      kp.print(("[cursed:pinata] gizka released (#%d)"):format(gizkas))
    end
  end
end

function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  local s = norm(script_name)
  if not is_death_script(s) then return end
  local pc = q("GetFirstPC")
  if not pc or object_id == pc then return end
  if not yes(q("GetIsObjectValid", object_id)) then return end
  if yes(q("IsObjectPartyMember", object_id)) then return end
  pinata(object_id, pc)
end
