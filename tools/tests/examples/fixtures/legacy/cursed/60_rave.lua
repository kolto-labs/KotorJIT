-- Rave: the ship is a nightclub.
--
-- A beat timer strobes the screen through a colour cycle, kicks the battle
-- music on, and on every beat picks a creature that is not fighting and
-- makes it dance. Every fourth beat a plasma burst goes off on a random
-- creature, party included. The party does not dance: ClearAllActions on
-- the player would cancel whatever the route told them to do.
--
-- Mechanism: kp.registertimer with a repeating callback (return true to
-- re-arm). SetGlobalFadeOut/In with a colour is the strobe. Dancing is
-- ActionPlayAnimation(ANIMATION_LOOPING_DANCE / DANCE1) queued through
-- nwscript.with_caller, which is how a script makes another creature act. Nothing starts
-- until the player exists and is alive, so the script is inert on the main
-- menu and during loads.
--
-- Oracle lines: "[cursed:rave] beat n: <name> dances" / "[cursed:rave] beat n: plasma on <name>"
-- Counter: local number 7 on the PC == beats so far.
priority = 30

local BEAT_MS = 700
local COUNTER_SLOT = 7
local RANGE = 30.0          -- the whole area answers GetFirstObjectInArea; keep the party in frame
local DANCE = { 16, 17 }          -- ANIMATION_LOOPING_DANCE, DANCE1
local VFX_PLASMA = 3010
local COLOURS = {
  { 1.0, 0.0, 0.6 }, { 0.0, 0.8, 1.0 }, { 0.4, 1.0, 0.0 }, { 1.0, 0.8, 0.0 }, { 0.6, 0.0, 1.0 },
}

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
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

local beats = 0
local music_on = false
local armed = false

local function creatures(pc)
  local out = {}
  local area = q("GetArea", pc)
  local o = q("GetFirstObjectInArea", area, 1)
  while o and yes(q("GetIsObjectValid", o)) do
    if not yes(q("GetIsDead", o)) and dist(pc, o) <= RANGE then out[#out + 1] = o end
    o = q("GetNextObjectInArea", area, 1)
  end
  return out
end

function cursed_beat(timer_id, fired, data)
  local pc = q("GetFirstPC")
  if not pc or not yes(q("GetIsObjectValid", pc)) or yes(q("GetIsDead", pc)) then return true end
  local mod = q("GetModuleName")
  if type(mod) ~= "string" or mod == "" then return true end

  beats = beats + 1
  q("SetLocalNumber", pc, COUNTER_SLOT, beats)
  local c = COLOURS[(beats - 1) % #COLOURS + 1]
  q("SetGlobalFadeOut", 0.0, 0.06, c[1], c[2], c[3])
  q("SetGlobalFadeIn", 0.06, 0.25, 0.0, 0.0, 0.0)

  if not music_on then
    q("MusicBattlePlay", q("GetArea", pc))
    music_on = true
  end

  local all = creatures(pc)
  if #all == 0 then return true end
  local who = all[math.random(#all)]
  local name = norm(q("GetName", who))
  if beats % 4 == 0 then
    local e = q("EffectVisualEffect", VFX_PLASMA)
    if e then q("ApplyEffectToObject", 0, e, who, 0.0) end
    kp.print(("[cursed:rave] beat %d: plasma on %s"):format(beats, name))
  elseif not yes(q("GetIsInCombat", who)) and not yes(q("IsObjectPartyMember", who))
         and nwscript and nwscript.with_caller then
    local anim = DANCE[math.random(#DANCE)]
    nwscript.with_caller(who, function()
      q("ClearAllActions")
      q("ActionPlayAnimation", anim, 1.0, 4.0)
    end)
    kp.print(("[cursed:rave] beat %d: %s dances"):format(beats, name))
  end
  return true
end

function OnTick(tick, relevant)
  if armed then return end
  local pc = q("GetFirstPC")
  if not pc or not yes(q("GetIsObjectValid", pc)) or yes(q("GetIsDead", pc)) then return end
  armed = true
  kp.registertimer(BEAT_MS, "cursed_beat", {})
  kp.print("[cursed:rave] the beat drops")
end
