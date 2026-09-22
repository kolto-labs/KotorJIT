-- Empty a container without the container GUI.
--
-- Engine tags are lowercase and several placeables often share one
-- ("metalbox", "footlker"), and GetObjectByTag returns the first match,
-- which may be an empty one. This picks the nearest same-tag placeable
-- that still holds items and takes each with ActionTakeItem(item,
-- container) -- the authored NWScript call -- so the PC never has to path
-- to a wall-flush box (ActionInteractObject is silently dropped there).
-- Verified live on the Endar Spire corridor: metalbox (medpac, credits) and
-- footlker (class-4 armor, long sword, two frag grenades).
--
-- Poll the PC's inventory afterwards; the takes complete within a few ticks.

local TAG = "metalbox"

local pc = nwscript.call('GetFirstPC')
local area = nwscript.call('GetArea',pc)
local best, best_d = nil, 1e9
local o = nwscript.call('GetFirstObjectInArea',area, 64)      -- 64 == OBJECT_TYPE_PLACEABLE
while nwscript.call('GetIsObjectValid',o) == 1 do
  if nwscript.call('GetTag',o):gsub("%z", ""):lower() == TAG
     and nwscript.call('GetIsObjectValid',nwscript.call('GetFirstItemInInventory',o)) == 1 then
    local d = nwscript.call('GetDistanceBetween',pc, o)
    if d < best_d then best, best_d = o, d end
  end
  o = nwscript.call('GetNextObjectInArea',area, 64)
end
if best == nil then return { taken = 0, reason = "no stocked placeable tagged " .. TAG } end

local items = {}
local it = nwscript.call('GetFirstItemInInventory',best)
while nwscript.call('GetIsObjectValid',it) == 1 do
  items[#items + 1] = it
  it = nwscript.call('GetNextItemInInventory',best)
end
nwscript.with_caller(pc, function()
  nwscript.call('ClearAllActions')
  for _, i in ipairs(items) do nwscript.call('ActionTakeItem',i, best) end
end)
return { container = best, dist = best_d, taken = #items }
