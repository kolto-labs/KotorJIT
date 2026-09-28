function OnTick() note('new-tick') end
bind('OnSave', function() note('new-save') end)
nested_dispatch()
function OnScriptLoad() note('new-load'); nested_dispatch() end
