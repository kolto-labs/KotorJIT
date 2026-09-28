-- L1 camera diagnostic: NON-ACCEPTANCE host script (the creative runner requires one --script).
-- Inert: one native-log line at load, no timers, no engine routines, no writes.
-- The line also serves as the runner's --marker so the clip logic has an anchor;
-- L1 media is not acceptance media and is not reviewed as such.
local present = (kp and kp.camera and kp.camera.snapshot) and 'present' or 'absent'
if kp and kp.print then kp.print('[l1cam] loaded camera=' .. present) end
