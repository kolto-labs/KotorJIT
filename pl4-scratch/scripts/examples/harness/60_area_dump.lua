-- Dump every object of one type in the PC's area: tag, position, distance,
-- and for creatures hp/hostility/action. Use it to learn a room before
-- writing route steps for it.
--
-- OBJECT_TYPE: 1 creature, 2 item, 4 trigger, 8 door, 32 waypoint, 64 placeable
-- (nwscript.nss values). Doors are 8 in this engine's GetObjectType.

local OBJECT_TYPE = 1
local MAX = 40

local function clean(s) return (s:gsub("%z", "")) end

local pc = nwscript.call('GetFirstPC')
local area = nwscript.call('GetArea',pc)
local rows = {}
local o = nwscript.call('GetFirstObjectInArea',area, OBJECT_TYPE)
while nwscript.call('GetIsObjectValid',o) == 1 and #rows < MAX do
  local p = nwscript.call('GetPosition',o)
  local row = { id = o, tag = clean(nwscript.call('GetTag',o)), name = clean(nwscript.call('GetName',o)),
                x = p.x, y = p.y, z = p.z, dist = nwscript.call('GetDistanceBetween',pc, o) }
  if OBJECT_TYPE == 1 then
    row.hp = nwscript.call('GetCurrentHitPoints',o)
    row.dead = nwscript.call('GetIsDead',o)
    row.hostile = nwscript.call('GetIsEnemy',o, pc)
    row.action = nwscript.call('GetCurrentAction',o)
  elseif OBJECT_TYPE == 8 then
    row.open = nwscript.call('GetIsOpen',o)
    row.locked = nwscript.call('GetLocked',o)
  end
  rows[#rows + 1] = row
  o = nwscript.call('GetNextObjectInArea',area, OBJECT_TYPE)
end
table.sort(rows, function(a, b) return a.dist < b.dist end)
return rows
