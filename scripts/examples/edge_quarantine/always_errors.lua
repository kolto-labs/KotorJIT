-- Errors on every call. The error budget in kp_luatest is 3, so the third
-- failure quarantines this script instead of letting it log forever.
function OnTick(tick, relevant)
    error("deliberate failure on tick " .. tostring(tick))
end
