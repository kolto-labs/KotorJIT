-- Claims the event by returning the STRING "1". A string that parses whole
-- converts, so this is a real vote.
--
-- Set priority above 30_claims_false to see this one win instead.
priority = 80

function OnRunScript(script, object, has_object, relevant)
    print(("[25_claims_via_string]  relevant=%s -> \"1\" (converts to true)")
          :format(tostring(relevant)))
    return "1"
end
