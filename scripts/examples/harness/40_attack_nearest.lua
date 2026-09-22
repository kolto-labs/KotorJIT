-- Attack the nearest live hostile within RADIUS, unless the PC is already
-- fighting it. Re-issuing ActionAttack every poll restarts the combat round,
-- so this is a no-op while the PC is mid-round (action 39) or already
-- attacking (action 3).
--
-- After queueing, expect the engine's autopause to fire on the first combat
-- event unless the ini disabled it: if the harness `state` shows
-- phase=paused, send `clear_auto_pause` (it also unpauses the world timers,
-- which is what actually lets rounds resolve).

local RADIUS = 40.0

local function clean(s) return (s:gsub("%z", "")) end

local pc = nwscript.call('GetFirstPC')
local area = nwscript.call('GetArea',pc)
local act = nwscript.call('GetCurrentAction',pc)

local best, best_d = nil, RADIUS + 1
local c = nwscript.call('GetFirstObjectInArea',area, 1)
while nwscript.call('GetIsObjectValid',c) == 1 do
  if nwscript.call('GetIsEnemy',c, pc) == 1 and nwscript.call('GetIsDead',c) == 0 then
    local d = nwscript.call('GetDistanceBetween',pc, c)
    if d < best_d then best, best_d = c, d end
  end
  c = nwscript.call('GetNextObjectInArea',area, 1)
end

if best == nil then return { target = nil, reason = "no live hostile in radius" } end
if act == 3 or act == 39 then
  return { target = clean(nwscript.call('GetTag',best)), dist = best_d, reason = "already engaged", action = act }
end

kp.as(pc, function()
  nwscript.call('ClearAllActions')
  nwscript.call('ActionAttack',best, 0)      -- 0 == no combat feat
end)
return { target = clean(nwscript.call('GetTag',best)), id = best, hp = nwscript.call('GetCurrentHitPoints',best), dist = best_d, queued = true }
