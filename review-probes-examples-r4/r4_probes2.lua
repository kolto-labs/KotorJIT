-- Round-4 probes, part 2: writer grill #1 carry case, and R4-1b check (a).
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
local path = "scripts/examples/cursed/40_chain_reaction.lua"
F.sources = { [path] = arg and arg[1] or path }
local function nprint(f, t) local n = 0 for _, s in ipairs(f.prints) do if s:find(t, 1, true) then n = n + 1 end end return n end
local function sets(f, from) local o = {} for i = (from or 0) + 1, #f.calls do local c = f.calls[i]
  if c.name == "SetMinOneHP" then o[#o+1] = c.args[1].."<-"..c.args[2] end end return table.concat(o, " ") end
-- G1: PC tag '' guarded (prior 0). Control goes to TAGGED bastila (GetFirstPC
-- fails fits). Same-module OnAreaEnter bumps the epoch. An untagged non-PC
-- member 5 with a genuine 1 (never guarded) is blasted, then settle.
do
  local f = F.new(path):load(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.objects[5] = {tag = "", party = 1, x = 2, min_one_hp = 1}; f.party = {1, 2, 5}
  f.overrides.GetFirstPC = function() return 2 end
  f.env.OnAreaEnter(99, 31); f:arm()
  local b = #f.calls
  f.objects[22] = {tag = "sith3", x = 2}; f.area_objects = {22, 5}
  f.env.OnRunScript("k_def_death01", 22); f:fire(#f.timers)
  f.overrides.GetFirstPC = function() return 1 end; f.env.OnAreaEnter(99, 1)
  print(("G1 untagged carry onto genuine-1 member: sets=[%s] member5=%s pc1=%s pending_total=%d prior_unknown=%d")
    :format(sets(f, b), tostring(f.objects[5].min_one_hp), tostring(f.objects[1].min_one_hp),
            nprint(f, "restore pending"), nprint(f, "prior unknown")))
end
-- R4-1b(a): R4-1b state, then the PC itself is blasted while control is
-- still on bastila; settle. Does the carry keep the PC's prior 0?
do
  local f = F.new(path):load(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.overrides.GetFirstPC = function() return 2 end
  f.env.OnAreaEnter(99, 23); f:arm()
  local stuck = f.objects[1].min_one_hp
  f.objects[22] = {tag = "sith3", x = 0}; f.area_objects = {22, 1}
  f.env.OnRunScript("k_def_death01", 22); f:fire(#f.timers)
  print(("R4-1b(a) PC blasted again while control swapped: before=%s after_settle=%s")
    :format(tostring(stuck), tostring(f.objects[1].min_one_hp)))
end
-- R4-1b(b): R4-1b state; control stays on bastila; no further blast on the
-- PC; blasts elsewhere and settles keep happening. Is the PC still 1?
do
  local f = F.new(path):load(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.overrides.GetFirstPC = function() return 2 end
  f.env.OnAreaEnter(99, 23); f:arm()
  for i = 1, 3 do f.objects[40 + i] = {tag = "s"..i, x = 50}; f.area_objects = {40 + i}
    f.env.OnRunScript("k_def_death01", 40 + i); f:fire(#f.timers) end
  print(("R4-1b(b) control stays swapped, 3 more blast+settle cycles elsewhere: pc1=%s pending_total=%d")
    :format(tostring(f.objects[1].min_one_hp), nprint(f, "restore pending")))
  f.overrides.GetFirstPC = function() return 1 end
  f.objects[50] = {tag = "s9", x = 50}; f.area_objects = {50}
  f.env.OnRunScript("k_def_death01", 50); f:fire(#f.timers)
  print(("R4-1b(b2) control back on PC, next settle: pc1=%s"):format(tostring(f.objects[1].min_one_hp)))
end
