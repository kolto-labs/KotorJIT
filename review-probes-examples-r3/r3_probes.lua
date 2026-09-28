-- Round-3 adversarial probes for 40_chain_reaction.lua (host fixture only).
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
local path = "scripts/examples/cursed/40_chain_reaction.lua"
F.sources = { [path] = arg and arg[1] or path }
local function fresh() return F.new(path):load() end
local function sets(f, from)
  local out = {}
  for i = from + 1, #f.calls do local c = f.calls[i]
    if c.name == "SetMinOneHP" then out[#out+1] = ("%s<-%s"):format(tostring(c.args[1]), tostring(c.args[2])) end end
  return table.concat(out, " ")
end

-- R3-1: two gone entries resolve to the same new object (last write wins).
-- PC 1 (tag pc, prior 0) guarded; control swaps to 7 (tag atton, prior 1)
-- while 1 stays valid; a blast guards 7 with pc=true. Module load recreates
-- both: pc->11, atton->12, GetFirstPC=12.
do
  local f = fresh(); f.area_objects = {20, 21, 1}; f:arm()
  f.env.OnRunScript("k_def_death01", 20)
  f.objects[7] = {tag="atton", party=1, x=0, min_one_hp=1}; f.party = {7, 1}
  f.overrides.GetFirstPC = function() return 7 end
  f.area_objects = {21, 7}; f.env.OnRunScript("k_def_death01", 21)
  local n = 0; for _ in pairs(f.objects) do n = n + 1 end
  f.objects[11] = {tag="pc", party=1, x=0, min_one_hp=f.objects[1].min_one_hp}
  f.objects[12] = {tag="atton", party=1, x=0, min_one_hp=f.objects[7].min_one_hp}
  f.objects[1] = nil; f.objects[7] = nil; f.party = {12, 11}
  f.overrides.GetFirstPC = function() return 12 end
  local before = #f.calls
  f.env.OnModuleLoad()
  print(("R3-1 two-gone-same-target: sets=[%s] old_pc(11)=%s atton(12,prior1)=%s pending_logged=%s")
    :format(sets(f, before), tostring(f.objects[11].min_one_hp), tostring(f.objects[12].min_one_hp),
            tostring(f:has("restore pending"))))
end

-- R3-2: session-wide owned[] + recycled numeric ID. Blast guards PC 1 and
-- bastila 2; settle restores both (owned={1,2}). Second blast guards PC 1
-- (prior 0). Module load: PC recreated under recycled ID 2 (was bastila's).
do
  local f = fresh(); f.area_objects = {20, 21, 2, 1}; f:arm()
  f.env.OnRunScript("k_def_death01", 20); assert(f:fire(#f.timers) == false)
  assert(f.objects[1].min_one_hp == 0 and f.objects[2].min_one_hp == 0)
  f.area_objects = {21, 1}; f.env.OnRunScript("k_def_death01", 21)
  assert(f.objects[1].min_one_hp == 1)
  f.objects[2] = {tag="pc", party=1, x=0, min_one_hp=1}; f.objects[1] = nil; f.party = {2}
  f.overrides.GetFirstPC = function() return 2 end
  local before = #f.calls
  f.env.OnModuleLoad()
  local after_load = f.objects[2].min_one_hp
  f.env.OnAreaEnter()
  f:arm(); f.objects[22] = {tag="sith3", x=0}; f.area_objects = {22, 2}
  f.env.OnRunScript("k_def_death01", 22); f:fire(#f.timers)
  f.env.OnScriptUnload()
  local pend = 0; for _, s in ipairs(f.prints) do if s:find("restore pending", 1, true) then pend = pend + 1 end end
  print(("R3-2 recycled-owned-id PC: after_load=%s after_blast_settle_unload=%s pending_logs=%d sets=[%s]")
    :format(tostring(after_load), tostring(f.objects[2].min_one_hp), pend, sets(f, before)))
end

-- R3-3: same-tag member on a recycled owned ID. Bastila 2 guarded+restored
-- earlier with PC 1 (owned {1,2}); later blast guards bastila 2 only; module
-- load: PC gets new id 9, bastila recycled onto id 1.
do
  local f = fresh(); f.area_objects = {20, 21, 2, 1}; f:arm()
  f.env.OnRunScript("k_def_death01", 20); f:fire(#f.timers)
  f.area_objects = {21, 2}; f.env.OnRunScript("k_def_death01", 21)
  f.objects[9] = {tag="pc", party=1, x=0, min_one_hp=0}
  f.objects[1] = {tag="bastila", party=1, x=1, min_one_hp=f.objects[2].min_one_hp}; f.objects[2] = nil
  f.party = {9, 1}; f.overrides.GetFirstPC = function() return 9 end
  f.env.OnModuleLoad()
  print(("R3-3 same-tag recycled owned id: bastila(1)=%s pending=%s")
    :format(tostring(f.objects[1].min_one_hp), tostring(f:has("restore pending: bastila"))))
end

-- R3-4: unload with a pending entry: state dropped, flag stays.
do
  local f = fresh(); f.area_objects = {20, 21, 2, 1}; f:arm()
  f.env.OnRunScript("k_def_death01", 20)
  local saved = f.objects[2]; f.objects[2] = nil; f.party = {1}
  f.env.OnScriptUnload()
  print(("R3-4 unload while member absent: bastila_flag=%s pending_logged=%s (script state discarded after unload)")
    :format(tostring(saved.min_one_hp), tostring(f:has("restore pending: bastila"))))
end

-- R3-5: literal same-tag ID reuse. Bastila 2 guarded (prior 0). After load,
-- id 2 is valid but names a NON-party creature with tag 'bastila' (flag 1);
-- the real Bastila is id 5 (carried flag 1).
do
  local f = fresh(); f:arm()
  f.env.OnRunScript("k_def_death01", 20); assert(f.objects[2].min_one_hp == 1)
  f.objects[5] = {tag="bastila", party=1, x=1, min_one_hp=1}
  f.objects[2] = {tag="bastila", x=9, min_one_hp=1}; f.party = {1, 5}
  local before = #f.calls
  f.env.OnModuleLoad()
  print(("R3-5 same-tag valid stored id, non-party: sets=[%s] impostor(2)=%s real_bastila(5)=%s pending=%s")
    :format(sets(f, before), tostring(f.objects[2].min_one_hp), tostring(f.objects[5].min_one_hp),
            tostring(f:has("restore pending"))))
end
