-- World probe: where the PC is, who is hostile nearby, what the party looks
-- like. One round trip; everything a combat or movement decision needs.
--
-- Returns:
--   pc        {x, y, z, hp, max_hp, in_combat, action, commandable}
--   hostiles  [{id, tag, hp, dist, action}], nearest first, within RADIUS
--   party     [{id, tag, hp, dist, action}] for the other party members
--   globals   the END_* room counters that gate the Endar Spire doors

local RADIUS = 60.0

local function clean(s) return (s:gsub("%z", "")) end

local pc = nwscript.call('GetFirstPC')
local area = nwscript.call('GetArea',pc)
local p = nwscript.call('GetPosition',pc)

local out = {
  pc = {
    x = p.x, y = p.y, z = p.z,
    hp = nwscript.call('GetCurrentHitPoints',pc),
    max_hp = nwscript.call('GetMaxHitPoints',pc),
    in_combat = nwscript.call('GetIsInCombat',pc),
    action = nwscript.call('GetCurrentAction',pc),
    commandable = nwscript.call('GetCommandable',pc),
  },
  hostiles = {},
  party = {},
  globals = {},
}

-- 1 == OBJECT_TYPE_CREATURE
local c = nwscript.call('GetFirstObjectInArea',area, 1)
while nwscript.call('GetIsObjectValid',c) == 1 do
  if c ~= pc then
    local d = nwscript.call('GetDistanceBetween',pc, c)
    local row = { id = c, tag = clean(nwscript.call('GetTag',c)),
                  hp = nwscript.call('GetCurrentHitPoints',c), dist = d,
                  action = nwscript.call('GetCurrentAction',c) }
    if nwscript.call('GetIsEnemy',c, pc) == 1 and nwscript.call('GetIsDead',c) == 0 and d <= RADIUS then
      out.hostiles[#out.hostiles + 1] = row
    elseif nwscript.call('IsObjectPartyMember', c) == 1 then
      out.party[#out.party + 1] = row
    end
  end
  c = nwscript.call('GetNextObjectInArea',area, 1)
end
table.sort(out.hostiles, function(a, b) return a.dist < b.dist end)

for _, g in ipairs({ "END_ROOM3_DEAD", "END_ROOM5_DEAD", "END_ROOM7_DEAD",
                     "END_ROOM8_DEAD", "END_SITH_DEAD", "END_TRASK_DLG",
                     "END_BRIDGE_SEALED" }) do
  out.globals[g] = nwscript.call('GetGlobalNumber',g)
end

return out
