-- Abstains by returning nothing. Runs first, but does not decide the event.
--
--   kp_luatest scripts/examples/arbitration OnScriptEvent k_def_heartbeat01 1
--
-- Expect: claimed by 30_claims_false, not by this script.
priority = 100

function OnScriptEvent(script, object, relevant)
    print(("[10_abstain_nil]  script=%s object=%d relevant=%s -> nil")
          :format(script, object, tostring(relevant)))
    -- no return
end
