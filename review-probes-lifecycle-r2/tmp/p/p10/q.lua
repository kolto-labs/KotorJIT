kp.registertimer(1, function() kp.scripts.reload('q'); error('boom') end)
kp.registertimer(1, function() error('boom2') end)
