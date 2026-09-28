local keep = {}
for i=1,4 do keep[i] = {} end
bind('OnSave', function() note('new-onsave') end)
T = kp.registertimer(100000, function() note('new-timer') return true end, {tag='ud'})
nested_dispatch()
