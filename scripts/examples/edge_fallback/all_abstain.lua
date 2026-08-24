-- Nobody claims, so the event falls back to its declared default.
-- OnScriptEvent declares fallback = "true", so the script is allowed to run.
function OnScriptEvent(script, object, relevant)
    print("[all_abstain] returning nil")
end
