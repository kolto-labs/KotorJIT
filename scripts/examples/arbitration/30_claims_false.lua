-- Claims the event and blocks it. Returning false stops the game running that
-- NWScript at all.
priority = 70

function OnScriptEvent(script, object, relevant)
    print(("[30_claims_false]  relevant=%s -> false (BLOCK)")
          :format(tostring(relevant)))
    return false
end
