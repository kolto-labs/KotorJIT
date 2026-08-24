-- Abstains by returning nothing. Runs first, but does not decide the event.
--
--   kp_luatest scripts/examples/arbitration OnScriptEvent k_def_heartbeat01 1
--
-- Expect: claimed by 25_claims_via_string (priority 80, the highest
-- priority script that returns something convertible), not by this one.
priority = 100

function OnRunScript(script, object, has_object, relevant)
    print(("[10_abstain_nil]  script=%s object=%d relevant=%s -> nil")
          :format(script, object, tostring(relevant)))
    -- no return
end
