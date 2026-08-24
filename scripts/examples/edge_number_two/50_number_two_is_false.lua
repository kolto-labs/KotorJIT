-- A boolean result is compared against 1, so returning 2 yields FALSE.
-- Surprising, and deliberate: widening it would change which scripts win.
--
-- Run alone to see it:
--   kp_luatest scripts/examples/arbitration/only_two OnScriptEvent x 1
priority = -100

function OnScriptEvent(script, object, relevant)
    print(("[50_number_two_is_false]  relevant=%s -> 2 (converts to FALSE)")
          :format(tostring(relevant)))
    return 2
end
