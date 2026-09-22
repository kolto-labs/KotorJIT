-- Fire an authored UserDefined event, the way a module's own scripts do.
--
-- Endar's room5 ambush is a chain: door10_cut2's OnOpen checks that a party
-- member opened it (IsObjectPartyMember(GetLastOpenedBy())), plays two
-- cosmetic CutsceneAttacks, then SignalEvent(area, UserDefined 20). The
-- area's handler (k_pend_area02, case 20) cancels combat and has Trask start
-- the cutscene conversation whose scripts turn end_cut2_sith1/2/4 hostile.
-- A door opened by self-command never passes that party-member check, so the
-- route signals the event itself and gets the same authored result minus
-- the two cosmetic swings. Verified live: the dialog runs, the three Sith
-- flip to faction 1, the extras despawn.
--
-- TARGET: "area" for the PC's area, or an object tag.

local TARGET = "area"
local EVENT = 20

local pc = nwscript.call('GetFirstPC')
local who
if TARGET == "area" then
  who = nwscript.call('GetArea',pc)
else
  who = nwscript.call('GetObjectByTag',TARGET, 0)
  if nwscript.call('GetIsObjectValid',who) ~= 1 then error("no object tagged " .. TARGET) end
end
nwscript.call('SignalEvent',who, nwscript.call('EventUserDefined',EVENT))
return { target = TARGET, event = EVENT, id = who }
