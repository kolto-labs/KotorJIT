-- Abstains by returning a string that is not a number. Highest priority after
-- the nil case, and still does not decide the event.
--
-- "not-a-number" cannot convert to bool, so this is an abstention, not a vote.
-- Compare with 25_claims_via_string, which returns "1" and does convert.
priority = 90

function OnScriptEvent(script, object, relevant)
    print(("[20_abstain_badstring]  relevant=%s -> \"not-a-number\"")
          :format(tostring(relevant)))
    return "not-a-number"
end
