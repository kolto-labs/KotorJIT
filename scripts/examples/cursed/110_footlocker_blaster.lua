-- Footlocker blaster: every PC blaster bolt becomes a flying crate.
--
-- When the player fires a ranged weapon, a placeable (default: Endar
-- footlocker blueprint `footlker001`) is spawned near the muzzle and hopped
-- along the PC→target line so the shot reads as a crate on the projectile
-- path. On arrival the victim is Force-pushed hard (EffectForcePushed ×2 +
-- whirlwind / force-wave VFX) so they tumble. Dual-wield and burst fire each
-- emit their own crate because BroadcastSafeProjectile / OnCreatureAttacked
-- fire per shot.
--
-- Change ammo live from the cheat console (also via F12 / `lua exec`):
--   footammo                 -- print current resref + LoadModel site
--   footammo footlker001     -- Endar footlocker (default)
--   footammo <placeable>     -- any placeable blueprint the module can load
--
-- Native projectile model swap (CSWCAnimBaseProjectile::LoadModel,
-- codecave k1.after_load_model_5) is located at arm-time and logged so a
-- later trampoline can rewrite the mdl ResRef in-place. Until that lands,
-- this script flies CreateObject placeables on the same geometric path —
-- still a real footlocker with knockback, not a Force-Push vanity VFX alone.
--
-- Oracle: "[cursed:footlocker] shot …" / "[cursed:footlocker] impact …"
-- Counter: local number 7 on the PC == successful impacts.
-- Local 6 == #ammo (sanity for harness). Local 5 == 1 when armed.
priority = 30

local OBJECT_TYPE_PLACEABLE = 64
local INVENTORY_SLOT_RIGHTHAND = 4
local INVENTORY_SLOT_LEFTHAND = 5
local VFX_WHIRLWIND = 1018
local VFX_FORCE_WAVE = 3001
local DURATION_INSTANT = 0
local COUNTER_SLOT = 7
local ARM_TICKS = 200
local FLIGHT_STEPS = 6
local FLIGHT_STEP_MS = 40
local DEFAULT_AMMO = "footlker001"

-- Verified on k1_gog_103 (data/codecaves.toml k1.after_load_model_5).
local LOAD_MODEL_SIG = "f3bbd1ff5fc7463c00000000b8010000005e83c424c20800"

local function q(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return nil end
  local ok, v = pcall(nwscript.call, name, ...)
  return ok and v or nil
end
local function yes(v) return v == 1 or v == true end
local function norm(s) return type(s) == "string" and s:gsub("%z+$", "") or "" end

local ammo = DEFAULT_AMMO
local armed_flag = false
local tick_count = 0
local shots = 0
local impacts = 0
local load_model_va = nil
local last_dedup = {}
local flights = {}
local next_flight = 0

local function publish_armed(v)
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, v and 1 or 0) end
end

local function publish_ammo()
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 6, #ammo) end
end

local function disarm()
  armed_flag = false
  tick_count = 0
  publish_armed(false)
end

local function armed()
  if not armed_flag then return false end
  local pc = q("GetFirstPC")
  if not pc then return false end
  if yes(q("IsInConversation", pc)) then return false end
  return true
end

local function locate_projectile_load_model()
  if load_model_va then return load_model_va end
  if not (kp and kp.mem and kp.mem.findsig) then return nil end
  local hit = kp.mem.findsig(LOAD_MODEL_SIG)
  if hit then
    load_model_va = hit
    kp.print(("[cursed:footlocker] LoadModel site @ 0x%08X (CSWCAnimBaseProjectile)"):format(hit))
  else
    kp.print("[cursed:footlocker] LoadModel sig missed (placeable path still active)")
  end
  return load_model_va
end

function OnTick(tick, relevant)
  if armed_flag then return end
  tick_count = tick_count + 1
  if tick_count >= ARM_TICKS then
    armed_flag = true
    publish_armed(true)
    publish_ammo()
    locate_projectile_load_model()
    kp.print(("[cursed:footlocker] armed ammo=%s"):format(ammo))
  end
end

function OnModuleLoad(relevant) disarm() end
function OnAreaEnter(area, entering, relevant) disarm() end

local function holding_ranged(pc)
  for _, slot in ipairs({ INVENTORY_SLOT_RIGHTHAND, INVENTORY_SLOT_LEFTHAND }) do
    local item = q("GetItemInSlot", slot, pc)
    if item and yes(q("GetIsObjectValid", item)) and yes(q("GetWeaponRanged", item)) then
      return true
    end
  end
  return false
end

local function vec(a, b)
  return { x = b.x - a.x, y = b.y - a.y, z = b.z - a.z }
end

local function add(p, v, t)
  return { x = p.x + v.x * t, y = p.y + v.y * t, z = p.z + v.z * t }
end

local function fling(victim, pc)
  if not yes(q("GetIsObjectValid", victim)) or yes(q("GetIsDead", victim)) then return false end
  if victim == pc or yes(q("IsObjectPartyMember", victim)) then return false end
  for _ = 1, 2 do
    local push = q("EffectForcePushed")
    if push then q("ApplyEffectToObject", DURATION_INSTANT, push, victim, 0.0) end
  end
  local wave = q("EffectVisualEffect", VFX_WHIRLWIND)
  if wave then q("ApplyEffectToObject", DURATION_INSTANT, wave, victim, 0.0) end
  local burst = q("EffectVisualEffect", VFX_FORCE_WAVE)
  if burst then q("ApplyEffectToObject", DURATION_INSTANT, burst, victim, 0.0) end
  return true
end

function on_footlocker_flight(timer_id, count, data)
  local id = data and data.id
  local f = id and flights[id]
  if not f then return false end
  f.step = f.step + 1
  local t = math.min(1.0, f.step / FLIGHT_STEPS)
  local p = add(f.origin, f.delta, t)
  p.z = p.z + 0.6 * math.sin(t * math.pi)
  local loc = q("Location", p, f.facing)
  if loc and yes(q("GetIsObjectValid", f.crate)) and kp and kp.as then
    kp.as(f.crate, function() q("JumpToLocation", loc) end)
  end
  if f.step < FLIGHT_STEPS then return true end

  if fling(f.target, f.pc) then
    impacts = impacts + 1
    q("SetLocalNumber", f.pc, COUNTER_SLOT, impacts)
    kp.print(("[cursed:footlocker] impact #%d on %s"):format(
        impacts, norm(q("GetName", f.target))))
  end
  if yes(q("GetIsObjectValid", f.crate)) then
    q("DestroyObject", f.crate)
  end
  flights[id] = nil
  return false
end

local function launch(pc, target)
  if not armed() then return end
  if not holding_ranged(pc) then return end
  if not yes(q("GetIsObjectValid", target)) then return end
  if target == pc or yes(q("IsObjectPartyMember", target)) then return end

  -- Dedup BroadcastSafeProjectile + Attacked for the same bolt in one second.
  local now = q("GetTimeSecond") or 0
  local key = tostring(target) .. ":" .. tostring(now)
  if last_dedup[key] then return end
  last_dedup[key] = true

  local origin = q("GetPosition", pc)
  local dest = q("GetPosition", target)
  if type(origin) ~= "table" or type(dest) ~= "table" then return end

  local delta = vec(origin, dest)
  local muzzle = add(origin, delta, 0.08)
  muzzle.z = muzzle.z + 1.2
  dest = { x = dest.x, y = dest.y, z = dest.z + 1.0 }

  local facing = q("GetFacing", pc) or 0
  local loc0 = q("Location", muzzle, facing)
  local crate = q("CreateObject", OBJECT_TYPE_PLACEABLE, ammo, loc0, 0)
  if not crate or not yes(q("GetIsObjectValid", crate)) then
    kp.print(("[cursed:footlocker] CreateObject(%s) failed"):format(ammo))
    return
  end
  shots = shots + 1
  kp.print(("[cursed:footlocker] shot #%d ammo=%s -> %s"):format(
      shots, ammo, norm(q("GetName", target))))

  next_flight = next_flight + 1
  local id = next_flight
  flights[id] = {
    step = 0,
    crate = crate,
    pc = pc,
    target = target,
    origin = muzzle,
    delta = vec(muzzle, dest),
    facing = facing,
  }
  if kp and kp.registertimer then
    kp.registertimer(FLIGHT_STEP_MS, "on_footlocker_flight", { id = id })
  else
    on_footlocker_flight(0, 0, { id = id })
  end
end

function OnCreatureBroadcastSafeProjectile(creature, attacker, relevant)
  local pc = q("GetFirstPC")
  if not pc or attacker ~= pc then return end
  launch(pc, creature)
end

function OnCreatureAttacked(creature, attacker, relevant)
  local pc = q("GetFirstPC")
  if not pc or attacker ~= pc then return end
  if not holding_ranged(pc) then return end
  launch(pc, creature)
end

function OnConsoleCommand(line, relevant)
  if type(line) ~= "string" then return end
  local cmd, arg = line:match("^%s*(%S+)%s*(.-)%s*$")
  if not cmd then return end
  cmd = cmd:lower()
  if cmd == "footammo" or cmd == "kpammo" then
    if arg == nil or arg == "" then
      kp.print(("[cursed:footlocker] ammo=%s shots=%d impacts=%d"):format(ammo, shots, impacts))
      if load_model_va then
        kp.print(("[cursed:footlocker] LoadModel @ 0x%08X"):format(load_model_va))
      end
    else
      ammo = arg:lower()
      publish_ammo()
      kp.print(("[cursed:footlocker] ammo set to %s"):format(ammo))
    end
    return false
  end
end
