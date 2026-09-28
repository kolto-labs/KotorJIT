kp.registertimer(10, function() note('staged-fn') return true end)
kp.registertimer(10, 'cb')
error('late throw')
