-- Doors: inspect one, and open it the way the Endar Spire scripts do.
--
-- Endar's story doors (end_door01/02/05, ...) are plot doors the PC cannot
-- use: GetIsDoorActionPossible(d, 0) is 0, and a PC-queued ActionOpenDoor,
-- the retail `door_use` command and DoDoorAction all drop silently. The
-- authored scripts open them by having the door command itself
-- (k_pend_traskdl40 for end_door01), which is what OPEN=true does here.
-- Poll GetIsOpen afterwards; the open completes within a few ticks.
--
-- If GetIsOpen stays 0 after the self-command, the door is stuck in the
-- first phase of opening: the engine sets the "opening" animation but only
-- commits open_state (what GetIsOpen and the walkmesh read) from the
-- client's animation-done callback, which the headless client does not
-- deliver for doors unlocked at runtime (both end_door05s, end_door04). Once
-- stuck, every further open action is a no-op. The harness command
-- `door_commit_open` (CSWSDoor::MoveToNextOpenState) finishes the open; the
-- `scripted_door_open` route verb sends it itself after 2.5s.

local TAG = "end_door05"
local OPEN = false

local d = nwscript.call('GetObjectByTag',TAG, 0)
if nwscript.call('GetIsObjectValid',d) ~= 1 then error("no door tagged " .. TAG) end

local pc = nwscript.call('GetFirstPC')
local info = {
  tag = TAG, id = d,
  open = nwscript.call('GetIsOpen',d),
  locked = nwscript.call('GetLocked',d),
  key_required = nwscript.call('GetLockKeyRequired',d),
  plot = nwscript.call('GetPlotFlag',d),
  pc_can_open = nwscript.call('GetIsDoorActionPossible',d, 0),   -- 0 == DOOR_ACTION_OPEN
  dist = nwscript.call('GetDistanceBetween',pc, d),
}

if OPEN and info.open == 0 then
  kp.as(d, function() nwscript.call('ActionOpenDoor',d) end)
  info.queued = true
end
return info
