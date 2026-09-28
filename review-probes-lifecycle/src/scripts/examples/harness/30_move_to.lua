-- Move the PC: to a tagged object, or to an offset from where it stands.
-- Party members follow on their own (companion AI re-asserts follow-leader).
--
-- This only queues the move. Poll `GetCurrentAction(pc)` afterwards: 0 while
-- walking, 65534 once the queue empties (arrived, or the path was cut short).
-- Confirm arrival with the distance, never with the action alone.

local TARGET_TAG = "end_door05"   -- set to nil to use the OFFSET move instead
local RANGE = 1.5                 -- stop this far from the object
local OFFSET = { x = -3.0, y = 0.0, z = 0.0 }

local pc = nwscript.call('GetFirstPC')

if TARGET_TAG then
  local t = nwscript.call('GetObjectByTag',TARGET_TAG, 0)
  if nwscript.call('GetIsObjectValid',t) ~= 1 then error("no object tagged " .. TARGET_TAG) end
  nwscript.with_caller(pc, function()
    nwscript.call('ClearAllActions')
    nwscript.call('ActionMoveToObject',t, 1, RANGE)     -- 1 == run
  end)
  return { target = TARGET_TAG, dist = nwscript.call('GetDistanceBetween',pc, t) }
end

local p = nwscript.call('GetPosition',pc)
local there = nwscript.call('Location',nwscript.call('Vector',p.x + OFFSET.x, p.y + OFFSET.y, p.z + OFFSET.z), 0.0)
nwscript.with_caller(pc, function()
  nwscript.call('ClearAllActions')
  nwscript.call('ActionMoveToLocation',there, 1)
end)
return { from = { x = p.x, y = p.y, z = p.z } }
