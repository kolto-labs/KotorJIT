-- Rancor roulette: every enemy that notices you becomes something else.
--
-- The moment a hostile perceives the player it is redrawn as a random
-- somebody else (a Rakata, a Jawa, a Gamorrean, Malak, Bandon, HK-47,
-- Revan) with a whirlwind puff and a bark. Stats do not change: a Jawa
-- still hits like a Sith trooper, Malak still dies in three swings. That is
-- the joke. (The rancor is in the name and not in the wheel; see below.)
--
-- Mechanism: the stock perception script (k_def_percept01) runs ON the
-- perceiver, so OnRunScript gives us the sentry as object_id; heartbeat,
-- attacked and end-of-round scripts are the fallback for creatures whose
-- perception never fires. The hook only queues the id; the disguise is
-- applied 50 ms later from a timer. Applying it inside the RunScript hook
-- froze the client mid-fight twice (2026-09-16, client loop stopped at 400
-- frames); the same effect from a timer callback never did. Krayt dragon
-- (77) and hutt (70) are left out: their models have no combat animation set.
--
-- Oracle lines: "[cursed:roulette] <name> -> <monster> (#n)"
-- Counter: local number 7 on the PC == transformations so far.
priority = 30

-- Inside an engine hook, GetIsEnemy(x, pc) answers 0 even for a creature that
-- is plainly hostile (verified live 2026-09-16: 1 from the harness state, 0
-- from inside OnRunScript for the same trooper), and GetIsDead is still 0
-- while the death script runs. Hooks therefore treat "not a party member"
-- as hostile and never gate on GetIsDead for the creature the hook is about.

-- Only rows with a full humanoid combat animation set. Rancor (80), bantha
-- (53), kath hound (75), gizka (69), krayt dragon (77) and hutt (70) were
-- in the wheel first: both times the fight started with troopers wearing
-- those bodies the client stopped at exactly 400 frames and the channel
-- died (2026-09-16, twice), while every humanoid-disguise demo survived the
-- same host conditions. Big-monster disguises are for out-of-combat scenes.
local ROULETTE = {
  { row = 36, name = "rakata" },
  { row = 73, name = "jawa" },
  { row = 68, name = "gamorrean" },
  { row = 21, name = "darth malak" },
  { row = 184, name = "darth bandon" },
  { row = 3, name = "hk-47" },
  { row = 22, name = "revan" },
}
local VFX_WHIRLWIND = 1018
local DURATION_PERMANENT = 2
local COUNTER_SLOT = 7
local RANGE = 30.0

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

local done = {}
local count = 0

local queued = {}

function cursed_apply(timer_id, fired, data)
  local id = data.id
  queued[id] = nil
  if done[id] then return false end
  local pc = q("GetFirstPC")
  if not pc or not yes(q("GetIsObjectValid", id)) or yes(q("GetIsDead", id)) then return false end
  done[id] = true
  local pick = ROULETTE[math.random(#ROULETTE)]
  local who = norm(q("GetName", id))
  local disguise = q("EffectDisguise", pick.row)
  local puff = q("EffectVisualEffect", VFX_WHIRLWIND)
  if disguise then q("ApplyEffectToObject", DURATION_PERMANENT, disguise, id, 0.0) end
  if puff then q("ApplyEffectToObject", 0, puff, id, 0.0) end
  count = count + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, count)
  if kp and kp.as then
    kp.as(id, function() q("SpeakString", "What have you done to me?!", 0) end)
  end
  print(("[cursed:roulette] %s -> %s (#%d)"):format(who, pick.name, count))
  return false
end

-- Called from hooks: filter cheaply, then hand the work to a timer.
local function curse(id)
  if done[id] or queued[id] then return end
  local pc = q("GetFirstPC")
  if not pc or id == pc or not yes(q("GetIsObjectValid", id)) then return end
  if yes(q("IsObjectPartyMember", id)) then return end
  if dist(pc, id) > RANGE then return end   -- only what the camera can see
  queued[id] = true
  q("registertimer", 50, "cursed_apply", { id = id })
end

-- Every hook lands here; the guard inside curse() keeps it idempotent.
function OnRunScript(script_name, object_id, has_object, relevant)
  if not armed() then return end
  local s = norm(script_name)
  if s == "k_def_percept01" or s == "k_def_combend01" or s == "k_def_attacked01"
     or s == "k_def_heartbt01" then
    curse(object_id)
  end
end

function OnCreaturePerception(creature, perceived, how, relevant)
  if not armed() then return end
  curse(creature)
end

function OnCreatureAttacked(creature, attacker, relevant)
  if not armed() then return end
  curse(creature)
  curse(attacker)
end
