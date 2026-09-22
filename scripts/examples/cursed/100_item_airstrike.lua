-- Item airstrike: picking anything up calls down an orbital laser.
--
-- Every item the player acquires (loot, a container take, a script gift)
-- targets a space laser on every hostile within 20m: the laser visual, a
-- white flash, heavy damage. Pick up a medpac in a full room and the room
-- is over. Level-ups are the counterpart: the player ascends, briefly
-- redrawn as Revan with the knight-speed aura.
--
-- Mechanism: OnModuleAcquireItem and OnModulePlayerLevelUp are module
-- EventHandler callbacks. The laser is VFX_FNF_SPACE_LASER (3016, the
-- Leviathan cutscene beam) applied instantly to each target, followed by
-- EffectDamage. GetItemPossessor tells us whether the player took the item.
--
-- Oracle lines: "[cursed:strike] <item> -> k targets" / "[cursed:strike] ascension"
-- Counter: local number 7 on the PC == strikes so far.
priority = 30

-- Inside an engine hook, GetIsEnemy(x, pc) answers 0 even for a creature that
-- is plainly hostile (verified live 2026-09-16: 1 from the harness state, 0
-- from inside OnRunScript for the same trooper), and GetIsDead is still 0
-- while the death script runs. Hooks therefore treat "not a party member"
-- as hostile and never gate on GetIsDead for the creature the hook is about.

local RADIUS = 20.0
local DAMAGE = 60
local VFX_SPACE_LASER = 3016
local VFX_KNIGHT_SPEED = 2031
local REVAN = 22
local DAMAGE_TYPE_LIGHT = 2048
local DURATION_TEMPORARY = 1
local COUNTER_SLOT = 7

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end

local strikes = 0
local seen = {}   -- the acquire event fires more than once per item (verified live); strike once
-- A save load replays OnModuleAcquireItem for every item already in the
-- party's packs (11 of them on the Endar checkpoint, verified live). The
-- strike is armed only after ARM_TICKS frames of gameplay and disarmed again
-- on every module/area load, so only real pickups count.
local ARM_TICKS = 200
local armed = false
local ticks = 0

local function dist(a, b)
  local pa, pb = q("GetPosition", a), q("GetPosition", b)
  if type(pa) ~= "table" or type(pb) ~= "table" then return 99 end
  local dx, dy, dz = pa.x - pb.x, pa.y - pb.y, pa.z - pb.z
  return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function strike(pc, label)
  local hit = 0
  local area = q("GetArea", pc)
  local targets = {}
  local o = q("GetFirstObjectInArea", area, 1)
  while o and yes(q("GetIsObjectValid", o)) do
    -- distance from positions: GetDistanceBetween is not trusted inside a hook
    if o ~= pc and not yes(q("IsObjectPartyMember", o)) and not yes(q("GetIsDead", o))
       and dist(pc, o) <= RADIUS then
      targets[#targets + 1] = o
    end
    o = q("GetNextObjectInArea", area, 1)
  end
  q("SetGlobalFadeOut", 0.0, 0.05, 1.0, 1.0, 1.0)
  q("SetGlobalFadeIn", 0.15, 0.5, 0.0, 0.0, 0.0)
  for _, t in ipairs(targets) do
    local beam = q("EffectVisualEffect", VFX_SPACE_LASER)
    local dmg = q("EffectDamage", DAMAGE, DAMAGE_TYPE_LIGHT, 0)
    if beam then q("ApplyEffectToObject", 0, beam, t, 0.0) end
    if dmg then q("ApplyEffectToObject", 0, dmg, t, 0.0) end
    hit = hit + 1
  end
  strikes = strikes + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, strikes)
  q("SetLocalNumber", pc, 6, hit)          -- targets hit by the last strike, for the route gate
  kp.print(("[cursed:strike] %s -> %d targets (#%d)"):format(label, hit, strikes))
end

function OnTick(tick, relevant)
  if armed then return end
  ticks = ticks + 1
  if ticks >= ARM_TICKS then
    armed = true
    local pc = q("GetFirstPC")
    if pc then q("SetLocalNumber", pc, 5, 1) end   -- local 5 == 1: armed (the route waits on it)
    kp.print("[cursed:strike] armed")
  end
end

local function disarm()
  armed = false; ticks = 0
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, 0) end
end
function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end

function OnModuleAcquireItem(item, previous_possessor, relevant)
  if not armed then return end
  local pc = q("GetFirstPC")
  if not pc then return end
  if seen[item] then return end
  local owner = q("GetItemPossessor", item)
  if owner ~= pc and not yes(q("IsObjectPartyMember", owner)) then return end
  seen[item] = true
  strike(pc, norm(q("GetName", item)))
end

function OnModulePlayerLevelUp(player, relevant)
  local pc = q("GetFirstPC")
  if not pc then return end
  local look = q("EffectDisguise", REVAN)
  local aura = q("EffectVisualEffect", VFX_KNIGHT_SPEED)
  if look then q("ApplyEffectToObject", DURATION_TEMPORARY, look, pc, 15.0) end
  if aura then q("ApplyEffectToObject", DURATION_TEMPORARY, aura, pc, 15.0) end
  q("SetGlobalFadeOut", 0.0, 0.1, 1.0, 0.9, 0.5)
  q("SetGlobalFadeIn", 0.2, 0.8, 0.0, 0.0, 0.0)
  kp.print("[cursed:strike] ascension")
end
