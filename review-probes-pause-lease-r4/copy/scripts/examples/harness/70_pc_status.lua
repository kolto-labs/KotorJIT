-- The PC in detail: hit points, active effects, equipped slots, inventory.
-- Effects explain a creature that will not move or act (paralysis, cutscene
-- holds); an empty list with commandable=1 means the block is elsewhere
-- (paused world timers, see README).

local function clean(s) return (s:gsub("%z", "")) end

local pc = nwscript.call('GetFirstPC')
local out = {
  hp = nwscript.call('GetCurrentHitPoints',pc),
  max_hp = nwscript.call('GetMaxHitPoints',pc),
  dead = nwscript.call('GetIsDead',pc),
  commandable = nwscript.call('GetCommandable',pc),
  in_combat = nwscript.call('GetIsInCombat',pc),
  action = nwscript.call('GetCurrentAction',pc),
  effects = {},
  slots = {},
  inventory = {},
}

local e = nwscript.call('GetFirstEffect',pc)
while nwscript.call('GetIsEffectValid',e) == 1 do
  out.effects[#out.effects + 1] = nwscript.call('GetEffectType',e)
  e = nwscript.call('GetNextEffect',pc)
end

-- INVENTORY_SLOT_* 0..11; 4 is the right weapon on Endar's short sword.
for slot = 0, 11 do
  local it = nwscript.call('GetItemInSlot',slot, pc)
  if nwscript.call('GetIsObjectValid',it) == 1 then out.slots["slot" .. slot] = clean(nwscript.call('GetTag',it)) end
end

local it = nwscript.call('GetFirstItemInInventory',pc)
while nwscript.call('GetIsObjectValid',it) == 1 do
  out.inventory[#out.inventory + 1] = { id = it, tag = clean(nwscript.call('GetTag',it)) }
  it = nwscript.call('GetNextItemInInventory',pc)
end
return out
