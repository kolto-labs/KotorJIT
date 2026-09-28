-- Cross a module transition the way the transition door does.
--
-- A transition door (end_door10 -> end_m01ab at waypoint from_01a) needs a
-- player "use", which plot doors refuse in headless mode. The door's own
-- transition boils down to StartNewModule(module, waypoint), so the route
-- calls that directly. Afterwards gate on the harness `state`:
--   wait module == "end_m01ab", then phase in {gameplay, dialog, paused}
-- (the arrival often opens with a dialog -- Carth's comlink call here).
--
-- INSPECT=true only reports the door's link; set it false to go.

local DOOR_TAG = "end_door10"
local MODULE, WAYPOINT = "end_m01ab", "from_01a"
local INSPECT = true

local pc = nwscript.call('GetFirstPC')
local d = nwscript.call('GetObjectByTag',DOOR_TAG, 0)
local info = {
  module_now = nwscript.call('GetModuleName'),
  door_valid = nwscript.call('GetIsObjectValid',d),
  door_dist = nwscript.call('GetIsObjectValid',d) == 1 and nwscript.call('GetDistanceBetween',pc, d) or -1,
  party = nwscript.call('GetPartyMemberCount'),
}
if INSPECT then return info end
nwscript.call('StartNewModule',MODULE, WAYPOINT)
info.requested = MODULE .. "/" .. WAYPOINT
return info
