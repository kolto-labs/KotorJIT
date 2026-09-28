
local T={x=2,y=-2.25,z=0.125}
local T2={x=2.5,y=-2.25,z=0.125}
function rel(tag,t) local c=kp.motion.capture(42) local m,s=kp.motion.relocate(c,t or T) note(tag,m,s) end
function res(tag) local m,e=kp.motion.restore(42) note(tag,m,m and tostring(m.position.x) or e) end

function OnScriptLoad() end
