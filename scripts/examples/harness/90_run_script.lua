-- Run an authored NCS with a chosen object as OBJECT_SELF.
--
-- This is how the route fires scripts whose only in-game trigger has no
-- headless equivalent. Verified live on the Endar Spire:
--   k_pend_door20 on end_door08   the bridge door's OnFailToOpen (a click on
--                                  the locked plot door): checks
--                                  END_ROOM8_DEAD >= 2, spawns the bridge
--                                  Sith, unlocks and opens itself, sets
--                                  TraskState 31, despawns the placeholder
--                                  Carth.
--   k_pend_reinfrc03 on end_jedicut the cutscene node that creates
--                                  end_reinforce1/2 at their _1 waypoints.
--   k_pman_npcstart on end_trask   restarts a companion's follow/combat AI
--                                  after a cutscene's k_pman_npcstop.
--
-- The script decides its own postconditions (it may refuse: door20 does
-- nothing under the kill threshold), so read the world afterwards -- door
-- lock/open flags, globals, spawned tags -- rather than trusting the call.

local SCRIPT = "k_pend_door20"
local TARGET_TAG = "end_door08"   -- or nil for the PC

local who
if TARGET_TAG then
  who = nwscript.call('GetObjectByTag',TARGET_TAG, 0)
  if nwscript.call('GetIsObjectValid',who) ~= 1 then error("no object tagged " .. TARGET_TAG) end
else
  who = nwscript.call('GetFirstPC')
end
nwscript.call('ExecuteScript',SCRIPT, who)
return { script = SCRIPT, on = TARGET_TAG or "pc", id = who }
