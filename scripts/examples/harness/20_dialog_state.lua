-- Conversation state from the engine's side. Pair it with the harness
-- `state` command's `dialog` block (entry, waiting_for_player,
-- waiting_on_sound, replies), which reads the GUI panel.
--
-- A conversation that shows active=1 here while the panel has entry=-1 and
-- nobody is in it (pc_in=0, partner_in=0) is still initialising: the owner
-- has not sent its first entry. `dialog_skip` fails on it ("dialog owner has
-- no game object"); wait, then escalate to `dialog_abort` if it never starts.

local PARTNER_TAG = "end_trask"

local function clean(s) return (s:gsub("%z", "")) end

local pc = nwscript.call('GetFirstPC')
local partner = nwscript.call('GetObjectByTag',PARTNER_TAG, 0)

local out = {
  active = nwscript.call('GetIsConversationActive'),
  pc_in = nwscript.call('GetIsInConversation',pc),
  last_speaker = clean(nwscript.call('GetTag',nwscript.call('GetLastSpeaker'))),
  pc_speaker = clean(nwscript.call('GetTag',nwscript.call('GetPCSpeaker'))),
  pc_action = nwscript.call('GetCurrentAction',pc),
}
if nwscript.call('GetIsObjectValid',partner) == 1 then
  out.partner_in = nwscript.call('GetIsInConversation',partner)
  out.partner_action = nwscript.call('GetCurrentAction',partner)   -- 7 == dialog object
  out.partner_dist = nwscript.call('GetDistanceBetween',pc, partner)
end
return out
