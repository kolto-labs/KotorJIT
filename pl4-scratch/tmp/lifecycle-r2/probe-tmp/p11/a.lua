function OnScriptUnload() local ok, e = pcall(kp.scripts.list); note(ok and 'list-ok' or ('list-err:' .. tostring(e))) end
